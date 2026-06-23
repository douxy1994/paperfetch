#!/usr/bin/env bash
# Install the static paper-fetch skill for the Hermes Agent (Nous Research).
#
# Hermes reads user-scope skills from ~/.hermes/skills/<name>/ (same SKILL.md +
# references/ layout as Claude/Codex) and registers MCP servers via its CLI:
#   hermes mcp add <name> --command <cmd> --args ... [--env KEY=VALUE]
#   hermes mcp remove <name>
#
# Usage:
#   ./scripts/install-hermes-skill.sh              # user-scope skill (~/.hermes/skills/...)
#   ./scripts/install-hermes-skill.sh --project    # project-scope skill (./.hermes/skills/...)
#   ./scripts/install-hermes-skill.sh --register-mcp [--env-file .env]
#   ./scripts/install-hermes-skill.sh --uninstall  # remove the installed skill entry
#
# Override the global Hermes config directory with HERMES_HOME (defaults to ~/.hermes).

set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_skill_install_common.sh"

PF_HOST="hermes"
PF_RESTART_NAME="Hermes Agent"

pf_host_register_mcp() {
    command -v hermes >/dev/null 2>&1 || pf_skill_die "hermes not found on PATH; cannot auto-register MCP. Install Hermes Agent CLI or rerun without --register-mcp."

    if [ -n "$PF_MCP_ENV_FILE" ] && [ ! -f "$PF_MCP_ENV_FILE" ]; then
        pf_skill_warn "MCP env file $PF_MCP_ENV_FILE does not exist yet; registration will still point to it."
    fi

    # Hermes runs in its own venv. Its live `mcp add` probe launches the
    # registered --command as a subprocess, so that interpreter must be able to
    # import paper_fetch. Prefer Hermes' own python when it already has the
    # package installed (makes the probe succeed); otherwise fall back to the
    # caller's python3 and force-enable the entry afterwards.
    local python_bin hermes_python
    python_bin="$(python3 -c 'import sys; print(sys.executable)')"
    hermes_python="$(${HERMES_HOME:-$HOME/.hermes}/hermes-agent/venv/bin/python -c 'import sys; print(sys.executable)' 2>/dev/null || true)"
    if [ -n "$hermes_python" ] && "$hermes_python" -c 'import paper_fetch.mcp.server' >/dev/null 2>&1; then
        python_bin="$hermes_python"
        pf_skill_log "Using Hermes venv python ($python_bin) so its connection probe can import paper_fetch."
    else
        pf_skill_warn "Hermes venv cannot import paper_fetch; registering with caller python ($python_bin). The probe may fail, but the entry will be force-enabled below. Run this installer again after installing the package into Hermes' venv for a clean probe."
    fi

    pf_skill_log "Registering Hermes MCP server '$PF_MCP_NAME'"
    # `hermes mcp remove` is idempotent: ignore failure if the server is absent.
    hermes mcp remove "$PF_MCP_NAME" >/dev/null 2>&1 || true

    local args=(mcp add "$PF_MCP_NAME" --command "$python_bin")
    if [ -n "$PF_MCP_ENV_FILE" ]; then
        args+=(--env "PAPER_FETCH_ENV_FILE=$PF_MCP_ENV_FILE")
    fi
    # `--args` must be the last option; everything after it is the argv for the
    # stdio command. Hermes invokes: <python_bin> -X utf8 -m paper_fetch.mcp.server
    args+=(--args -X utf8 -m paper_fetch.mcp.server)

    # `hermes mcp add` probes the server and then prompts interactively. Two
    # prompts can appear:
    #   1. "Save config anyway (you can test later)? [y/N]"  (defaults to N)
    #      shown when the live connection probe fails (e.g. offline install,
    #      slow first launch of the cloakbrowser runtime). We answer "y" so the
    #      config is always written.
    #   2. "Enable all N tools? [Y/n/select]"  (defaults to Y)
    #      shown after the config is saved. We answer "y" to enable every tool.
    # Feeding both answers lets registration succeed non-interactively whether
    # or not the probe reaches the server. stderr is surfaced so users still
    # see the "Saved '...' to config.yaml" confirmation.
    printf 'y\ny\n' | hermes "${args[@]}" >&2 || pf_skill_die "hermes mcp add failed for '$PF_MCP_NAME'."

    # When the probe failed, Hermes writes the entry with enabled:false. The
    # caller python may legitimately host paper_fetch even if Hermes' probe
    # could not reach it (different venv, slow cloakbrowser warmup). Force the
    # entry back to enabled:true so the server is usable without a re-probe.
    pf_hermes_force_enable "$PF_MCP_NAME"
}

# Set a registered MCP server's `enabled` field to true in Hermes' config.yaml,
# regardless of whether the live probe succeeded. Hermes stores servers under a
# top-level `mcp_servers:` mapping as {command, args, enabled}. Idempotent and
# safe when the server or the config file is absent.
pf_hermes_force_enable() {
    local name="$1"
    local config_file
    config_file="${HERMES_HOME:-$HOME/.hermes}/config.yaml"
    [ -f "$config_file" ] || return 0

    PF_CONFIG_FILE="$config_file" \
    PF_MCP_NAME="$name" \
    python3 - <<'PY'
import os
import re
from pathlib import Path

path = Path(os.environ["PF_CONFIG_FILE"])
name = os.environ["PF_MCP_NAME"]
text = path.read_text(encoding="utf-8")

# Locate the `mcp_servers:` block and the `<name>:` entry within it. Hermes
# writes a shallow `  <name>:\n    command: ...\n    enabled: <bool>` shape, so
# we toggle the first `enabled:` key found directly under that entry.
mcp_idx = text.find("mcp_servers:")
if mcp_idx == -1:
    raise SystemExit(0)

entry_pat = re.compile(r"(^|\n)([ \t]*)(" + re.escape(name) + r"):[ \t]*\n")
m = entry_pat.search(text, mcp_idx)
if not m:
    raise SystemExit(0)

indent = m.group(2)
# A sibling entry starts at the same or lower indent; stop before it.
entry_start = m.end()
sibling_pat = re.compile(r"\n" + re.escape(indent) + r"\S")
sibling = sibling_pat.search(text, entry_start)
entry_end = sibling.start() if sibling else len(text)
entry = text[entry_start:entry_end]

enabled_pat = re.compile(r"(^[ \t]*)enabled:[ \t]*\w+[ \t]*$", re.MULTILINE)
em = enabled_pat.search(entry)
if em:
    new_entry = entry[:em.start()] + em.group(1) + "enabled: true" + entry[em.end():]
else:
    # No enabled key yet; append one at the entry's indent.
    head = entry.rstrip()
    if head.endswith("\n"):
        new_entry = head + indent + "enabled: true\n"
    else:
        new_entry = head + "\n" + indent + "enabled: true\n"
    if not new_entry.endswith("\n"):
        new_entry += "\n"

path.write_text(text[:entry_start] + new_entry + text[entry_end:], encoding="utf-8")
PY
}

pf_host_unregister_mcp() {
    if command -v hermes >/dev/null 2>&1; then
        hermes mcp remove "$PF_MCP_NAME" >/dev/null 2>&1 || true
        pf_skill_log "Removed Hermes MCP server '$PF_MCP_NAME'"
    fi
}

pf_host_print_registered_note() {
    echo "  2. Hermes MCP server '$PF_MCP_NAME' is registered and will launch via the current python3 environment."
    echo "     Browser-backed providers auto-start cloakbrowser Chrome unless CLOAKBROWSER_CDP_ENDPOINT points at an existing browser."
}

pf_skill_main "$@"
