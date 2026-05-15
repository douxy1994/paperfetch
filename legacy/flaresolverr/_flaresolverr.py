"""FlareSolverr helpers for browser-workflow provider access."""

from __future__ import annotations

import atexit
import base64
import json
import logging
import platform
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import urllib3

from paper_fetch.config import (
    FLARESOLVERR_ENV_FILE_ENV_VAR,
    FLARESOLVERR_KEEP_SESSION_ENV_VAR,
    FLARESOLVERR_SOURCE_DIR_ENV_VAR,
    FLARESOLVERR_URL_ENV_VAR,
    env_flag_enabled,
    load_env_file,
    resolve_user_data_dir,
)
from paper_fetch.extraction.html.signals import detect_html_block, summarize_html
from paper_fetch.providers.browser_runtime.seed import (
    CLOUDFLARE_COOKIE_NAMES,
    _CLOUDFLARE_COOKIE_PREFIXES,
    merge_browser_context_seeds,
    normalize_browser_cookie_for_playwright,
    normalize_browser_cookies_for_playwright,
    parse_optional_int,
)
from paper_fetch.providers.browser_runtime.types import (
    BrowserFetchedHtml as FetchedPublisherHtml,
    BrowserRuntimeFailure as FlareSolverrFailure,
)
from paper_fetch.quality.html_availability import choose_parser, extract_page_title
from paper_fetch.quality.html_signals import looks_like_abstract_redirect
from paper_fetch.quality.reason_codes import CLOUDFLARE_CHALLENGE, REDIRECTED_TO_ABSTRACT
from paper_fetch.utils import normalize_text, provider_display_name, sanitize_filename
from paper_fetch.providers.base import (
    ProviderFailure,
    ProviderStatusResult,
    build_provider_status_check,
    provider_status_check_from_failure,
)
from paper_fetch.reason_codes import ERROR, NOT_CONFIGURED, OK, READY

from bs4 import BeautifulSoup

DEFAULT_VENDOR_FLARESOLVERR_DIR = Path(__file__).resolve().parent / "vendor"
DEFAULT_FLARESOLVERR_URL = "http://127.0.0.1:8191/v1"
DEFAULT_FLARESOLVERR_WAIT_SECONDS = 8
DEFAULT_FLARESOLVERR_WARM_WAIT_SECONDS = 1
DEFAULT_FLARESOLVERR_MAX_TIMEOUT_MS = 120000
FLARESOLVERR_STATUS_PROBE_ID = "probe://flaresolverr/status"

logger = logging.getLogger("paper_fetch.providers.flaresolverr")

_BROWSER_WORKFLOW_PROVIDERS = ("wiley", "science", "pnas", "ams")

_POSIX_FLARESOLVERR_WORKFLOW_FILES = (
    "setup_flaresolverr_source.sh",
    "start_flaresolverr_source.sh",
    "run_flaresolverr_source.sh",
    "stop_flaresolverr_source.sh",
    "flaresolverr_source_common.sh",
)
_WINDOWS_FLARESOLVERR_WORKFLOW_FILES = (
    "start_flaresolverr_source.ps1",
    "stop_flaresolverr_source.ps1",
    "flaresolverr_source_common.ps1",
)


def resolve_flaresolverr_source_dir(env: Mapping[str, str] | None = None) -> Path:
    configured = str((env or {}).get(FLARESOLVERR_SOURCE_DIR_ENV_VAR, "")).strip()
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_VENDOR_FLARESOLVERR_DIR


def resolve_flaresolverr_env_file(env: Mapping[str, str] | None = None) -> Path | None:
    configured = str((env or {}).get(FLARESOLVERR_ENV_FILE_ENV_VAR, "")).strip()
    if not configured:
        return None
    return Path(configured).expanduser()


def resolve_flaresolverr_url(env: Mapping[str, str] | None = None) -> str:
    return str((env or {}).get(FLARESOLVERR_URL_ENV_VAR, "")).strip() or DEFAULT_FLARESOLVERR_URL


@dataclass
class FlareSolverrSessionState:
    session_id: str
    created_at: float
    last_used_at: float
    warm: bool = False


_SESSION_REGISTRY: dict[tuple[str, str], FlareSolverrSessionState] = {}
_SESSION_LOCKS: dict[tuple[str, str], threading.RLock] = {}
_SESSION_REGISTRY_LOCK = threading.RLock()


