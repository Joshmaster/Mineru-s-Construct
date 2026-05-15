#!/usr/bin/env bash
# setup.sh — gera hyrule_env.py a partir das variáveis de ambiente (GitHub Secrets)
#
# Uso:
#   export DISCORD_TOKEN="..."
#   export OPENROUTER_KEY_1="..." OPENROUTER_KEY_2="..." OPENROUTER_KEY_3="..."
#   export CEREBRAS_KEY_1="..."   CEREBRAS_KEY_2="..."   CEREBRAS_KEY_3="..."
#   export MISTRAL_KEY_1="..."    MISTRAL_KEY_2="..."    MISTRAL_KEY_3="..."
#   export WA_OWNER="..."         WA_ALLOW_FROM="..."
#   bash setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$SCRIPT_DIR/hyrule_env.py"

# ── Validar variáveis obrigatórias ────────────────────────────────────────────
MISSING=()
for VAR in DISCORD_TOKEN OPENROUTER_KEY_1 CEREBRAS_KEY_1 MISTRAL_KEY_1 WA_OWNER WA_ALLOW_FROM; do
    [[ -z "${!VAR}" ]] && MISSING+=("$VAR")
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "ERRO: variáveis obrigatórias não definidas:"
    for v in "${MISSING[@]}"; do echo "  - $v"; done
    echo ""
    echo "Exemplo:"
    echo "  export DISCORD_TOKEN='seu_token'"
    echo "  bash setup.sh"
    exit 1
fi

# ── Gerar hyrule_env.py ───────────────────────────────────────────────────────
cat > "$OUT" <<PYEOF
"""
Credenciais do sistema Hyrule.
Gerado automaticamente por setup.sh — não editar user2almente.
ESTE ARQUIVO NAO VAI PRO GIT.
"""

DISCORD_TOKEN = "${DISCORD_TOKEN}"

OPENROUTER_KEYS = [k for k in [
    "${OPENROUTER_KEY_1}",
    "${OPENROUTER_KEY_2:-}",
    "${OPENROUTER_KEY_3:-}",
] if k]

CEREBRAS_KEYS = [k for k in [
    "${CEREBRAS_KEY_1}",
    "${CEREBRAS_KEY_2:-}",
    "${CEREBRAS_KEY_3:-}",
] if k]

MISTRAL_KEYS = [k for k in [
    "${MISTRAL_KEY_1}",
    "${MISTRAL_KEY_2:-}",
    "${MISTRAL_KEY_3:-}",
] if k]

WA_OWNER = "${WA_OWNER}"

WA_ALLOW_FROM = [n.strip() for n in "${WA_ALLOW_FROM}".split(",") if n.strip()]
PYEOF

echo "✓ hyrule_env.py gerado em $OUT"

# ── Instalar dependências Python ──────────────────────────────────────────────
if [[ "${SKIP_DEPS:-}" != "1" ]]; then
    echo "Instalando dependências Python..."
    pip3 install -q discord.py aiohttp requests flask neonize qrcode httpx segno
    echo "✓ dependências instaladas"
fi

echo ""
echo "Próximo passo:"
echo "  python3 startup_services.py start"
