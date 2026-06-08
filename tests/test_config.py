import pytest
from dispatcher.config import Settings, get_settings
from pydantic import ValidationError


def test_defaults() -> None:
    settings = Settings()
    assert settings.app_name == "dispatcher"
    assert settings.database == "dispatcher.db"
    assert settings.log_level == "INFO"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISPATCHER_DATABASE", "custom.db")
    monkeypatch.setenv("DISPATCHER_LOG_LEVEL", "DEBUG")
    settings = Settings()
    assert settings.database == "custom.db"
    assert settings.log_level == "DEBUG"


def test_log_level_is_normalized_to_upper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISPATCHER_LOG_LEVEL", "debug")
    assert Settings().log_level == "DEBUG"


def test_invalid_log_level_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISPATCHER_LOG_LEVEL", "TRACE")
    with pytest.raises(ValidationError):
        Settings()


def test_empty_database_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISPATCHER_DATABASE", "")
    with pytest.raises(ValidationError):
        Settings()


def test_empty_app_name_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISPATCHER_APP_NAME", "")
    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
