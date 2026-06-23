#!/usr/bin/env bash
# Install the static paper-fetch skill for ZCode.
#
# ZCode (https://z.ai) reads user-scope skills from ~/.zcode/skills/<name>/
# and MCP servers from the JSON config at ~/.zcode/v2/config.json under the
# top-level "mcp" object. Each MCP entry uses the schema:
#   { "type": "local", "enabled": true, "command": [...], "environment": {...} }
#
# ZCode has no `mcp add` CLI subcommand, so this installer edits the JSON
# config directly (mirrors the Antigravity config-edit approach). The skill
# directory layout (SKILL.md + references/) is identical to Claude/Codex.
#
# Usage:
#   ./scripts/install-zcode-skill.sh              # user-scope skill (~/.zcode/skills/...)
#   ./scripts/install-zcode-skill.sh --project    # project-scope skill (./.zcode/skills/...)
#   ./scripts/install-zcode-skill.sh --register-mcp [--env-file .env]
#   ./scripts/install-zcode-skill.sh --uninstall  # remove the installed skill entry
#
# Override the global ZCode config directory with ZCODE_HOME (defaults to ~/.zcode).

set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_skill_install_common.sh"

PF_HOST="zcode"
PF_RESTART_NAME="ZCode"

# ZCode MCP entries live in a JSON config (not behind a CLI), so config-scope
# is the only meaningful distinction. User scope edits the global config;
# project scope edits the workspace config alongside the skill.
pf_zcode_mcp_config_path() {
    if [ "$PF_SCOPE" = "user" ]; then
        printf '%s/v2/config.json\n' "$(pf_skill_user_base)"
    else
        printf '%s/.zcode/v2/config.json\n' "$PF_REPO_DIR"
    fi
}

pf_host_register_mcp() {
    local python_bin config_path
    python_bin="$(python3 -c 'import sys; print(sys.executable)')"
    config_path="$(pf_zcode_mcp_config_path)"

    if [ -n "$PF_MCP_ENV_FILE" ] && [ ! -f "$PF_MCP_ENV_FILE" ]; then
        pf_skill_warn "MCP env file $PF_MCP_ENV_FILE does not exist yet; registration will still point to it."
    fi

    pf_skill_log "Registering ZCode MCP server '$PF_MCP_NAME' in $config_path"
    mkdir -p "$(dirname "$config_path")"

    PF_CONFIG_PATH="$config_path" \
    PF_MCP_NAME="$PF_MCP_NAME" \
    PF_PYTHON_BIN="$python_bin" \
    PF_MCP_ENV_FILE="$PF_MCP_ENV_FILE" \
    python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["PF_CONFIG_PATH"])
name = os.environ["PF_MCP_NAME"]
python_bin = os.environ["PF_PYTHON_BIN"]
env_file = os.environ.get("PF_MCP_ENV_FILE") or ""

# ZCode's MCP config schema: each entry is
#   { "type": "local", "enabled": true, "command": [...], "environment": {...} }
entry = {
    "type": "local",
    "enabled": True,
    "command": [python_bin, "-X", "utf8", "-m", "paper_fetch.mcp.server"],
}
if env_file:
    entry["environment"] = {"PAPER_FETCH_ENV_FILE": env_file}

data = {}
if path.exists():
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Existing {path} is not valid JSON: {exc}")
if not isinstance(data, dict):
    raise SystemExit(f"Existing {path} must contain a JSON object")

# ZCode stores servers under the top-level "mcp" key.
servers = data.setdefault("mcp", {})
if not isinstance(servers, dict):
    raise SystemExit(f"'mcp' in {path} must be a JSON object")

servers[name] = entry
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

pf_host_unregister_mcp() {
    local config_path
    config_path="$(pf_zcode_mcp_config_path)"
    [ -f "$config_path" ] || return 0

    PF_CONFIG_PATH="$config_path" \
    PF_MCP_NAME="$PF_MCP_NAME" \
    python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["PF_CONFIG_PATH"])
name = os.environ["PF_MCP_NAME"]
try:
    data = json.loads(path.read_text(encoding="utf-8") or "{}")
except json.JSONDecodeError:
    raise SystemExit(0)
if not isinstance(data, dict):
    raise SystemExit(0)

servers = data.get("mcp")
if isinstance(servers, dict):
    servers.pop(name, None)
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
    pf_skill_log "Removed ZCode MCP server '$PF_MCP_NAME' from $config_path"
}

pf_host_print_registered_note() {
    echo "  2. ZCode MCP server '$PF_MCP_NAME' is registered in $(pf_zcode_mcp_config_path) and will launch via the current python3 environment."
    echo "     Browser-backed providers auto-start cloakbrowser Chrome unless CLOAKBROWSER_CDP_ENDPOINT points at an existing browser."
}

pf_skill_main "$@"
