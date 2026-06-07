"""Elsevier DOI/PII identifier helpers."""

from __future__ import annotations

import re
import urllib.parse

ELSEVIER_PII_PATH_TOKENS = frozenset({"pii"})


def normalize_elsevier_pii(value: str | None) -> str | None:
    if not value:
        return None
    pii = re.sub(r"[^A-Za-z0-9]", "", value.strip())
    return pii or None


def extract_elsevier_pii_from_url(url: str | None) -> str | None:
    if not url:
        return None
    normalized_url = str(url).strip()
    if not normalized_url:
        return None
    parsed = urllib.parse.urlparse(normalized_url)
    path_segments = [
        urllib.parse.unquote(segment).strip()
        for segment in parsed.path.split("/")
        if urllib.parse.unquote(segment).strip()
    ]
    for index, segment in enumerate(path_segments[:-1]):
        if segment.lower() not in ELSEVIER_PII_PATH_TOKENS:
            continue
        pii = normalize_elsevier_pii(path_segments[index + 1])
        if pii:
            return pii
    return None
