#!/usr/bin/env bash
set -euo pipefail

WRAPPER="$HOME/.local/bin/opencode"
REAL_OPENCODE="${REAL_OPENCODE:-$HOME/.nvm/versions/node/v22.22.2/bin/opencode}"

mkdir -p "$HOME/.local/bin" "$HOME/.config/opencode"

python3 - <<'PY'
from pathlib import Path
import sys

sys.path.insert(0, str(Path.home() / "Agents"))
from watch_mastersword_queue import _ensure_config

_ensure_config()
PY

cat > "$WRAPPER" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

export OPENCODE_CONFIG="${OPENCODE_CONFIG:-$HOME/.config/opencode/opencode.json}"
export OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX="${OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX:-2048}"

_load_key() {
  python3 - "$1" <<'PY' 2>/dev/null
from pathlib import Path; import sys
sys.path.insert(0, str(Path.home() / 'Agents'))
try:
    import hyrule_env as e; keys = getattr(e, sys.argv[1], [])
    print(keys[0] if keys else '')
except: print('')
PY
}

[[ -z "${OPENROUTER_API_KEY:-}" && -f "$HOME/Agents/hyrule_env.py" ]] && \
  OPENROUTER_API_KEY="$(_load_key OPENROUTER_KEYS)" && export OPENROUTER_API_KEY

[[ -z "${MISTRAL_API_KEY:-}" && -f "$HOME/Agents/hyrule_env.py" ]] && \
  MISTRAL_API_KEY="$(_load_key MISTRAL_KEYS)" && export MISTRAL_API_KEY

[[ -z "${CEREBRAS_API_KEY:-}" && -f "$HOME/Agents/hyrule_env.py" ]] && \
  CEREBRAS_API_KEY="$(_load_key CEREBRAS_KEYS)" && export CEREBRAS_API_KEY

REAL="${REAL_OPENCODE:-$HOME/.nvm/versions/node/v22.22.2/bin/opencode}"
exec "$REAL" "$@"
EOF
chmod +x "$WRAPPER"

if ! grep -q "Hyrule OpenCode / MASTERSWORD defaults" "$HOME/.bashrc"; then
  cat >> "$HOME/.bashrc" <<'EOF'

# Hyrule OpenCode / MASTERSWORD defaults
export OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX="${OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX:-2048}"
export OPENCODE_CONFIG="${OPENCODE_CONFIG:-$HOME/.config/opencode/opencode.json}"
alias mastersword='cd ~/Agents && ./mastersword'
EOF
fi

echo "OpenCode CLI configurado:"
echo "  wrapper:      $WRAPPER"
echo "  config:       $HOME/.config/opencode/opencode.json"
echo "  modelo:       openrouter/openai/gpt-5.1"
echo "  small_model:  cerebras/qwen-3-235b-a22b-instruct-2507"
echo "  providers:    openrouter + mistral + cerebras"