@dataclass(frozen=True)
class FlareSolverrRuntimeConfig:
    provider: str
    doi: str
    url: str
    env_file: Path
    source_dir: Path
    artifact_dir: Path
    headless: bool
    keep_session: bool = False
    required_files: tuple[str, ...] = field(
        default_factory=lambda: _default_flaresolverr_workflow_files()
    )


def _browser_workflow_label(provider: str) -> str:
    normalized = normalize_text(provider).lower()
    if normalized in _BROWSER_WORKFLOW_PROVIDERS:
        return f"{provider_display_name(normalized)} browser workflow"
    return f"{normalized or provider} browser workflow"


def _default_flaresolverr_workflow_files() -> tuple[str, ...]:
    if platform.system().lower() == "windows":
        return _WINDOWS_FLARESOLVERR_WORKFLOW_FILES
    return _POSIX_FLARESOLVERR_WORKFLOW_FILES


def load_runtime_config(env: Mapping[str, str], *, provider: str, doi: str) -> FlareSolverrRuntimeConfig:
    source_dir = resolve_flaresolverr_source_dir(env)
    env_file = resolve_flaresolverr_env_file(env)
    workflow_label = _browser_workflow_label(provider)
    if env_file is None:
        raise ProviderFailure(
            NOT_CONFIGURED,
            (
                f"{workflow_label} requires FLARESOLVERR_ENV_FILE pointing at a repo-local vendor/flaresolverr preset. "
                "Start the service with ./scripts/flaresolverr-up <preset> first."
            ),
            missing_env=["FLARESOLVERR_ENV_FILE"],
        )
    if not env_file.exists():
        raise ProviderFailure(
            NOT_CONFIGURED,
            f"Configured FLARESOLVERR_ENV_FILE does not exist: {env_file}",
            missing_env=["FLARESOLVERR_ENV_FILE"],
        )

    env_values = load_env_file(env_file)
    headless = normalize_text(env_values.get("HEADLESS", "true")).lower() != "false"
    artifact_dir = resolve_user_data_dir(env) / "publisher-browser-artifacts" / provider / sanitize_filename(doi)
    return FlareSolverrRuntimeConfig(
        provider=provider,
        doi=doi,
        url=resolve_flaresolverr_url(env),
        env_file=env_file,
        source_dir=source_dir,
        artifact_dir=artifact_dir,
        headless=headless,
        keep_session=env_flag_enabled(env, FLARESOLVERR_KEEP_SESSION_ENV_VAR),
    )


def ensure_runtime_ready(config: FlareSolverrRuntimeConfig) -> None:
    check_local_workflow(config)
    try:
        health_check(config.url)
    except ProviderFailure as exc:
        workflow_label = _browser_workflow_label(config.provider)
        raise ProviderFailure(
            NOT_CONFIGURED,
            (
                f"{workflow_label} requires a running local FlareSolverr service. "
                f"{exc.message} Start it with ./scripts/flaresolverr-up <preset>."
            ),
        ) from exc


def check_local_workflow(config: FlareSolverrRuntimeConfig) -> None:
    workflow_label = _browser_workflow_label(config.provider)
    if not config.source_dir.exists():
        raise ProviderFailure(
            NOT_CONFIGURED,
            (
                f"{workflow_label} is repo-local only. Missing vendor/flaresolverr under the current checkout: "
                f"{config.source_dir}"
            ),
        )
    missing_files = [name for name in config.required_files if not (config.source_dir / name).exists()]
    if missing_files:
        raise ProviderFailure(
            NOT_CONFIGURED,
            (
                f"{workflow_label} requires the repo-local vendor/flaresolverr workflow. "
                f"Missing files: {', '.join(missing_files)}"
            ),
        )


def health_check(url: str) -> None:
    try:
        payload = post_to_flaresolverr(url, {"cmd": "sessions.list"}, timeout_seconds=10.0)
    except FlareSolverrFailure as exc:
        raise ProviderFailure(NOT_CONFIGURED, f"Health check failed for {url}: {exc.message}.") from exc
    if normalize_text(str(payload.get("status") or "")).lower() not in {"", "ok"}:
        raise ProviderFailure(
            NOT_CONFIGURED,
            f"Health check returned status={payload.get('status')!r} message={payload.get('message')!r}.",
        )


