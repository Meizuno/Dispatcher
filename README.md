# Dispatcher

A clean Python project base.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Development

```powershell
ruff check .        # lint
ruff format .       # format
mypy dispatcher     # type check
pytest              # tests
```

## Layout

```
dispatcher/         # application package
tests/              # test suite (mirrors dispatcher/)
pyproject.toml      # dependencies + tool config
```
