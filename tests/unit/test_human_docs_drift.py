from __future__ import annotations

import re
import shlex
import subprocess
import warnings
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
AI_ONBOARDING_DIR = REPO_ROOT / "docs" / "ai-onboarding"
HARD_CONSTRAINTS_PATH = AI_ONBOARDING_DIR / "hard-constraints.md"
PROVIDER_DEVELOPMENT_PATH = REPO_ROOT / "docs" / "provider-development.md"
ADDING_PROVIDER_PATH = REPO_ROOT / "docs" / "adding-a-provider.md"
HUMAN_DOC_PATHS = (PROVIDER_DEVELOPMENT_PATH, ADDING_PROVIDER_PATH)

FENCE_PATTERN = re.compile(r"```(?P<lang>[^\n`]*)\n(?P<body>.*?)```", re.DOTALL)
PROVIDER_API_CALL_PATTERN = re.compile(
    r"\b(?P<name>register_provider_bundle|ProviderBundle|ProviderSpec)\s*\("
)
PROHIBITION_PATTERN = re.compile(r"禁止使用|不要使用|do not use", re.IGNORECASE)
API_TOKEN_PATTERN = re.compile(
    r"`(?P<backtick>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)`"
    r"|\b(?P<call>[A-Za-z_][A-Za-z0-9_]*)\s*\("
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fenced_code_blocks(markdown: str) -> list[str]:
    return [match.group("body") for match in FENCE_PATTERN.finditer(markdown)]


def _src_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(SRC_DIR.rglob("*.py"))
    )


def _api_tokens(markdown: str) -> set[str]:
    tokens: set[str] = set()
    for match in API_TOKEN_PATTERN.finditer(markdown):
        token = match.group("backtick") or match.group("call")
        if token is None:
            continue
        if "." in token and token.endswith(".py"):
            continue
        if "/" in token or "-" in token:
            continue
        if token in {"None", "True", "False", "TODO", "TBD", "JSON", "YAML"}:
            continue
        if token[0].islower() and not token.endswith("_bundle"):
            continue
        tokens.add(token)
    return tokens


def _human_docs_text() -> str:
    return "\n".join(_read(path) for path in HUMAN_DOC_PATHS)


def _ai_docs_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(AI_ONBOARDING_DIR.glob("*.md"))
    )


def test_provider_development_code_block_api_names_still_exist_in_src() -> None:
    code_blocks = _fenced_code_blocks(_read(PROVIDER_DEVELOPMENT_PATH))
    api_names = {
        match.group("name")
        for block in code_blocks
        for match in PROVIDER_API_CALL_PATTERN.finditer(block)
    }

    assert api_names == {"register_provider_bundle", "ProviderBundle", "ProviderSpec"}

    src_text = _src_text()
    for api_name in sorted(api_names):
        assert re.search(rf"\b{re.escape(api_name)}\b", src_text), (
            f"{api_name} appears in {PROVIDER_DEVELOPMENT_PATH.relative_to(REPO_ROOT)} "
            "code blocks but no longer exists under src/"
        )


def _grep_commands_from_hard_constraints() -> list[list[str]]:
    commands: list[list[str]] = []
    for block in _fenced_code_blocks(_read(HARD_CONSTRAINTS_PATH)):
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            tokens = shlex.split(line)
            if tokens[:2] == ["git", "grep"]:
                commands.append(tokens)
    return commands


def _grep_pattern_and_paths(tokens: list[str]) -> tuple[str, list[str]]:
    assert "--" in tokens, f"grep command must include explicit path separator: {' '.join(tokens)}"
    separator = tokens.index("--")
    path_tokens = tokens[separator + 1 :]
    assert path_tokens, f"grep command must include at least one path: {' '.join(tokens)}"

    pattern: str | None = None
    index = 2
    while index < separator:
        token = tokens[index]
        if token in {"-e", "--regexp"}:
            index += 1
            assert index < separator, f"grep option {token} requires a pattern"
            pattern = tokens[index]
        elif token.startswith("-"):
            pass
        else:
            pattern = token
        index += 1

    assert pattern is not None, f"grep command must include a pattern: {' '.join(tokens)}"
    return pattern, path_tokens


def test_hard_constraints_grep_commands_are_parseable_and_paths_exist() -> None:
    commands = _grep_commands_from_hard_constraints()
    assert commands, f"{HARD_CONSTRAINTS_PATH.relative_to(REPO_ROOT)} must list grep checks"

    for tokens in commands:
        pattern, path_tokens = _grep_pattern_and_paths(tokens)
        re.compile(pattern)
        for path_token in path_tokens:
            path = REPO_ROOT / path_token
            assert path.exists(), (
                f"{HARD_CONSTRAINTS_PATH.relative_to(REPO_ROOT)} grep path does not exist: "
                f"{path_token}"
            )

        result = subprocess.run(
            tokens,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert result.returncode in {0, 1}, (
            f"grep command is not executable: {' '.join(tokens)}\n{result.stderr}"
        )


def test_human_only_api_drift_warns_but_ai_prohibition_conflicts_fail() -> None:
    human_text = _human_docs_text()
    ai_text = _ai_docs_text()
    human_apis = _api_tokens(human_text)
    ai_apis = _api_tokens(ai_text)

    missing_from_ai = sorted(human_apis - ai_apis)
    if missing_from_ai:
        warnings.warn(
            "Human reference docs mention APIs not present in docs/ai-onboarding/: "
            + ", ".join(missing_from_ai),
            UserWarning,
            stacklevel=1,
        )

    conflicts: list[str] = []
    for line in human_text.splitlines():
        if not PROHIBITION_PATTERN.search(line):
            continue
        prohibited_apis = _api_tokens(line)
        conflicts.extend(sorted(prohibited_apis & ai_apis))

    assert not conflicts, (
        "AI onboarding docs mention APIs that human reference docs mark as prohibited: "
        + ", ".join(sorted(set(conflicts)))
    )
