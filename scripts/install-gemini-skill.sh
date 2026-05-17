#!/usr/bin/env bash
# Install the static paper-fetch skill for Gemini CLI.
#
# Usage:
#   ./scripts/install-gemini-skill.sh              # user-scope skill (~/.gemini/skills/...)
#   ./scripts/install-gemini-skill.sh --project    # project-scope skill (./.gemini/skills/...)
#   ./scripts/install-gemini-skill.sh --register-mcp [--env-file .env]
#   ./scripts/install-gemini-skill.sh --uninstall  # remove the installed skill entry

set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_skill_install_common.sh"

PF_HOST="gemini"
PF_RESTART_NAME="Gemini CLI"
PF_GEMINI_MCP_SKIPPED=0

pf_host_register_mcp() {
    if ! command -v gemini >/dev/null 2>&1; then
        PF_GEMINI_MCP_SKIPPED=1
        pf_skill_warn "gemini not found on PATH; installed the skill and skipped Gemini MCP registration."
        return 0
    fi

    local python_bin
    python_bin="$(python3 -c 'import sys; print(sys.executable)')"

    if [ -n "$PF_MCP_ENV_FILE" ] && [ ! -f "$PF_MCP_ENV_FILE" ]; then
        pf_skill_warn "MCP env file $PF_MCP_ENV_FILE does not exist yet; registration will still point to it."
    fi

    pf_skill_log "Registering Gemini MCP server '$PF_MCP_NAME'"
    gemini mcp remove -s user "$PF_MCP_NAME" >/dev/null 2>&1 || true

    local args=(mcp add -s user)
    if [ -n "$PF_MCP_ENV_FILE" ]; then
        args+=(-e "PAPER_FETCH_ENV_FILE=$PF_MCP_ENV_FILE")
    fi
    args+=("$PF_MCP_NAME" "$python_bin" -m paper_fetch.mcp.server)
    gemini "${args[@]}"
}

pf_host_unregister_mcp() {
    if command -v gemini >/dev/null 2>&1; then
        gemini mcp remove -s user "$PF_MCP_NAME" >/dev/null 2>&1 || true
        pf_skill_log "Removed Gemini MCP server '$PF_MCP_NAME'"
    fi
}

pf_host_print_registered_note() {
    if [ "$PF_GEMINI_MCP_SKIPPED" = "1" ]; then
        echo "  2. Gemini CLI was not found, so only the skill was installed. Register MCP manually with a stdio server that runs 'python3 -m paper_fetch.mcp.server'."
    else
        echo "  2. Gemini MCP server '$PF_MCP_NAME' is registered and will launch via the current python3 environment."
    fi
}

pf_skill_main "$@"
