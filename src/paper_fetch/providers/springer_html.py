"""Public Springer Nature HTML extraction facade."""

from __future__ import annotations

from typing import Any

from . import _springer_html as _impl

clean_markdown = _impl.clean_markdown
decode_html = _impl.decode_html
download_figure_assets = _impl.download_figure_assets
extract_asset_html_scopes = _impl.extract_asset_html_scopes
extract_authors = _impl.extract_authors
extract_full_size_figure_image_url = _impl.extract_full_size_figure_image_url
extract_html_assets = _impl.extract_html_assets
extract_scoped_html_assets = _impl.extract_scoped_html_assets
extract_source_data_html_scope = _impl.extract_source_data_html_scope
merge_html_metadata = _impl.merge_html_metadata
normalize_display_authors = _impl.normalize_display_authors
parse_html_metadata = _impl.parse_html_metadata

_DEFAULT_EXTRACT_ARTICLE_MARKDOWN = _impl.extract_article_markdown
extract_article_markdown = _DEFAULT_EXTRACT_ARTICLE_MARKDOWN


def extract_html_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
    active_extract_article_markdown = globals()["extract_article_markdown"]
    if active_extract_article_markdown is _DEFAULT_EXTRACT_ARTICLE_MARKDOWN:
        return _impl.extract_html_payload(*args, **kwargs)

    original_extract_article_markdown = _impl.extract_article_markdown
    _impl.extract_article_markdown = active_extract_article_markdown
    try:
        return _impl.extract_html_payload(*args, **kwargs)
    finally:
        _impl.extract_article_markdown = original_extract_article_markdown

__all__ = [
    "clean_markdown",
    "decode_html",
    "download_figure_assets",
    "extract_article_markdown",
    "extract_asset_html_scopes",
    "extract_authors",
    "extract_full_size_figure_image_url",
    "extract_html_assets",
    "extract_html_payload",
    "extract_scoped_html_assets",
    "extract_source_data_html_scope",
    "merge_html_metadata",
    "normalize_display_authors",
    "parse_html_metadata",
]
