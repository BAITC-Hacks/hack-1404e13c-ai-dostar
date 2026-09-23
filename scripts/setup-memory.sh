#!/usr/bin/env bash
set -euo pipefail

if ! command -v codex >/dev/null 2>&1; then
  echo 'Codex CLI is required: https://developers.openai.com/codex/' >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null; then
  echo 'Python 3.10+ is required.' >&2
  exit 1
fi

if ! codex plugin marketplace list --json | python3 -c 'import json,sys; assert any(m["name"] == "mem0-plugins" for m in json.load(sys.stdin)["marketplaces"])' 2>/dev/null; then
  codex plugin marketplace add mem0ai/mem0
fi
if ! codex plugin list --marketplace mem0-plugins --json | python3 -c 'import json,sys; assert any(p["pluginId"] == "mem0@mem0-plugins" and p["enabled"] for p in json.load(sys.stdin)["installed"])' 2>/dev/null; then
  codex plugin add mem0@mem0-plugins
fi

if [[ -z "${MEM0_API_KEY:-}" ]]; then
  echo 'Mem0 plugin installed. Set MEM0_API_KEY from the team Mem0 workspace, then restart Codex.'
else
  echo 'Mem0 plugin installed and MEM0_API_KEY is set. Restart Codex and run Mem0 doctor.'
fi
