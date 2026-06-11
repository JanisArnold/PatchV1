# V1 Roadmap

PATCH V0 is the permanent brain foundation for Raspberry Pi V1.

For the full staged plan from PC testing to Pi deployment, voice, camera, display, and optimization, use the canonical roadmap:

- [Project Roadmap](../roadmap.md)

## V1 summary

The main V1 additions beyond V0 are:

- speech-to-text input (whisper.cpp `small.en`, silero-VAD later)
- text-to-speech output (Piper, fed sentence-by-sentence from the token stream)
- LanceDB-backed episodic memory on the Pi
- camera integration (Gemma 4 is natively multimodal — frames go straight in, no second model)
- eye/display UI driven by orchestrator states
- Pi deployment validation
- optional `systemd` startup for `llama-server` and PATCH

The terminal-mode brain core should stay reusable, with one efficient local default model and cloud fallback reserved for heavier tasks later.
