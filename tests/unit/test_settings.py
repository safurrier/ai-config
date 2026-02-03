"""Tests for ai_config.settings module."""

import json
from pathlib import Path

from ai_config.settings import merge_settings, read_json, write_json


class TestReadJson:
    """Tests for read_json function."""

    def test_file_not_exists(self, tmp_path: Path) -> None:
        """Non-existent file returns empty dict."""
        result = read_json(tmp_path / "missing.json")
        assert result == {}

    def test_empty_file(self, tmp_path: Path) -> None:
        """Empty file returns empty dict."""
        path = tmp_path / "empty.json"
        path.write_text("")
        result = read_json(path)
        assert result == {}

    def test_whitespace_only_file(self, tmp_path: Path) -> None:
        """Whitespace-only file returns empty dict."""
        path = tmp_path / "whitespace.json"
        path.write_text("   \n\t  ")
        result = read_json(path)
        assert result == {}

    def test_valid_json(self, tmp_path: Path) -> None:
        """Valid JSON file is parsed correctly."""
        path = tmp_path / "valid.json"
        path.write_text('{"key": "value", "number": 42}')
        result = read_json(path)
        assert result == {"key": "value", "number": 42}

    def test_nested_json(self, tmp_path: Path) -> None:
        """Nested JSON structures are preserved."""
        path = tmp_path / "nested.json"
        data = {"outer": {"inner": {"deep": [1, 2, 3]}}}
        path.write_text(json.dumps(data))
        result = read_json(path)
        assert result == data


class TestWriteJson:
    """Tests for write_json function."""

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Parent directories are created if they don't exist."""
        path = tmp_path / "a" / "b" / "c" / "settings.json"
        write_json(path, {"key": "value"})
        assert path.exists()
        assert read_json(path) == {"key": "value"}

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Existing file is overwritten."""
        path = tmp_path / "settings.json"
        path.write_text('{"old": "value"}')
        write_json(path, {"new": "value"})
        assert read_json(path) == {"new": "value"}

    def test_formatting_with_indent(self, tmp_path: Path) -> None:
        """Output is formatted with 2-space indent."""
        path = tmp_path / "settings.json"
        write_json(path, {"key": "value"})
        content = path.read_text()
        assert "  " in content  # Has indentation
        assert content.endswith("\n")  # Ends with newline

    def test_complex_structure(self, tmp_path: Path) -> None:
        """Complex nested structures are preserved."""
        path = tmp_path / "settings.json"
        data = {
            "plugins": [
                {"id": "plugin1", "enabled": True},
                {"id": "plugin2", "enabled": False},
            ],
            "settings": {"theme": "dark", "nested": {"level": 2}},
        }
        write_json(path, data)
        result = read_json(path)
        assert result == data


class TestMergeSettings:
    """Tests for merge_settings function."""

    def test_empty_base(self) -> None:
        """Updates applied to empty base."""
        result = merge_settings({}, {"key": "value"})
        assert result == {"key": "value"}

    def test_empty_updates(self) -> None:
        """Empty updates preserves base."""
        result = merge_settings({"key": "value"}, {})
        assert result == {"key": "value"}

    def test_non_overlapping_keys(self) -> None:
        """Non-overlapping keys are combined."""
        result = merge_settings({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_overlapping_scalar_keys(self) -> None:
        """Overlapping scalar keys are overwritten."""
        result = merge_settings({"a": 1, "b": 2}, {"b": 3})
        assert result == {"a": 1, "b": 3}

    def test_nested_dict_merge(self) -> None:
        """Nested dicts are merged recursively."""
        base = {"outer": {"a": 1, "b": 2}}
        updates = {"outer": {"b": 3, "c": 4}}
        result = merge_settings(base, updates)
        assert result == {"outer": {"a": 1, "b": 3, "c": 4}}

    def test_deep_nested_merge(self) -> None:
        """Deep nested dicts are merged correctly."""
        base = {"l1": {"l2": {"l3": {"a": 1}}}}
        updates = {"l1": {"l2": {"l3": {"b": 2}}}}
        result = merge_settings(base, updates)
        assert result == {"l1": {"l2": {"l3": {"a": 1, "b": 2}}}}

    def test_dict_replaced_by_scalar(self) -> None:
        """Dict can be replaced by scalar."""
        base = {"key": {"nested": "value"}}
        updates = {"key": "scalar"}
        result = merge_settings(base, updates)
        assert result == {"key": "scalar"}

    def test_scalar_replaced_by_dict(self) -> None:
        """Scalar can be replaced by dict."""
        base = {"key": "scalar"}
        updates = {"key": {"nested": "value"}}
        result = merge_settings(base, updates)
        assert result == {"key": {"nested": "value"}}

    def test_base_not_mutated(self) -> None:
        """Original base dict is not mutated."""
        base = {"a": 1, "b": {"c": 2}}
        base_copy = {"a": 1, "b": {"c": 2}}
        merge_settings(base, {"a": 10, "b": {"d": 3}})
        assert base == base_copy
