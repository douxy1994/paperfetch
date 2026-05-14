"""Provider availability rule ownership for HTML full-text checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class AvailabilityContainerRules:
    candidate_selectors: tuple[str, ...] = ()
    remove_selectors: tuple[str, ...] = ()
    drop_keywords: tuple[str, ...] = ()
    drop_texts: tuple[str, ...] = ()
    drop_tags: tuple[str, ...] = ()
    browser_workflow_drop_tags: tuple[str, ...] = ()
    browser_workflow_short_text_patterns: tuple[str, ...] = ()

    def drop_tags_for(self, *, browser_workflow: bool = False) -> tuple[str, ...]:
        return self.browser_workflow_drop_tags if browser_workflow else self.drop_tags

    def short_text_patterns_for(
        self, *, browser_workflow: bool = False
    ) -> tuple[str, ...]:
        return (
            self.browser_workflow_short_text_patterns if browser_workflow else ()
        )


@dataclass(frozen=True)
class AvailabilityPolicy:
    """Provider-owned availability rules kept separate from cleanup policy."""

    name: str
    container_rules: AvailabilityContainerRules = field(
        default_factory=AvailabilityContainerRules
    )
    site_rule_overrides: Mapping[str, Any] = field(default_factory=dict)
    positive_signals: Callable[[str], tuple[list[str], list[str], list[str]]] | None = (
        None
    )
    blocking_fallback_signals: Callable[[str], list[str]] | None = None
    availability_overrides: Callable[..., tuple[list[str], list[str], list[str]]] | None = (
        None
    )
    access_block_text_tokens: tuple[str, ...] = ()
