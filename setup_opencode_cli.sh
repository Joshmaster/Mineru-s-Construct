#!/usr/bin/env bash
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

if [[ -z "${OPENROUTER_API_KEY:-}" && -f "$HOME/Agents/hyrule_env.py" ]]; then
  OPENROUTER_API_KEY="$(python3 - <<'PY' 2>/dev/null
from pathlib import Path
import sys
sys.path.insert(0, str(Path.home() / 'Agents'))
try:
    from hyrule_env import OPENROUTER_KEYS
    print(OPENROUTER_KEYS[0] if OPENROUTER_KEYS else '')
except Exception:
    print('')
PY
)"
  export OPENROUTER_API_KEY
fi

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
echo "  wrapper: $WRAPPER"
echo "  config:  $HOME/.config/opencode/opencode.json"
echo "  modelo:  openrouter/openai/gpt-5.1"
