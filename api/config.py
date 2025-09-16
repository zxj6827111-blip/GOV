"""Configuration helpers for the FastAPI service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_RULES_FILE = Path(os.getenv("RULES_FILE", "rules/v3_3.yaml"))


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration for the API service."""

    rules_file: Path = DEFAULT_RULES_FILE

    @classmethod
    def load(cls) -> "AppConfig":
        """Load configuration from environment variables."""

        rules_file = Path(os.getenv("RULES_FILE", str(DEFAULT_RULES_FILE)))
        return cls(rules_file=rules_file)
