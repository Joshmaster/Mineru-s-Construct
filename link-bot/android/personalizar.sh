#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  Link Bot TOTK - Personalizar (Termux Android)
# ============================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
KIT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
CONFIG_DIR="$KIT_DIR/config"

echo -e "${BLUE}"
echo "============================================================"
echo "   LINK BOT TOTK - Personalizar"
echo "============================================================"
echo -e "${NC}"

if [ ! -f "$CONFIG_DIR/config.example.json" ]; then
    echo -e "${RED}ERRO: estrutura do kit corrompida.${NC}"
    exit 1
fi

# Backup
if [ -f "$CONFIG_DIR/config.json" ]; then
    BTS=$(date +%Y%m%d-%H%M%S)
    cp "$CONFIG_DIR/config.json" "$CONFIG_DIR/config.json.backup-$BTS"
    echo -e "${YELLOW}Backup do config anterior: config.json.backup-$BTS${NC}"
    echo
fi

# Numero
echo -e "${BLUE}[1/2] Configurando seu numero...${NC}"
echo
echo "Digite seu numero do WhatsApp (que vai poder falar com o bot):"
echo "Formato: 5511999999999 (codigo + DDD + numero, sem + ou espacos)"
echo
read -p "  Numero: " MEU_NUM

if ! echo "$MEU_NUM" | grep -qE '^[0-9]+$'; then
    echo -e "${RED}ERRO: numero deve conter apenas digitos.${NC}"
    exit 1
fi

# Controle PC
echo
echo -e "${BLUE}[2/2] Controle do PC pelo WhatsApp?${NC}"
echo
echo "As skills de PC (abre programa, CPU, volume, screenshot)"
echo "ficam DESATIVADAS por padrao por seguranca."
echo
echo "  [s] Ativar agora (use SO se confia 100% no numero acima)"
echo "  [n] Manter desativado (recomendado, pode mudar depois)"
echo
read -p "  Escolha [s/N] (default n): " PC_CHOICE

PC_ENABLED="false"
case "$PC_CHOICE" in
    s|S|sim|SIM) PC_ENABLED="true" ;;
esac

# Gera config.json
echo
echo -e "${BLUE}Gerando config.json...${NC}"

cat > "$CONFIG_DIR/config.json" << EOF
{
  "MODE": "TOTK puro (sem LLM)",
  "ALLOW_FROM": ["$MEU_NUM"],
  "STORAGE_PATH": "$HOME/.linkbot/data.db",
  "SESSION_PATH": "$HOME/.linkbot/session.sqlite",
  "ENABLE_PC_CONTROL": $PC_ENABLED
}
EOF

echo -e "${GREEN}OK${NC}"

echo
echo -e "${GREEN}============================================================"
echo "   Personalizacao concluida!"
echo
echo "   Numero autorizado: $MEU_NUM"
echo "   Controle PC: $PC_ENABLED"
echo
echo "   Proximo: ./menu.sh"
echo "     [1] Iniciar bot (primeira vez vai pedir QR)"
echo "============================================================${NC}"
