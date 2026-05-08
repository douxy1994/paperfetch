# ruff: noqa: F401
from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from paper_fetch.mcp.cache_index import (
    LOCK_DIRNAME,
    cache_lock_dir,
    cache_scope_id,
    scoped_cache_index_resource_uri,
    scoped_cached_resource_uri_prefix,
)
from paper_fetch.mcp import server as mcp_server
from paper_fetch.mcp import tools as mcp_tools
from paper_fetch.mcp.fetch_cache import FetchCache
from paper_fetch.mcp.server import build_server
from paper_fetch.models import (
    ArticleModel,
    Asset,
    EXTRACTION_REVISION,
    FetchEnvelope,
    Metadata,
    Quality,
    QUALITY_FLAG_CACHED_WITH_CURRENT_REVISION,
    RenderOptions,
    Section,
    TokenEstimateBreakdown,
)
from paper_fetch.providers.base import ProviderFailure
from paper_fetch.resolve.query import ResolvedQuery
from paper_fetch.service import FetchStrategy, HasFulltextProbeResult, PaperFetchFailure
from paper_fetch.utils import sanitize_filename
from tests.golden_criteria import golden_criteria_scenario_asset


def sample_article() -> ArticleModel:
    return ArticleModel(
        doi="10.1000/example",
        source="elsevier_xml",
        metadata=Metadata(
            title="Example Article",
            authors=["Alice Example"],
            abstract="Example abstract",
            journal="Example Journal",
            published="2026-01-01",
        ),
        sections=[Section(heading="Introduction", level=2, kind="body", text="Example body.")],
        references=[],
        assets=[],
        quality=Quality(
            has_fulltext=True,
            token_estimate=128,
            warnings=["example warning"],
            source_trail=["source:ok"],
            token_estimate_breakdown=TokenEstimateBreakdown(abstract=32, body=96, refs=24),
        ),
    )


def sample_envelope(*, modes: set[str], doi: str = "10.1000/example") -> FetchEnvelope:
    article = sample_article()
    article.doi = doi
    article.metadata.title = "Example Article" if doi == "10.1000/example" else f"Article for {doi}"
    return FetchEnvelope(
        doi=doi,
        source="elsevier_xml",
        has_fulltext=True,
        warnings=["example warning"],
        source_trail=["source:ok"],
        token_estimate=article.quality.token_estimate,
        token_estimate_breakdown=article.quality.token_estimate_breakdown,
        quality=article.quality,
        article=article if "article" in modes else None,
        markdown="# Example Article\n\nExample body.\n" if "markdown" in modes else None,
        metadata=article.metadata if "metadata" in modes else None,
    )


def sample_resolved_query(query: str) -> ResolvedQuery:
    return ResolvedQuery(
        query=query,
        query_kind="doi",
        doi=query if query.startswith("10.") else "10.1000/example",
        landing_url="https://example.test/article",
        provider_hint="crossref",
        confidence=1.0,
        candidates=[],
        title="Example Article",
    )


def sample_probe_result(
    query: str,
    *,
    doi: str | None = None,
    title: str | None = None,
    state: str = "likely_yes",
    evidence: list[str] | None = None,
    warnings: list[str] | None = None,
) -> HasFulltextProbeResult:
    return HasFulltextProbeResult(
        query=query,
        doi=doi or (query if query.startswith("10.") else "10.1000/example"),
        title=title or f"Article for {query}",
        state=state,
        evidence=list(evidence or ["crossref_fulltext_link"]),
        warnings=list(warnings or []),
    )


def create_cached_downloads(download_dir: Path, doi: str) -> None:
    base = sanitize_filename(doi)
    download_dir.mkdir(parents=True, exist_ok=True)
    (download_dir / f"{base}.xml").write_text("<article />", encoding="utf-8")
    (download_dir / f"{base}.md").write_text("# Cached Markdown\n", encoding="utf-8")
    asset_dir = download_dir / f"{base}_assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "figure-1.png").write_bytes(b"\x89PNG\r\n")


def create_cached_fetch_envelope(
    download_dir: Path,
    doi: str,
    *,
    modes: list[str] | None = None,
    extraction_revision: int = EXTRACTION_REVISION,
) -> None:
    request = {
        "modes": list(modes or ["article", "markdown"]),
        "strategy": {
            "allow_metadata_only_fallback": True,
            "preferred_providers": None,
            "asset_profile": None,
        },
        "include_refs": None,
        "max_tokens": "full_text",
    }
    payload = sample_envelope(modes=set(request["modes"]), doi=doi).to_dict()
    path = mcp_tools._fetch_envelope_cache_path(download_dir, doi)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": mcp_tools._FETCH_ENVELOPE_CACHE_VERSION,
                "extraction_revision": extraction_revision,
                "request": request,
                "payload": payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    mcp_tools.refresh_cache_index_for_doi(download_dir, doi)


def write_binary(path: Path, size: int = 8) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n" + (b"x" * max(0, size - 6)))


def fake_service_fetch_with_cached_downloads(query, *, modes=None, context=None, **kwargs):
    download_dir = context.download_dir if context is not None else None
    if download_dir is not None:
        create_cached_downloads(download_dir, query)
    return sample_envelope(modes=set(modes or []), doi=query)


async def wait_for_threading_event(event: threading.Event, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if event.is_set():
            return True
        await asyncio.sleep(0.01)
    return event.is_set()


class FakeSession:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []
        self.resource_list_changed_calls = 0

    async def send_log_message(self, *, level, data, logger=None, related_request_id=None) -> None:
        self.messages.append(
            {
                "level": level,
                "data": data,
                "logger": logger,
                "related_request_id": related_request_id,
            }
        )

    async def send_resource_list_changed(self) -> None:
        self.resource_list_changed_calls += 1


class FakeContext:
    def __init__(self) -> None:
        self.progress: list[tuple[float, float | None, str | None]] = []
        self.session = FakeSession()
        self.request_id = "unit-request"

    async def report_progress(self, progress: float, total: float | None = None, message: str | None = None) -> None:
        self.progress.append((progress, total, message))

__all__ = [name for name in globals() if not name.startswith("__")]
