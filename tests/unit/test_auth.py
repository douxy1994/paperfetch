from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from paper_fetch import auth


class _FakeAuthPage:
    url = "https://journals.ametsoc.org/view/journals/mwre/example.xml"

    def __init__(self) -> None:
        self.goto_calls: list[tuple[str, dict[str, object]]] = []
        self.closed = False

    def goto(self, url: str, **kwargs) -> None:
        self.goto_calls.append((url, dict(kwargs)))

    def title(self) -> str:
        return "AMS Article"

    def close(self) -> None:
        self.closed = True


class _FakeAuthContext:
    def __init__(self, state_payload: str) -> None:
        self.page = _FakeAuthPage()
        self.state_payload = state_payload
        self.storage_state_path: str | None = None
        self.closed = False

    def new_page(self) -> _FakeAuthPage:
        return self.page

    def storage_state(self, *, path: str) -> None:
        self.storage_state_path = path
        Path(path).write_text(self.state_payload, encoding="utf-8")

    def close(self) -> None:
        self.closed = True


class _FakeAuthBrowser:
    def __init__(self) -> None:
        self.context = _FakeAuthContext('{"cookies":[],"origins":[]}')
        self.new_context_kwargs: dict[str, object] = {}
        self.closed = False

    def new_context(self, **kwargs):
        self.new_context_kwargs = dict(kwargs)
        return self.context

    def close(self) -> None:
        self.closed = True


class _FakeCloakBrowserModule:
    def __init__(self) -> None:
        self.browser = _FakeAuthBrowser()
        self.launch_kwargs: dict[str, object] = {}

    def launch(self, **kwargs):
        self.launch_kwargs = dict(kwargs)
        return self.browser


def test_upsert_env_file_updates_existing_values(tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# existing\n"
        'export PAPER_FETCH_AMS_STORAGE_STATE_JSON="/old/state.json"\n'
        "KEEP=value\n",
        encoding="utf-8",
    )

    auth.upsert_env_file(
        env_file,
        {
            "PAPER_FETCH_AMS_STORAGE_STATE_JSON": "/tmp/with space/state.json",
            "NEW_KEY": 'quoted"value',
        },
    )

    assert env_file.read_text(encoding="utf-8") == (
        "# existing\n"
        'PAPER_FETCH_AMS_STORAGE_STATE_JSON="/tmp/with space/state.json"\n'
        "KEEP=value\n"
        'NEW_KEY="quoted\\"value"\n'
    )


def test_authenticate_ams_saves_storage_state_and_env_file(monkeypatch, tmp_path) -> None:
    fake_module = _FakeCloakBrowserModule()
    state_path = tmp_path / "ams" / "storage-state.json"
    env_file = tmp_path / ".env"

    monkeypatch.setattr(auth, "build_runtime_env", lambda: {})
    monkeypatch.setattr(
        auth._cloakbrowser,
        "_import_cloakbrowser",
        lambda: fake_module,
    )
    monkeypatch.setattr(
        auth,
        "wait_for_atypon_body_dom_ready",
        lambda *_args, **_kwargs: SimpleNamespace(ready=True),
    )

    result = auth.authenticate_ams(
        state_json=state_path,
        env_file=env_file,
        wait_seconds=1,
        target_url="https://journals.ametsoc.org/doi/10.1175/MWR-D-10-05037.1",
    )

    assert result.provider == "ams"
    assert result.storage_state_path == state_path
    assert result.env_written is True
    assert result.env_file_path == env_file
    assert result.verified is True
    assert state_path.read_text(encoding="utf-8") == '{"cookies":[],"origins":[]}'
    assert f'PAPER_FETCH_AMS_STORAGE_STATE_JSON="{state_path}"' in env_file.read_text(encoding="utf-8")
    assert fake_module.launch_kwargs["headless"] is False
    assert "storage_state" not in fake_module.browser.new_context_kwargs
    assert fake_module.browser.context.storage_state_path == str(state_path)


def test_authenticate_ams_reuses_configured_state_path(monkeypatch, tmp_path) -> None:
    fake_module = _FakeCloakBrowserModule()
    state_path = tmp_path / "configured" / "storage-state.json"

    monkeypatch.setattr(
        auth,
        "build_runtime_env",
        lambda: {"PAPER_FETCH_AMS_STORAGE_STATE_JSON": str(state_path)},
    )
    monkeypatch.setattr(
        auth._cloakbrowser,
        "_import_cloakbrowser",
        lambda: fake_module,
    )
    monkeypatch.setattr(
        auth,
        "wait_for_atypon_body_dom_ready",
        lambda *_args, **_kwargs: SimpleNamespace(ready=True),
    )

    result = auth.authenticate_ams(write_env=False, wait_seconds=1)

    assert result.storage_state_path == state_path
    assert result.env_written is False
    assert result.env_file_path is None
    assert state_path.read_text(encoding="utf-8") == '{"cookies":[],"origins":[]}'
