#!/bin/sh
set -eu

CODEX_HOME="${CODEX_HOME:-/data/codex}"
export CODEX_HOME

mkdir -p "$CODEX_HOME"
chmod 700 "$CODEX_HOME"

if [ ! -f "$CODEX_HOME/config.toml" ]; then
  cat > "$CODEX_HOME/config.toml" <<'EOF'
cli_auth_credentials_store = "file"
forced_login_method = "chatgpt"
EOF
  chmod 600 "$CODEX_HOME/config.toml"
fi

if [ ! -f "$CODEX_HOME/auth.json" ] && [ -n "${CODEX_AUTH_JSON_B64:-}" ]; then
  printf '%s' "$CODEX_AUTH_JSON_B64" | base64 -d > "$CODEX_HOME/auth.json"
  chmod 600 "$CODEX_HOME/auth.json"
fi

exec "$@"
