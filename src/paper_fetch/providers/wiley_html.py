"""Public Wiley HTML extraction facade."""

from __future__ import annotations

from ._wiley_html import (
    BASE_HOSTS,
    CROSSREF_PDF_POSITION,
    HOSTS,
    HTML_PATH_TEMPLATES,
    PDF_PATH_TEMPLATES,
    blocking_fallback_signals,
    extract_authors,
    extract_scoped_html_assets,
)

__all__ = [
    "BASE_HOSTS",
    "CROSSREF_PDF_POSITION",
    "HOSTS",
    "HTML_PATH_TEMPLATES",
    "PDF_PATH_TEMPLATES",
    "blocking_fallback_signals",
    "extract_authors",
    "extract_scoped_html_assets",
]
