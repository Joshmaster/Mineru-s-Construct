#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  Link Bot TOTK - Instalar / Atualizar (Termux Android)
# ============================================================

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}"
echo "============================================================"
echo "   LINK BOT TOTK - Instalar / Atualizar"
echo "============================================================"
echo -e "${NC}"

# --- 1) Termux base ---
echo -e "${BLUE}[1/4] Atualizando Termux...${NC}"
pkg update -y >/dev/null 2>&1
pkg upgrade -y >/dev/null 2>&1
echo -e "${GREEN}OK${NC}"

# --- 2) Pacotes do sistema ---
echo
echo -e "${BLUE}[2/4] Instalando dependencias do sistema...${NC}"
NEEDED="python python-pip ffmpeg termux-api nano"
for p in $NEEDED; do
    if ! pkg list-installed 2>/dev/null | grep -q "^$p/"; then
        echo "  Instalando $p..."
        pkg install -y "$p" >/dev/null 2>&1 || pkg install -y "$p"
    fi
done
echo -e "${GREEN}OK${NC}"

# --- 3) Storage ---
if [ ! -d "$HOME/storage" ]; then
    echo
    echo -e "${BLUE}[3/4] Configurando acesso ao storage...${NC}"
    echo -e "${YELLOW}Aceita o pedido de permissao quando aparecer.${NC}"
    termux-setup-storage
    sleep 2
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${BLUE}[3/4] Storage ja configurado.${NC} ${GREEN}OK${NC}"
fi

# --- 4) Pip libs ---
echo
echo -e "${BLUE}[4/4] Instalando libs Python (neonize, qrcode, httpx, psutil)...${NC}"
echo -e "${YELLOW}(pode levar 3-8 min na primeira vez)${NC}"
echo
pip install --upgrade pip --quiet
pip install --upgrade neonize 'qrcode[pil]' httpx psutil

echo
echo -e "${GREEN}============================================================"
echo "   Instalacao completa!"
echo
echo "   Proximo: ./personalizar.sh"
echo "============================================================${NC}"
