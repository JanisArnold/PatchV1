from __future__ import annotations


class TextInputAdapter:
    def get_input(self) -> str:
        return input("You> ").strip()


class TextOutputAdapter:
    def emit(self, text: str) -> None:
        print(f"PATCH> {text}")

    def begin_stream(self) -> None:
        print("PATCH> ", end="", flush=True)

    def emit_token(self, token: str) -> None:
        print(token, end="", flush=True)

    def end_stream(self) -> None:
        print()
