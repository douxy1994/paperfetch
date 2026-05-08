"""Public Science HTML extraction facade."""

from __future__ import annotations

from ._science_html import (
    BASE_HOSTS,
    CROSSREF_PDF_POSITION,
    HOSTS,
    HTML_PATH_TEMPLATES,
    PDF_PATH_TEMPLATES,
    blocking_fallback_signals,
    extract_authors,
)

__all__ = [
    "BASE_HOSTS",
    "CROSSREF_PDF_POSITION",
    "HOSTS",
    "HTML_PATH_TEMPLATES",
    "PDF_PATH_TEMPLATES",
    "blocking_fallback_signals",
    "extract_authors",
]
