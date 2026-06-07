from __future__ import annotations

import json
import subprocess
import sys
import time
import wave
from pathlib import Path

from patch.cli import build_app
from patch.config import load_config


def main() -> None:
    try:
        from vosk import KaldiRecognizer, Model
    except ImportError as exc:
        raise SystemExit("Missing optional dependency 'vosk'. Install it on the Pi before running this script.") from exc

    config = load_config()
    app = build_app()
    audio_path = Path(config.data_dir) / "voice_loop_input.wav"
    tts_path = Path(config.data_dir) / "voice_loop_reply.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        print("PATCH voice loop test. Press Enter to record one turn, or type /exit.")
        while True:
            command = input("> ").strip()
            if command.lower() == "/exit":
                break

            capture_ms = _record_audio(config, audio_path)
            _record_perf(app, "audio.capture", capture_ms, {"device": config.audio_input_device})

            transcript, stt_ms = _transcribe_audio(Model, KaldiRecognizer, config, audio_path)
            _record_perf(app, "stt.vosk", stt_ms, {"model_path": config.vosk_model_path})
            print(f"Transcript: {transcript}")
            if not transcript:
                print("No transcript returned. Try again.")
                continue

            turn_started = time.perf_counter()
            reply = app.handle_text_turn(transcript)
            if reply is None:
                continue
            print(f"Reply: {reply}")

            tts_ms = _synthesize_speech(config, reply, tts_path)
            _record_perf(app, "tts.piper", tts_ms, {"voice": config.piper_voice_name})

            playback_start_ms, playback_total_ms = _play_audio(config, tts_path)
            _record_perf(app, "audio.playback_start", playback_start_ms, {"device": config.audio_output_device})
            _record_perf(app, "audio.playback_total", playback_total_ms, {"device": config.audio_output_device})

            roundtrip_ms = int((time.perf_counter() - turn_started) * 1000)
            _record_perf(app, "turn.voice_roundtrip", roundtrip_ms, {"runtime_mode": app.runtime_mode})
    finally:
        app.close()


def _record_audio(config, audio_path: Path) -> int:
    started = time.perf_counter()
    subprocess.run(
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
        check=True,
    )
    return int((time.perf_counter() - started) * 1000)


def _transcribe_audio(Model, KaldiRecognizer, config, audio_path: Path) -> tuple[str, int]:
    started = time.perf_counter()
    model = Model(config.vosk_model_path)
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
    transcript = " ".join(part.strip() for part in chunks if part.strip()).strip()
    return transcript, int((time.perf_counter() - started) * 1000)


def _synthesize_speech(config, reply: str, tts_path: Path) -> int:
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
            reply,
        ],
        check=True,
    )
    return int((time.perf_counter() - started) * 1000)


def _play_audio(config, tts_path: Path) -> tuple[int, int]:
    started = time.perf_counter()
    process = subprocess.Popen(
        ["aplay", "-D", config.audio_output_device, str(tts_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    playback_start_ms = int((time.perf_counter() - started) * 1000)
    process.wait()
    return playback_start_ms, int((time.perf_counter() - started) * 1000)


def _record_perf(app, phase: str, latency_ms: int, metadata: dict[str, object]) -> None:
    app.memory_store.record_performance_log(
        session_id=app.session_id,
        phase=phase,
        latency_ms=latency_ms,
        metadata_json=json.dumps(metadata),
    )


if __name__ == "__main__":
    main()
