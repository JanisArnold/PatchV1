"""Standalone Pi voice-loop harness.

Pipeline: arecord -> STT (whisper.cpp or Vosk) -> PATCH -> Piper -> aplay.

Replies are streamed sentence-by-sentence: as soon as the LLM finishes the
first sentence, it is synthesized and queued for playback while the rest is
still generating. On a Pi 4 at a few tokens per second this is the difference
between speaking after ~2 seconds and speaking after ~20.
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

from patch.cli import build_app
from patch.config import load_config


def main() -> None:
    config = load_config()
    app = build_app()
    audio_path = Path(config.data_dir) / "voice_loop_input.wav"
    tts_dir = Path(config.data_dir) / "voice_loop_tts"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    tts_dir.mkdir(parents=True, exist_ok=True)

    transcribe = _build_stt(config)

    try:
        print("PATCH voice loop test. Press Enter to start recording (Enter again to stop), or type /exit.")
        while True:
            command = input("> ").strip()
            if command.lower() == "/exit":
                break

            capture_ms = _record_audio(config, audio_path)
            _record_perf(app, "audio.capture", capture_ms, {"device": config.audio_input_device})

            transcript, stt_ms = transcribe(audio_path)
            _record_perf(app, f"stt.{config.stt_engine}", stt_ms, {"engine": config.stt_engine})
            print(f"Transcript: {transcript}")
            if not transcript:
                print("No transcript returned. Try again.")
                continue

            turn_started = time.perf_counter()
            speaker = _SentenceSpeaker(config, tts_dir)
            try:
                reply = app.handle_text_turn(transcript, on_sentence=speaker.speak)
            finally:
                first_audio_ms, playback_total_ms = speaker.finish()
            if reply is None:
                continue
            print(f"Reply: {reply}")

            if first_audio_ms is not None:
                _record_perf(app, "tts.first_audio", first_audio_ms, {"voice": config.piper_voice_name})
            _record_perf(app, "audio.playback_total", playback_total_ms, {"device": config.audio_output_device})

            roundtrip_ms = int((time.perf_counter() - turn_started) * 1000)
            _record_perf(app, "turn.voice_roundtrip", roundtrip_ms, {"runtime_mode": app.runtime_mode})
    finally:
        app.close()


class _SentenceSpeaker:
    """Synthesizes sentences as they arrive and plays them in order."""

    def __init__(self, config, tts_dir: Path) -> None:
        self._config = config
        self._tts_dir = tts_dir
        self._queue: "queue.Queue[Path | None]" = queue.Queue()
        self._counter = 0
        self._started = time.perf_counter()
        self._first_audio_ms: int | None = None
        self._thread = threading.Thread(target=self._play_worker, daemon=True)
        self._thread.start()

    def speak(self, sentence: str) -> None:
        self._counter += 1
        wav_path = self._tts_dir / f"sentence_{self._counter:03d}.wav"
        _synthesize_speech(self._config, sentence, wav_path)
        self._queue.put(wav_path)

    def finish(self) -> tuple:
        """Wait for playback to drain; return (first_audio_ms, total_ms)."""
        self._queue.put(None)
        self._thread.join()
        total_ms = int((time.perf_counter() - self._started) * 1000)
        return self._first_audio_ms, total_ms

    def _play_worker(self) -> None:
        while True:
            wav_path = self._queue.get()
            if wav_path is None:
                return
            if self._first_audio_ms is None:
                self._first_audio_ms = int((time.perf_counter() - self._started) * 1000)
            subprocess.run(
                ["aplay", "-D", self._config.audio_output_device, str(wav_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )


def _build_stt(config):
    if config.stt_engine == "vosk":
        try:
            from vosk import KaldiRecognizer, Model
        except ImportError as exc:
            raise SystemExit("stt_engine is 'vosk' but the package is missing: pip install vosk") from exc
        model = Model(config.vosk_model_path)

        def transcribe(audio_path: Path) -> tuple:
            started = time.perf_counter()
            transcript = _transcribe_vosk(KaldiRecognizer, model, audio_path)
            return transcript, int((time.perf_counter() - started) * 1000)

        return transcribe

    def transcribe(audio_path: Path) -> tuple:
        started = time.perf_counter()
        transcript = _transcribe_whisper_cpp(config, audio_path)
        return transcript, int((time.perf_counter() - started) * 1000)

    return transcribe


def _transcribe_whisper_cpp(config, audio_path: Path) -> str:
    completed = subprocess.run(
        [
            config.whisper_cpp_binary,
            "-m",
            config.whisper_model_path,
            "-f",
            str(audio_path),
            "--no-prints",
            "--no-timestamps",
        ],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"whisper.cpp failed: {completed.stderr.strip()}")
    return " ".join(completed.stdout.split()).strip()


def _transcribe_vosk(KaldiRecognizer, model, audio_path: Path) -> str:
    with wave.open(str(audio_path), "rb") as wav_file:
        if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2 or wav_file.getframerate() != 16000:
            raise RuntimeError("Audio file must be WAV mono PCM 16-bit 16kHz for Vosk.")
        recognizer = KaldiRecognizer(model, wav_file.getframerate())
        chunks: list[str] = []
        while True:
            data = wav_file.readframes(4000)
            if not data:
                break
            if recognizer.AcceptWaveform(data):
                chunks.append(json.loads(recognizer.Result()).get("text", ""))
        chunks.append(json.loads(recognizer.FinalResult()).get("text", ""))
    return " ".join(part.strip() for part in chunks if part.strip()).strip()


def _record_audio(config, audio_path: Path) -> int:
    """Record until the user presses Enter (push-to-talk style).

    A fixed-length recording wastes the unused seconds twice: once waiting,
    once transcribing silence. `voice_record_seconds` is kept as a hard cap.
    arecord finalizes the WAV header cleanly on SIGTERM.
    """
    started = time.perf_counter()
    process = subprocess.Popen(
        [
            "arecord",
            "-D",
            config.audio_input_device,
            "-d",
            str(config.voice_record_seconds),
            "-f",
            "S16_LE",
            "-r",
            "16000",
            "-c",
            "1",
            str(audio_path),
        ],
    )
    input("Recording... press Enter to stop. ")
    if process.poll() is None:
        process.terminate()
    process.wait()
    return int((time.perf_counter() - started) * 1000)


def _synthesize_speech(config, text: str, tts_path: Path) -> int:
    started = time.perf_counter()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "piper",
            "--data-dir",
            config.piper_voice_dir,
            "-m",
            config.piper_voice_name,
            "-f",
            str(tts_path),
            "--",
            text,
        ],
        check=True,
    )
    return int((time.perf_counter() - started) * 1000)


def _record_perf(app, phase: str, latency_ms: int, metadata: dict[str, object]) -> None:
    app.perf_logger.log({"phase": phase, "latency_ms": latency_ms, **metadata})


if __name__ == "__main__":
    main()