def _runtime_probe_details(env: Mapping[str, str]) -> dict[str, Any]:
    env_file = resolve_flaresolverr_env_file(env)
    source_dir = resolve_flaresolverr_source_dir(env)
    details: dict[str, Any] = {
        "url": resolve_flaresolverr_url(env),
        "env_file": str(env_file) if env_file is not None else None,
        "source_dir": str(source_dir),
        "headless": None,
    }
    if env_file is not None and env_file.exists():
        env_values = load_env_file(env_file)
        details["headless"] = normalize_text(env_values.get("HEADLESS", "true")).lower() != "false"
    return details


def _skipped_status_check(name: str, message: str, *, details: Mapping[str, Any]) -> Any:
    return build_provider_status_check(
        name,
        NOT_CONFIGURED,
        message,
        details=details,
    )


def probe_runtime_status(
    env: Mapping[str, str],
    *,
    provider: str,
    doi: str = FLARESOLVERR_STATUS_PROBE_ID,
) -> ProviderStatusResult:
    runtime_details = _runtime_probe_details(env)
    checks = []

    config: FlareSolverrRuntimeConfig | None = None
    try:
        config = load_runtime_config(env, provider=provider, doi=doi)
        runtime_details = {
            **runtime_details,
            "env_file": str(config.env_file),
            "source_dir": str(config.source_dir),
            "headless": config.headless,
        }
        checks.append(
            build_provider_status_check(
                "runtime_env",
                OK,
                f"{provider} runtime environment is configured.",
                details=runtime_details,
            )
        )
    except ProviderFailure as exc:
        checks.append(provider_status_check_from_failure("runtime_env", exc, details=runtime_details))
    except Exception as exc:
        checks.append(build_provider_status_check("runtime_env", ERROR, str(exc), details=runtime_details))

    repo_details = {
        "source_dir": runtime_details.get("source_dir"),
        "required_files": list(config.required_files) if config is not None else list(_default_flaresolverr_workflow_files()),
    }
    if config is None:
        checks.append(
            _skipped_status_check(
                "repo_local_workflow",
                "Skipped because runtime_env is not configured.",
                details=repo_details,
            )
        )
        checks.append(
            _skipped_status_check(
                "flaresolverr_health",
                "Skipped because runtime_env is not configured.",
                details={"url": runtime_details.get("url")},
            )
        )
    else:
        workflow_ok = False
        try:
            check_local_workflow(config)
            workflow_ok = True
            checks.append(
                build_provider_status_check(
                    "repo_local_workflow",
                    OK,
                    "Repo-local FlareSolverr workflow files are available.",
                    details={
                        "source_dir": str(config.source_dir),
                        "required_files": list(config.required_files),
                    },
                )
            )
        except ProviderFailure as exc:
            checks.append(
                provider_status_check_from_failure(
                    "repo_local_workflow",
                    exc,
                    details={
                        "source_dir": str(config.source_dir),
                        "required_files": list(config.required_files),
                    },
                )
            )
        except Exception as exc:
            checks.append(
                build_provider_status_check(
                    "repo_local_workflow",
                    ERROR,
                    str(exc),
                    details={
                        "source_dir": str(config.source_dir),
                        "required_files": list(config.required_files),
                    },
                )
            )

        if not workflow_ok:
            checks.append(
                _skipped_status_check(
                    "flaresolverr_health",
                    "Skipped because repo_local_workflow is not ready.",
                    details={"url": config.url},
                )
            )
        else:
            try:
                health_check(config.url)
                checks.append(
                    build_provider_status_check(
                        "flaresolverr_health",
                        OK,
                        "Local FlareSolverr health check passed.",
                        details={"url": config.url},
                    )
                )
            except ProviderFailure as exc:
                checks.append(provider_status_check_from_failure("flaresolverr_health", exc, details={"url": config.url}))
            except Exception as exc:
                checks.append(build_provider_status_check("flaresolverr_health", ERROR, str(exc), details={"url": config.url}))

    missing_env: list[str] = []
    for check in checks:
        for name in check.missing_env:
            if name not in missing_env:
                missing_env.append(name)

    if any(check.status == ERROR for check in checks):
        status = ERROR
    elif all(check.status == OK for check in checks):
        status = READY
    else:
        status = NOT_CONFIGURED

    return ProviderStatusResult(
        provider=provider,
        status=status,
        available=status == READY,
        official_provider=True,
        missing_env=missing_env,
        notes=[],
        checks=list(checks),
    )


