"""FastAPI application entry-point for GovBudgetChecker."""

from __future__ import annotations

from fastapi import FastAPI

from api.config import AppConfig

app = FastAPI(title="GovBudgetChecker API", version="0.1.0")


@app.get("/healthz")
def read_health() -> dict[str, str]:
    """Return a simple health check payload."""

    return {"status": "ok"}


@app.get("/config/rules")
def get_rules_config() -> dict[str, str]:
    """Expose the currently configured rules file path."""

    config = AppConfig.load()
    return {"rules_file": str(config.rules_file)}
