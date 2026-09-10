"""Tests for settings loading from .env and environment variables."""
from __future__ import annotations

import os
import tempfile

from app.core.config.settings import _coerce_value, _load_env_file


def test_load_env_file_nonexistent():
    values = _load_env_file("/path/to/nonexistent/.env")
    assert values == {}


def test_load_env_file_skips_comments_and_blanks():
    content = "# comment\n\nKEY=value\n# another\nFOO=bar\n"
    fd, path = tempfile.mkstemp(suffix=".env", text=True)
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        values = _load_env_file(path)
        assert values == {"KEY": "value", "FOO": "bar"}
    finally:
        os.unlink(path)


def test_load_env_file_strips_inline_comment():
    fd, path = tempfile.mkstemp(suffix=".env", text=True)
    try:
        os.write(fd, b"KEY=value # inline comment\n")
        os.close(fd)
        values = _load_env_file(path)
        assert values["KEY"] == "value"
    finally:
        os.unlink(path)


def test_load_env_file_strips_quotes():
    fd, path = tempfile.mkstemp(suffix=".env", text=True)
    try:
        os.write(fd, b"KEY='quoted'\nFOO=\"dquoted\"\n")
        os.close(fd)
        values = _load_env_file(path)
        assert values["KEY"] == "quoted"
        assert values["FOO"] == "dquoted"
    finally:
        os.unlink(path)


class TestCoerceValue:
    def test_bool_true_values(self):
        for v in ("1", "true", "True", "YES", "on"):
            assert _coerce_value(v, bool) is True

    def test_bool_false_values(self):
        for v in ("0", "false", "no", "off"):
            assert _coerce_value(v, bool) is False

    def test_int_values(self):
        assert _coerce_value("42", int) == 42
        assert _coerce_value("0", int) == 0

    def test_str_values(self):
        assert _coerce_value("hello", str) == "hello"
