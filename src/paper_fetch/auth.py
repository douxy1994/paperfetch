"""Interactive authentication helpers for publisher browser workflows."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Mapping

from .config import (
    AMS_STORAGE_STATE_JSON_ENV_VAR,
    BROWSER_USER_AGENT_ENV_VAR,
    CLOAKBROWSER_HEADLESS_ENV_VAR,
    CLOAKBROWSER_TIMEOUT_MS_ENV_VAR,
    DEFAULT_USER_ENV_FILE,
    build_runtime_env,
    resolve_user_data_dir,
)
from .providers import _cloakbrowser
from .providers.base import ProviderFailure
from .providers.browser_workflow.fetchers.readiness import wait_for_atypon_body_dom_ready
from .reason_codes import ERROR
from .runtime_browser import browser_context_options, cloakbrowser_binary_path_env
from .utils import normalize_text


AMS_AUTH_DOI = "10.1175/mwr-d-10-05037.1"
AMS_AUTH_URL = "https://journals.ametsoc.org/doi/10.1175/MWR-D-10-05037.1"
DEFAULT_AUTH_WAIT_SECONDS = 300


@dataclass(frozen=True)
class AuthResult:
    provider: str
    storage_state_path: Path
    env_file_path: Path | None
    env_written: bool
    verified: bool
    final_url: str | None
    title: str | None


def default_ams_storage_state_path(env: Mapping[str, str] | None = None) -> Path:
    return resolve_user_data_dir(env) / "auth" / "ams" / "storage-state.json"


def _dotenv_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def upsert_env_file(path: Path, values: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(values)
    output_lines: list[str] = []
    assignment_pattern = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
    for line in existing_lines:
        match = assignment_pattern.match(line.strip())
        if match and match.group(1) in pending:
            key = match.group(1)
            output_lines.append(f"{key}={_dotenv_quote(pending.pop(key))}")
        else:
            output_lines.append(line)
    for key, value in pending.items():
        output_lines.append(f"{key}={_dotenv_quote(value)}")
    path.write_text("\n".join(output_lines).rstrip() + "\n", encoding="utf-8")


def authenticate_ams(
    *,
    state_json: Path | None = None,
    env_file: Path | None = None,
    write_env: bool = True,
    timeout_ms: int | None = None,
    wait_seconds: int = DEFAULT_AUTH_WAIT_SECONDS,
    browser_user_agent: str | None = None,
    target_url: str = AMS_AUTH_URL,
) -> AuthResult:
    runtime_env = build_runtime_env()
    configured_state_json = normalize_text(runtime_env.get(AMS_STORAGE_STATE_JSON_ENV_VAR))
    storage_state_path = (
        state_json
        or (Path(configured_state_json) if configured_state_json else None)
        or default_ams_storage_state_path(runtime_env)
    ).expanduser().resolve()
    runtime_env[AMS_STORAGE_STATE_JSON_ENV_VAR] = str(storage_state_path)
    runtime_env[CLOAKBROWSER_HEADLESS_ENV_VAR] = "false"
    if timeout_ms is not None:
        runtime_env[CLOAKBROWSER_TIMEOUT_MS_ENV_VAR] = str(timeout_ms)
    if browser_user_agent:
        runtime_env[BROWSER_USER_AGENT_ENV_VAR] = browser_user_agent

    runtime = _cloakbrowser.load_runtime_config(
        runtime_env,
        provider="ams",
        doi=AMS_AUTH_DOI,
        require_storage_state=False,
    )
    _cloakbrowser.ensure_runtime_ready(runtime)
    cloakbrowser = _cloakbrowser._import_cloakbrowser()

    browser = None
    context = None
    page = None
    verified = False
    final_url: str | None = None
    title: str | None = None
    try:
        with cloakbrowser_binary_path_env(runtime.binary_path):
            browser = cloakbrowser.launch(headless=False, locale="en-US")
        context = browser.new_context(
            **browser_context_options(
                user_agent=normalize_text(runtime.user_agent),
                **_cloakbrowser._storage_context_options(runtime),
            )
        )
        page = context.new_page()
        page.goto(target_url, wait_until="domcontentloaded", timeout=runtime.timeout_ms)
        readiness = wait_for_atypon_body_dom_ready(
            page,
            "ams",
            timeout_seconds=max(0, int(wait_seconds)),
        )
        verified = bool(readiness.ready)
        final_url = normalize_text(str(getattr(page, "url", "") or "")) or None
        try:
            title = normalize_text(str(page.title() or "")) or None
        except Exception:
            title = None
        _cloakbrowser._save_storage_state(context, runtime)
    except ProviderFailure:
        raise
    except Exception as exc:
        message = normalize_text(str(exc)) or exc.__class__.__name__
        raise ProviderFailure(ERROR, f"AMS authentication failed: {message}") from exc
    finally:
        for value in (page, context, browser):
            try:
                if value is not None:
                    value.close()
            except Exception:
                pass

    if not storage_state_path.is_file():
        raise ProviderFailure(
            ERROR,
            f"AMS authentication did not produce a storage-state JSON: {storage_state_path}",
        )

    env_file_path = env_file.expanduser() if env_file is not None else DEFAULT_USER_ENV_FILE
    env_written = False
    if write_env:
        try:
            upsert_env_file(
                env_file_path,
                {AMS_STORAGE_STATE_JSON_ENV_VAR: str(storage_state_path)},
            )
        except OSError as exc:
            raise ProviderFailure(
                ERROR,
                f"Failed to update AMS environment file {env_file_path}: {exc}",
            ) from exc
        env_written = True

    return AuthResult(
        provider="ams",
        storage_state_path=storage_state_path,
        env_file_path=env_file_path if write_env else None,
        env_written=env_written,
        verified=verified,
        final_url=final_url,
        title=title,
    )
