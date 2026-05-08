"""Public Science/PNAS browser-workflow routing facade."""

from __future__ import annotations

from ._science_pnas_profiles import (
    build_html_candidates,
    build_pdf_candidates,
    extract_pdf_url_from_crossref,
    preferred_html_candidate_from_landing_page,
    site_rule_for_publisher,
)

__all__ = [
    "build_html_candidates",
    "build_pdf_candidates",
    "extract_pdf_url_from_crossref",
    "preferred_html_candidate_from_landing_page",
    "site_rule_for_publisher",
]
