"""Shared HTML parser selection helpers."""

from __future__ import annotations

import importlib.util

_PARSER: str = "lxml" if importlib.util.find_spec("lxml") is not None else "html.parser"


def choose_parser() -> str:
    """Prefer lxml; html.parser is only a compatibility fallback for minimal installs."""
    return _PARSER
