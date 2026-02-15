"""Unit tests for epub2kr.config module."""
import json
from pathlib import Path

import pytest

import epub2kr.config as config_module
from epub2kr.config import DEFAULTS, load_config, save_config


@pytest.fixture
def temp_config_path(tmp_path, monkeypatch):
    """Mock CONFIG_PATH to use a temporary directory."""
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)
    return config_path


def test_load_config_returns_defaults_when_no_file_exists(temp_config_path):
    """load_config returns DEFAULTS when no config file exists."""
    assert not temp_config_path.exists()
    config = load_config()
    assert config == DEFAULTS


def test_load_config_merges_saved_values_with_defaults(temp_config_path):
    """load_config merges saved values with defaults."""
    saved_config = {
        "service": "deepl",
        "target_lang": "ko",
        "threads": 8,
    }
    temp_config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_config_path, "w") as f:
        json.dump(saved_config, f)

    config = load_config()

    # Saved values override defaults
    assert config["service"] == "deepl"
    assert config["target_lang"] == "ko"
    assert config["threads"] == 8

    # Unset keys use defaults
    assert config["source_lang"] == DEFAULTS["source_lang"]
    assert config["bilingual"] == DEFAULTS["bilingual"]
    assert config["font_size"] == DEFAULTS["font_size"]


def test_save_config_creates_parent_directories(tmp_path, monkeypatch):
    """save_config creates parent directories if they don't exist."""
    # Use a nested path to test directory creation
    config_path = tmp_path / "nested" / "dir" / "config.json"
    monkeypatch.setattr(config_module, "CONFIG_PATH", config_path)

    assert not config_path.parent.exists()

    config = {"service": "google", "target_lang": "en"}
    save_config(config)

    assert config_path.parent.exists()
    assert config_path.exists()


def test_save_then_load_config_round_trip(temp_config_path):
    """save_config then load_config preserves configuration."""
    original_config = {
        "service": "openai",
        "source_lang": "zh",
        "target_lang": "ko",
        "threads": 10,
        "model": "gpt-4",
        "bilingual": True,
        "font_size": "1.0em",
        "line_height": "2.0",
        "font_family": "Noto Sans KR",
    }

    save_config(original_config)
    loaded_config = load_config()

    # All saved values should be preserved
    for key in original_config:
        assert loaded_config[key] == original_config[key]


def test_load_config_handles_corrupt_json_gracefully(temp_config_path):
    """load_config returns defaults when config file has corrupt JSON."""
    temp_config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_config_path, "w") as f:
        f.write("{ invalid json }")

    config = load_config()
    assert config == DEFAULTS


def test_load_config_handles_missing_file_gracefully(temp_config_path):
    """load_config returns defaults when config file is missing."""
    # Explicitly ensure file doesn't exist
    if temp_config_path.exists():
        temp_config_path.unlink()

    config = load_config()
    assert config == DEFAULTS


def test_saved_config_overrides_defaults(temp_config_path):
    """Saved config overrides defaults, unset keys use defaults."""
    partial_config = {
        "service": "ollama",
        "model": "llama3",
    }

    save_config(partial_config)
    config = load_config()

    # Overridden values
    assert config["service"] == "ollama"
    assert config["model"] == "llama3"

    # Default values for unset keys
    assert config["source_lang"] == DEFAULTS["source_lang"]
    assert config["target_lang"] == DEFAULTS["target_lang"]
    assert config["threads"] == DEFAULTS["threads"]
    assert config["bilingual"] == DEFAULTS["bilingual"]
    assert config["font_size"] == DEFAULTS["font_size"]
    assert config["line_height"] == DEFAULTS["line_height"]
    assert config["font_family"] == DEFAULTS["font_family"]


def test_load_config_handles_oserror_gracefully(temp_config_path, monkeypatch):
    """load_config returns defaults when file read fails with OSError."""
    # Create the file to ensure it exists
    temp_config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_config_path, "w") as f:
        json.dump({"service": "deepl"}, f)

    # Mock open to raise OSError
    def mock_open(*args, **kwargs):
        raise OSError("Permission denied")

    monkeypatch.setattr("builtins.open", mock_open)

    config = load_config()
    assert config == DEFAULTS


def test_save_config_preserves_unicode(temp_config_path):
    """save_config preserves Unicode characters (ensure_ascii=False)."""
    config = {
        "service": "google",
        "font_family": "맑은 고딕",  # Korean font name
    }

    save_config(config)

    with open(temp_config_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Should contain the Korean text directly, not escaped
    assert "맑은 고딕" in content


def test_save_config_formats_json_with_indent(temp_config_path):
    """save_config formats JSON with indentation for readability."""
    config = {
        "service": "google",
        "threads": 4,
    }

    save_config(config)

    with open(temp_config_path, "r") as f:
        content = f.read()

    # Check for indentation (indent=2)
    assert "  " in content  # Should have 2-space indentation
    assert content.count("\n") >= 3  # Multi-line output