def extract_flaresolverr_browser_context_seed(solution: dict[str, Any]) -> dict[str, Any]:
    final_url = solution.get("url") if isinstance(solution.get("url"), str) else None
    return {
        "browser_cookies": normalize_browser_cookies_for_playwright(
            solution.get("cookies") if isinstance(solution.get("cookies"), list) else None,
            fallback_url=final_url,
        ),
        "browser_user_agent": normalize_text(str(solution.get("userAgent") or "")) or None,
        "browser_final_url": final_url,
    }


def warm_browser_context_with_flaresolverr(
    candidate_urls: list[str],
    *,
    publisher: str,
    config: FlareSolverrRuntimeConfig,
    browser_context_seed: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    merged_seed = merge_browser_context_seeds(browser_context_seed)
    if not candidate_urls:
        return merged_seed

    try:
        result = fetch_html_with_flaresolverr(candidate_urls, publisher=publisher, config=config)
    except FlareSolverrFailure as exc:
        return merge_browser_context_seeds(merged_seed, exc.browser_context_seed)
    return merge_browser_context_seeds(merged_seed, result.browser_context_seed)


def redact_flaresolverr_response_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted_payload = json.loads(json.dumps(payload, ensure_ascii=False))
    solution = redacted_payload.get("solution")
    if not isinstance(solution, dict):
        return redacted_payload
    cookies = solution.get("cookies")
    if not isinstance(cookies, list):
        return redacted_payload

    redacted_cookies: list[dict[str, Any]] = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        redacted_cookie = dict(cookie)
        if "value" in redacted_cookie:
            redacted_cookie["value"] = "[redacted]"
        redacted_cookies.append(redacted_cookie)
    solution["cookies"] = redacted_cookies
    return redacted_payload


def save_flaresolverr_failure_artifacts(
    artifact_dir: Path,
    *,
    html: str | None = None,
    screenshot_b64: str | None = None,
    response_payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths: dict[str, str] = {}

    if html:
        html_path = artifact_dir / "html.failure.html"
        html_path.write_text(html, encoding="utf-8")
        artifact_paths["html_path"] = str(html_path)

    if screenshot_b64:
        screenshot_path = artifact_dir / "html.failure.png"
        try:
            screenshot_path.write_bytes(decode_base64_blob(screenshot_b64))
            artifact_paths["screenshot_path"] = str(screenshot_path)
        except Exception:
            pass

    if response_payload is not None:
        response_path = artifact_dir / "html.failure.response.json"
        response_path.write_text(
            json.dumps(redact_flaresolverr_response_payload(response_payload), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        artifact_paths["response_path"] = str(response_path)
    return artifact_paths


def decode_base64_blob(data: str) -> bytes:
    payload = data or ""
    if "," in payload and payload.lower().startswith("data:"):
        payload = payload.split(",", 1)[1]
    return base64.b64decode(payload)


def build_local_service_pool() -> urllib3.PoolManager:
    return urllib3.PoolManager()


def _session_registry_key(config: FlareSolverrRuntimeConfig) -> tuple[str, str]:
    return (config.url.rstrip("/"), config.provider)


def _session_lock_for(config: FlareSolverrRuntimeConfig) -> threading.RLock:
    key = _session_registry_key(config)
    with _SESSION_REGISTRY_LOCK:
        lock = _SESSION_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _SESSION_LOCKS[key] = lock
        return lock


def _destroy_remote_session(
    base_url: str,
    session_id: str,
    *,
    pool: urllib3.PoolManager | None = None,
) -> None:
    try:
        response = post_to_flaresolverr(
            base_url,
            {"cmd": "sessions.destroy", "session": session_id},
            timeout_seconds=30.0,
            pool=pool,
        )
    except FlareSolverrFailure:
        return
    message = normalize_text(str(response.get("message") or ""))
    status = normalize_text(str(response.get("status") or "")).lower()
    if status not in {"", "ok"} and not is_invalid_session_message(message):
        logger.debug(
            "flaresolverr_session provider=%s action=destroy_failed session_id=%s message=%s",
            "unknown",
            session_id,
            message or response.get("status"),
        )


def _create_registered_session(
    config: FlareSolverrRuntimeConfig,
    *,
    pool: urllib3.PoolManager,
    action: str,
) -> FlareSolverrSessionState:
    session_id = f"{sanitize_filename(config.provider)}-{uuid.uuid4().hex[:12]}"
    create_response = post_to_flaresolverr(
        config.url,
        {"cmd": "sessions.create", "session": session_id},
        timeout_seconds=30.0,
        pool=pool,
    )
    if normalize_text(str(create_response.get("status") or "")).lower() not in {"", "ok"}:
        raise FlareSolverrFailure(
            "flaresolverr_session_create_failed",
            normalize_text(str(create_response.get("message") or "")) or "FlareSolverr refused to create a session.",
            details={"response": create_response},
        )
    now = time.time()
    session_state = FlareSolverrSessionState(
        session_id=session_id,
        created_at=now,
        last_used_at=now,
        warm=False,
    )
    with _SESSION_REGISTRY_LOCK:
        _SESSION_REGISTRY[_session_registry_key(config)] = session_state
    logger.debug(
        "flaresolverr_session provider=%s action=%s session_id=%s warm=%s",
        config.provider,
        action,
        session_id,
        session_state.warm,
    )
    return session_state


def _acquire_registered_session(
    config: FlareSolverrRuntimeConfig,
    *,
    pool: urllib3.PoolManager,
    recreate: bool = False,
) -> FlareSolverrSessionState:
    key = _session_registry_key(config)
    with _SESSION_REGISTRY_LOCK:
        session_state = _SESSION_REGISTRY.get(key)
        if session_state is not None and not recreate:
            session_state.last_used_at = time.time()
            logger.debug(
                "flaresolverr_session provider=%s action=reuse session_id=%s warm=%s",
                config.provider,
                session_state.session_id,
                session_state.warm,
            )
            return session_state
    return _create_registered_session(config, pool=pool, action="recreate" if recreate else "create")


def _mark_registered_session_used(config: FlareSolverrRuntimeConfig, session_state: FlareSolverrSessionState) -> None:
    with _SESSION_REGISTRY_LOCK:
        registered = _SESSION_REGISTRY.get(_session_registry_key(config))
        if registered is None or registered.session_id != session_state.session_id:
            return
        registered.last_used_at = time.time()
        registered.warm = True


def _evict_registered_session(
    config: FlareSolverrRuntimeConfig,
    *,
    pool: urllib3.PoolManager,
    reason: str,
) -> FlareSolverrSessionState | None:
    key = _session_registry_key(config)
    with _SESSION_REGISTRY_LOCK:
        session_state = _SESSION_REGISTRY.pop(key, None)
    if session_state is None:
        return None
    logger.debug(
        "flaresolverr_session provider=%s action=evict reason=%s session_id=%s",
        config.provider,
        reason,
        session_state.session_id,
    )
    _destroy_remote_session(config.url, session_state.session_id, pool=pool)
    return session_state


def _destroy_registered_session_if_current(
    config: FlareSolverrRuntimeConfig,
    session_state: FlareSolverrSessionState,
    *,
    pool: urllib3.PoolManager,
    reason: str,
) -> FlareSolverrSessionState | None:
    key = _session_registry_key(config)
    with _SESSION_REGISTRY_LOCK:
        registered = _SESSION_REGISTRY.get(key)
        if registered is None or registered.session_id != session_state.session_id:
            return None
        _SESSION_REGISTRY.pop(key, None)
    logger.debug(
        "flaresolverr_session provider=%s action=destroy reason=%s session_id=%s",
        config.provider,
        reason,
        session_state.session_id,
    )
    _destroy_remote_session(config.url, session_state.session_id, pool=pool)
    return session_state


def _wait_seconds_for_session(
    session_state: FlareSolverrSessionState,
    *,
    cold_wait_seconds: int,
    warm_wait_seconds: int,
) -> tuple[int, str]:
    if session_state.warm:
        return warm_wait_seconds, "warm"
    return cold_wait_seconds, "cold"


def is_invalid_session_message(message: str | None) -> bool:
    normalized = normalize_text(message or "").lower()
    if "session" not in normalized:
        return False
    return any(
        pattern in normalized
        for pattern in (
            "session not found",
            "invalid session",
            "unknown session",
            "session does not exist",
            "session doesn't exist",
            "session not exists",
            "no such session",
        )
    )


def reset_session_registry_for_tests() -> None:
    with _SESSION_REGISTRY_LOCK:
        _SESSION_REGISTRY.clear()
        _SESSION_LOCKS.clear()


def _destroy_registered_sessions_at_exit() -> None:
    with _SESSION_REGISTRY_LOCK:
        registered = list(_SESSION_REGISTRY.items())
        _SESSION_REGISTRY.clear()
    for (base_url, provider), session_state in registered:
        try:
            logger.debug(
                "flaresolverr_session provider=%s action=destroy_at_exit session_id=%s",
                provider,
                session_state.session_id,
            )
            _destroy_remote_session(base_url, session_state.session_id)
        except Exception:
            continue


atexit.register(_destroy_registered_sessions_at_exit)


def post_to_flaresolverr(
    base_url: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: float,
    pool: urllib3.PoolManager | None = None,
) -> dict[str, Any]:
    client = pool or build_local_service_pool()
    try:
        response = client.request(
            "POST",
            base_url.rstrip("/"),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            body=json.dumps(payload).encode("utf-8"),
            timeout=urllib3.Timeout(connect=timeout_seconds, read=timeout_seconds),
            retries=False,
        )
    except urllib3.exceptions.ReadTimeoutError as exc:
        raise FlareSolverrFailure("flaresolverr_timeout", f"Timed out while calling FlareSolverr: {exc}") from exc
    except urllib3.exceptions.HTTPError as exc:
        raise FlareSolverrFailure("flaresolverr_transport_error", f"Failed to call FlareSolverr: {exc}") from exc

    try:
        payload_json = json.loads(response.data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlareSolverrFailure(
            "invalid_flaresolverr_response",
            f"FlareSolverr returned non-JSON content: {exc}",
        ) from exc
    if not isinstance(payload_json, dict):
        raise FlareSolverrFailure(
            "invalid_flaresolverr_response",
            "FlareSolverr returned a non-object JSON payload.",
        )
    return payload_json


def fetch_html_with_flaresolverr(
    candidate_urls: list[str],
    *,
    publisher: str,
    config: FlareSolverrRuntimeConfig,
    wait_seconds: int = DEFAULT_FLARESOLVERR_WAIT_SECONDS,
    warm_wait_seconds: int = DEFAULT_FLARESOLVERR_WARM_WAIT_SECONDS,
    max_timeout_ms: int = DEFAULT_FLARESOLVERR_MAX_TIMEOUT_MS,
    return_image_payload: bool = False,
    return_screenshot: bool = False,
    disable_media: bool = False,
) -> FetchedPublisherHtml:
    if not candidate_urls:
        raise FlareSolverrFailure("empty_html_attempts", "No publisher HTML candidates were attempted.")

    last_failure: FlareSolverrFailure | None = None
    latest_browser_context_seed: Mapping[str, Any] | None = None
    pool = build_local_service_pool()
    artifact_dir = config.artifact_dir / "flaresolverr"
    session_lock = _session_lock_for(config)
    session_state: FlareSolverrSessionState | None = None

    with session_lock:
        try:
            session_state = _acquire_registered_session(config, pool=pool)

            for url in candidate_urls:
                challenge_retried = False
                session_recreated = False
                force_cold_retry = False

                while True:
                    if session_state is None:
                        session_state = _acquire_registered_session(config, pool=pool)

                    effective_wait_seconds = wait_seconds
                    wait_mode = "cold"
                    if not force_cold_retry:
                        effective_wait_seconds, wait_mode = _wait_seconds_for_session(
                            session_state,
                            cold_wait_seconds=wait_seconds,
                            warm_wait_seconds=warm_wait_seconds,
                        )
                    logger.debug(
                        "flaresolverr_request provider=%s action=request session_id=%s wait_mode=%s wait_seconds=%s url=%s",
                        publisher,
                        session_state.session_id,
                        wait_mode,
                        effective_wait_seconds,
                        url,
                    )
                    request_payload = {
                        "cmd": "request.get",
                        "url": url,
                        "session": session_state.session_id,
                        "returnScreenshot": bool(return_screenshot),
                        "waitInSeconds": effective_wait_seconds,
                        "maxTimeout": max_timeout_ms,
                    }
                    if disable_media and not return_image_payload:
                        request_payload["disableMedia"] = True
                    if return_image_payload:
                        request_payload["returnImagePayload"] = True
                    try:
                        request_response = post_to_flaresolverr(
                            config.url,
                            request_payload,
                            timeout_seconds=(max_timeout_ms / 1000.0) + 45.0,
                            pool=pool,
                        )
                    except FlareSolverrFailure as exc:
                        last_failure = exc
                        break

                    top_level_status = normalize_text(str(request_response.get("status") or "")).lower()
                    if top_level_status and top_level_status != "ok":
                        message = normalize_text(str(request_response.get("message") or ""))
                        if is_invalid_session_message(message):
                            _evict_registered_session(config, pool=pool, reason="invalid_session")
                            session_state = None
                            if not session_recreated:
                                session_recreated = True
                                session_state = _acquire_registered_session(config, pool=pool, recreate=True)
                                force_cold_retry = True
                                continue
                            last_failure = FlareSolverrFailure(
                                "flaresolverr_session_invalid",
                                message or "FlareSolverr session became invalid.",
                                details={"response": request_response},
                            )
                            save_flaresolverr_failure_artifacts(artifact_dir, response_payload=request_response)
                            break
                        error_kind = (
                            "flaresolverr_timeout" if "timeout" in message.lower() else "flaresolverr_request_failed"
                        )
                        last_failure = FlareSolverrFailure(
                            error_kind,
                            message or "FlareSolverr request.get failed.",
                            details={"response": request_response},
                        )
                        save_flaresolverr_failure_artifacts(artifact_dir, response_payload=request_response)
                        break

                    solution = request_response.get("solution") or {}
                    html = str(solution.get("response") or "")
                    final_url = str(solution.get("url") or url)
                    response_status = parse_optional_int(solution.get("status"))
                    response_headers = solution.get("headers") if isinstance(solution.get("headers"), dict) else {}
                    title = extract_page_title(BeautifulSoup(html, choose_parser()))
                    summary = summarize_html(html)
                    browser_context_seed = extract_flaresolverr_browser_context_seed(solution)
                    if browser_context_seed.get("browser_cookies") or browser_context_seed.get("browser_user_agent"):
                        latest_browser_context_seed = browser_context_seed
                    _mark_registered_session_used(config, session_state)
                    force_cold_retry = False

                    if looks_like_abstract_redirect(url, final_url):
                        last_failure = FlareSolverrFailure(
                            REDIRECTED_TO_ABSTRACT,
                            "Publisher redirected the full-text URL to an abstract page.",
                            browser_context_seed=browser_context_seed,
                        )
                        save_flaresolverr_failure_artifacts(
                            artifact_dir,
                            html=html,
                            screenshot_b64=solution.get("screenshot"),
                            response_payload=request_response,
                        )
                        break

                    detected = detect_html_block(title or "", summary, response_status)
                    if detected is not None:
                        if detected.reason == CLOUDFLARE_CHALLENGE and wait_mode == "warm" and not challenge_retried:
                            challenge_retried = True
                            force_cold_retry = True
                            logger.debug(
                                "flaresolverr_request provider=%s action=retry_challenge session_id=%s "
                                "wait_mode=cold url=%s",
                                publisher,
                                session_state.session_id,
                                url,
                            )
                            continue
                        last_failure = FlareSolverrFailure(
                            detected.reason,
                            detected.message,
                            browser_context_seed=browser_context_seed,
                        )
                        save_flaresolverr_failure_artifacts(
                            artifact_dir,
                            html=html,
                            screenshot_b64=solution.get("screenshot"),
                            response_payload=request_response,
                        )
                        break

                    return FetchedPublisherHtml(
                        source_url=url,
                        final_url=final_url,
                        html=html,
                        response_status=response_status,
                        response_headers=response_headers,
                        title=title,
                        summary=summary,
                        browser_context_seed=browser_context_seed,
                        screenshot_b64=solution.get("screenshot") if isinstance(solution.get("screenshot"), str) else None,
                        image_payload=solution.get("imagePayload") if isinstance(solution.get("imagePayload"), dict) else None,
                    )
        finally:
            if not config.keep_session and session_state is not None:
                _destroy_registered_session_if_current(config, session_state, pool=pool, reason="request_complete")

    if last_failure is None and latest_browser_context_seed is not None:
        last_failure = FlareSolverrFailure(
            "empty_html_attempts",
            "No publisher HTML candidates were attempted.",
            browser_context_seed=latest_browser_context_seed,
        )
    if last_failure is None:
        last_failure = FlareSolverrFailure("empty_html_attempts", "No publisher HTML candidates were attempted.")
    raise last_failure
