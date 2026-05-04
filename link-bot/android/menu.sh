#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  Link Bot TOTK - Menu Principal (Termux Android)
# ============================================================

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
KIT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
LINKBOT_DIR="$HOME/.linkbot"

if ! command -v python >/dev/null 2>&1; then
    echo -e "${RED}Python nao encontrado. Rode  ./instalar-atualizar.sh  primeiro.${NC}"
    exit 1
fi

pause_continue() {
    echo
    read -p "  [Enter pra voltar ao menu]" _
}

show_menu() {
    clear
    echo -e "${BLUE}"
    echo "============================================================"
    echo "             LINK BOT TOTK - MENU"
    echo "           Bot pessoal de WhatsApp"
    echo "============================================================"
    echo -e "${NC}"
    echo -e "  ${CYAN}===== ROTINA DIARIA =====${NC}"
    echo "   [1] Iniciar bot                  <- mais usado"
    echo "   [2] Re-parear WhatsApp (reseta QR)"
    echo "   [3] Status / config atual"
    echo
    echo -e "  ${CYAN}===== MANUTENCAO =====${NC}"
    echo "   [4] Atualizar dependencias"
    echo "   [5] Reaplicar personalizacao (numero/PC)"
    echo "   [6] Editar config.json (nano)"
    echo "   [7] Listar arquivos da pasta .linkbot"
    echo
    echo -e "  ${CYAN}===== INFO =====${NC}"
    echo "   [V] Versao Python e libs"
    echo "   [S] Listar skills do bot"
    echo "   [B] Backup pra /sdcard/"
    echo "   [W] Wake-lock (anti-MIUI)"
    echo
    echo "   [0] Sair"
    echo
    echo "============================================================"
}

while true; do
    show_menu
    read -p "  Escolha uma opcao: " ESCOLHA

    case "${ESCOLHA,,}" in
        1)
            clear
            echo -e "${GREEN}============================================================"
            echo "  LINK ESTA ACORDANDO..."
            echo "============================================================${NC}"
            echo "  Primeira vez? Aparece QR no terminal."
            echo "  Pra parar: Ctrl+C"
            echo
            termux-wake-lock 2>/dev/null
            cd "$KIT_DIR"
            python -m bot.main
            cd "$SCRIPT_DIR"
            termux-wake-unlock 2>/dev/null
            pause_continue
            ;;

        2)
            clear
            echo -e "${YELLOW}Resetar sessao do WhatsApp (vai pedir QR de novo)?${NC}"
            read -p "  Tem certeza? [s/N]: " CONFIRMA
            if [ "${CONFIRMA,,}" = "s" ]; then
                cd "$KIT_DIR"
                python -m bot.main --reset
                cd "$SCRIPT_DIR"
            fi
            pause_continue
            ;;

        3)
            clear
            echo -e "${BLUE}============================================================"
            echo "  STATUS / CONFIG"
            echo "============================================================${NC}"
            if [ -f "$KIT_DIR/config/config.json" ]; then
                echo "  Config atual:"
                echo "  ---"
                cat "$KIT_DIR/config/config.json"
                echo "  ---"
            else
                echo -e "${RED}  Config NAO encontrado. Rode personalizar.sh.${NC}"
            fi
            echo
            if [ -f "$LINKBOT_DIR/session.sqlite" ]; then
                echo "  Sessao do WhatsApp: PAREADA"
            else
                echo "  Sessao do WhatsApp: NAO PAREADA"
            fi
            if [ -f "$LINKBOT_DIR/data.db" ]; then
                echo "  Banco de dados: existe ($(du -h "$LINKBOT_DIR/data.db" | cut -f1))"
            else
                echo "  Banco de dados: ainda nao criado"
            fi
            pause_continue
            ;;

        4)
            clear
            echo -e "${BLUE}Atualizando dependencias...${NC}"
            pip install --upgrade neonize 'qrcode[pil]' httpx psutil
            pause_continue
            ;;

        5)
            bash "$SCRIPT_DIR/personalizar.sh"
            pause_continue
            ;;

        6)
            if [ -f "$KIT_DIR/config/config.json" ]; then
                command -v nano >/dev/null 2>&1 || pkg install -y nano >/dev/null 2>&1
                nano "$KIT_DIR/config/config.json"
            else
                echo -e "${RED}Config nao existe. Rode personalizar.sh primeiro.${NC}"
                pause_continue
            fi
            ;;

        7)
            clear
            echo -e "${BLUE}Conteudo de $LINKBOT_DIR:${NC}"
            ls -la "$LINKBOT_DIR" 2>/dev/null || echo "(pasta ainda nao existe)"
            pause_continue
            ;;

        v)
            clear
            echo "Python: $(python --version)"
            echo
            echo "Libs do bot:"
            for lib in neonize qrcode httpx psutil; do
                ver=$(pip show $lib 2>/dev/null | grep "^Version" | awk '{print $2}')
                if [ -n "$ver" ]; then
                    echo "  $lib: $ver"
                else
                    echo "  $lib: nao instalado"
                fi
            done
            echo
            echo "FFmpeg: $(ffmpeg -version 2>/dev/null | head -1 || echo 'nao instalado')"
            pause_continue
            ;;

        s)
            clear
            echo -e "${BLUE}Skills disponiveis:${NC}"
            ls -1 "$KIT_DIR/bot/skills/"*.py 2>/dev/null | grep -v "__" | xargs -n 1 basename
            echo
            echo "Total: $(ls -1 "$KIT_DIR/bot/skills/"*.py 2>/dev/null | grep -v "__" | wc -l)"
            pause_continue
            ;;

        b)
            clear
            BTS=$(date +%Y%m%d-%H%M%S)
            BACKUP_DIR="/sdcard/backup-linkbot-$BTS"
            echo -e "${BLUE}Criando backup em: $BACKUP_DIR${NC}"
            mkdir -p "$BACKUP_DIR"
            cp -r "$LINKBOT_DIR" "$BACKUP_DIR/linkbot-data" 2>/dev/null
            cp -r "$KIT_DIR/config" "$BACKUP_DIR/config" 2>/dev/null
            if [ -d "$BACKUP_DIR" ]; then
                echo -e "${GREEN}Backup completo.${NC}"
            else
                echo -e "${RED}Falhou. Concedeu permissao de storage? (termux-setup-storage)${NC}"
            fi
            pause_continue
            ;;

        w)
            clear
            termux-wake-lock 2>/dev/null && \
                echo -e "${GREEN}Wake-lock ATIVADO. CPU nao vai dormir.${NC}" || \
                echo -e "${RED}Falhou. termux-api instalado?${NC}"
            pause_continue
            ;;

        0|q|sair|"")
            clear
            echo -e "${GREEN}"
            echo "  Boa jornada, aventureiro. Hyrule te aguarda. 🗡️🔱"
            echo -e "${NC}"
            sleep 1
            exit 0
            ;;

        *)
            echo -e "${RED}  Opcao invalida.${NC}"
            sleep 1
            ;;
    esac
done
