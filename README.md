# Docket

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
mypy docket         # type check
pytest              # tests
```

## Layout

```
docket/             # application package
tests/              # test suite (mirrors docket/)
pyproject.toml      # dependencies + tool config
```
