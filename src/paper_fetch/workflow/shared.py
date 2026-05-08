"""Shared helpers reused across workflow stages."""

from __future__ import annotations

from ..providers.base import ProviderFailure
from ..tracing import provider_stage_marker


def source_trail_for_failure(stage: str, provider_name: str, failure: ProviderFailure) -> str:
    if failure.code == "not_configured":
        suffix = "not_configured"
    elif failure.code == "rate_limited":
        suffix = "rate_limited"
    else:
        suffix = "fail"
    return provider_stage_marker(stage, provider_name, suffix)
