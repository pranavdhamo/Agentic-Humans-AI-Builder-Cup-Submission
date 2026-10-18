"""Runtime configuration, read from the environment (no secrets are stored or returned)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# server/app/config.py -> Legacy_enterprise_migration
ROOT = Path(__file__).resolve().parents[2]


def _carddemo_src() -> Path:
    return Path(os.environ.get("SRC") or os.environ.get("CARDDEMO_SRC") or Path.home() / "carddemo-env-local/carddemo/app")


@dataclass(frozen=True)
class Settings:
    app_name: str = "Legacy Migration Studio API"
    root: Path = ROOT
    carddemo_src: Path = field(default_factory=_carddemo_src)
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            os.environ.get(
                "STUDIO_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080"
            ).split(",")
        )
    )

    @property
    def jar(self) -> Path:
        return self.root / "migrated/carddemo-batch/target/carddemo-batch-0.1.0.jar"

    @property
    def results_dir(self) -> Path:
        return self.root / "pipeline/results"

    @property
    def runs_dir(self) -> Path:
        return self.root / "pipeline/runs"


settings = Settings()
