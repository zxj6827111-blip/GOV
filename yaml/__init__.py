"""Minimal YAML loader for offline testing environments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

__all__ = ["safe_load", "YAMLError"]


class YAMLError(RuntimeError):
    """Raised when the lightweight YAML parser encounters invalid input."""


@dataclass
class _Parser:
    lines: list[str]
    index: int = 0

    def parse(self) -> Any:
        self._skip_empty()
        if self.index >= len(self.lines):
            return None
        indent = self._current_indent()
        if self._current_stripped().startswith("- "):
            return self._parse_list(indent)
        return self._parse_map(indent)

    def _skip_empty(self) -> None:
        while self.index < len(self.lines) and not self.lines[self.index].strip():
            self.index += 1

    def _current_indent(self) -> int:
        line = self.lines[self.index]
        return len(line) - len(line.lstrip(" "))

    def _current_stripped(self) -> str:
        return self.lines[self.index].strip()

    def _parse_map(self, indent: int) -> dict[str, Any]:
        mapping: dict[str, Any] = {}
        while self.index < len(self.lines):
            line = self.lines[self.index]
            if not line.strip():
                self.index += 1
                continue
            current_indent = self._current_indent()
            if current_indent < indent:
                break
            if current_indent > indent:
                raise YAMLError(f"Unexpected indentation at line {self.index + 1}")
            stripped = self._current_stripped()
            if stripped.startswith("- "):
                break
            if ":" not in stripped:
                raise YAMLError(f"Expected key-value pair at line {self.index + 1}")
            key, _, remainder = stripped.partition(":")
            key = key.strip()
            remainder = remainder.strip()
            self.index += 1
            if not remainder:
                value = self._parse_nested(indent)
                mapping[key] = value
            else:
                mapping[key] = self._parse_scalar(remainder)
        return mapping

    def _parse_list(self, indent: int) -> list[Any]:
        items: list[Any] = []
        while self.index < len(self.lines):
            line = self.lines[self.index]
            if not line.strip():
                self.index += 1
                continue
            current_indent = self._current_indent()
            if current_indent < indent:
                break
            stripped = self._current_stripped()
            if not stripped.startswith("- "):
                break
            content = stripped[2:].strip()
            self.index += 1
            if content and ":" in content:
                item = self._parse_inline_mapping(content, indent)
            elif content:
                item = self._parse_scalar(content)
            else:
                item = self._parse_nested(indent)
            items.append(item)
        return items

    def _parse_inline_mapping(self, content: str, indent: int) -> dict[str, Any]:
        item: dict[str, Any] = {}
        key, _, remainder = content.partition(":")
        key = key.strip()
        remainder = remainder.strip()
        if remainder:
            item[key] = self._parse_scalar(remainder)
        else:
            item[key] = self._parse_nested(indent + 2)
        while True:
            self._skip_empty()
            if self.index >= len(self.lines):
                break
            next_line = self.lines[self.index]
            next_indent = len(next_line) - len(next_line.lstrip(" "))
            stripped = next_line.strip()
            if next_indent <= indent:
                break
            if next_indent == indent + 2 and not stripped.startswith("- "):
                self.index += 1
                if ":" not in stripped:
                    raise YAMLError(f"Expected key-value pair at line {self.index}")
                sub_key, _, sub_remainder = stripped.partition(":")
                sub_key = sub_key.strip()
                sub_remainder = sub_remainder.strip()
                if sub_remainder:
                    item[sub_key] = self._parse_scalar(sub_remainder)
                else:
                    item[sub_key] = self._parse_nested(indent + 2)
            else:
                if not item:
                    raise YAMLError("Inline mapping must contain at least one key")
                last_key = next(reversed(item))
                if stripped.startswith("- "):
                    item[last_key] = self._parse_list(next_indent)
                else:
                    item[last_key] = self._parse_map(next_indent)
                break
        return item

    def _parse_nested(self, base_indent: int) -> Any:
        self._skip_empty()
        if self.index >= len(self.lines):
            return None
        current_indent = self._current_indent()
        if current_indent <= base_indent:
            return None
        if self._current_stripped().startswith("- "):
            return self._parse_list(current_indent)
        return self._parse_map(current_indent)

    def _parse_scalar(self, token: str) -> Any:
        if token.startswith("\"") and token.endswith("\""):
            return token[1:-1]
        if token.startswith("'") and token.endswith("'"):
            return token[1:-1]
        if token.lower() in {"null", "~"}:
            return None
        if token.lower() == "true":
            return True
        if token.lower() == "false":
            return False
        if token.startswith("[") and token.endswith("]"):
            try:
                return json.loads(token)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise YAMLError("Invalid inline list") from exc
        if token.isdigit():
            return int(token)
        try:
            return float(token)
        except ValueError:
            return token


def safe_load(stream: Any) -> Any:
    """Parse the given YAML stream using a minimal feature subset."""

    if hasattr(stream, "read"):
        text = stream.read()
    else:
        text = stream
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    if not isinstance(text, str):
        raise TypeError("safe_load expects a string, bytes, or file-like object")
    lines = [line.rstrip("\n") for line in text.splitlines()]
    parser = _Parser(lines)
    return parser.parse()
