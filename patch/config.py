from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from patch.contracts import ModelProfile


@dataclass
class AppConfig:
    name: str
    data_dir: Path
    benchmark_prompt_path: Path
    debug: bool
    default_profile: str
    recent_turn_limit: int
    max_fact_hits: int
    summary_turn_window: int
    active_provider: str
    ollama_base_url: str
    ollama_timeout_seconds: int
    model_profiles: Dict[str, ModelProfile]

    @property
    def database_path(self) -> Path:
        return self.data_dir / "patch.db"


def load_config() -> AppConfig:
    config_path = Path(
        os.environ.get("PATCH_CONFIG_PATH", "config/settings.json")
    )
    if not config_path.exists():
        config_path = Path("config/settings.example.json")

    raw = json.loads(config_path.read_text(encoding="utf-8"))

    base_dir = Path(os.environ.get("PATCH_DATA_DIR", raw["app"]["data_dir"]))
    benchmark_path = Path(raw["app"]["benchmark_prompt_path"])

    model_profiles: Dict[str, ModelProfile] = {}
    for name, value in raw["model_profiles"].items():
        extra = {
            key: val
            for key, val in value.items()
            if key
            not in {"provider", "model", "temperature", "top_p", "num_ctx", "system_prompt"}
        }
        model_profiles[name] = ModelProfile(
            name=name,
            provider=value["provider"],
            model=value["model"],
            temperature=float(value.get("temperature", 0.4)),
            top_p=float(value.get("top_p", 0.9)),
            num_ctx=int(value.get("num_ctx", 4096)),
            system_prompt=value.get("system_prompt", ""),
            options=extra,
        )

    return AppConfig(
        name=raw["app"]["name"],
        data_dir=base_dir,
        benchmark_prompt_path=benchmark_path,
        debug=bool(raw["app"].get("debug", False)),
        default_profile=raw["app"].get("default_profile", next(iter(model_profiles.keys()))),
        recent_turn_limit=int(raw["memory"]["recent_turn_limit"]),
        max_fact_hits=int(raw["memory"]["max_fact_hits"]),
        summary_turn_window=int(raw["memory"]["summary_turn_window"]),
        active_provider=raw["providers"]["active"],
        ollama_base_url=raw["providers"]["ollama"]["base_url"],
        ollama_timeout_seconds=int(raw["providers"]["ollama"]["timeout_seconds"]),
        model_profiles=model_profiles,
    )
