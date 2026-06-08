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
mypy src            # type check
pytest              # tests
```

## Layout

```
src/dispatcher/     # application package
tests/              # test suite (mirrors src/)
pyproject.toml      # dependencies + tool config
```
