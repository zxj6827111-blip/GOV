# Healthcheck

## Quality

| Tool | Result | Notes |
| --- | --- | --- |
| `ruff check --fix` | ⚠️ | Applied auto-fixes; 70 lint errors remain (e.g., E402 import order, F8xx/F4xx unused symbols). |
| `mypy .` | ⚠️ | Syntax issue in `engine/table_alias_matcher.py` resolved; run now stops on missing type stubs and duplicate module discovery. |
