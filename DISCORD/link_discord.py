import discord
import asyncio
import os
import re
import json
import sys
import threading
import aiohttp as aiohttp_client
from datetime import datetime, timedelta, timezone
from aiohttp import web

_log_lock = threading.Lock()

BRT = timezone(timedelta(hours=-3))

# Força UTF-8 no stdout/stderr (Windows usa cp1252 por padrão — quebra emojis)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).parent.parent))
try:
    from hyrule_env import DISCORD_TOKEN as TOKEN, OPENROUTER_KEYS, GROQ_KEYS
except ImportError:
    TOKEN = ""
    OPENROUTER_KEYS = []
    GROQ_KEYS = []

OLLAMA_URL   = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:7b"
MODELOS_FALLBACK = [
    {"url": "https://openrouter.ai/api/v1/chat/completions",   "model": "google/gemma-4-31b-it:free",               "keys": OPENROUTER_KEYS},
    {"url": "https://api.groq.com/openai/v1/chat/completions", "model": "meta-llama/llama-4-scout-17b-16e-instruct","keys": GROQ_KEYS},
    {"url": "https://openrouter.ai/api/v1/chat/completions",   "model": "meta-llama/llama-3.3-70b-instruct:free",   "keys": OPENROUTER_KEYS},
    {"url": "https://openrouter.ai/api/v1/chat/completions",   "model": "nvidia/nemotron-3-super-120b-a12b:free",   "keys": OPENROUTER_KEYS},
]
_fallback_modelo_idx = 0
_fallback_key_idx    = 0

USUARIOS = {
    "OWNER": DISCORD_OWNER_ID,
    "USER2": DISCORD_USER2_ID
}

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
LOG_FILE      = os.path.join(BASE_DIR, "discord.log")
FILES_DIR     = os.path.join(BASE_DIR, "files")
HISTORY_DIR   = os.path.join(BASE_DIR, "history")
RECEIVED_DIR  = os.path.join(BASE_DIR, "received")   # anexos recebidos do Discord, baixados imediatamente
RECEIVED_META = os.path.join(BASE_DIR, "received_files.json")   # metadados persistidos
USER_CTX_FILE = os.path.join(BASE_DIR, "user_context.json")     # contexto por usuário
PERSONA_FILE  = os.path.join(BASE_DIR, "..", "OPENCODE", "roaming", "LINK_PERSONA.md")
os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)
os.makedirs(RECEIVED_DIR, exist_ok=True)

buffer = []  # ultimas 100 mensagens em memoria

# Historico de conversa por usuario (para contexto)
historico_ia = {}

# ── Contexto persistente por usuário ─────────────────────────────────────────
# Estrutura: {autor: {last_file: {local_path, nome}, last_pedido: str, last_action: str}}
_user_ctx: dict[str, dict] = {}


def _carregar_ctx():
    global _user_ctx
    if os.path.exists(USER_CTX_FILE):
        try:
            _user_ctx = json.load(open(USER_CTX_FILE, encoding="utf-8"))
        except Exception:
            _user_ctx = {}

def _salvar_ctx():
    try:
        json.dump(_user_ctx, open(USER_CTX_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass

def _set_ctx(autor: str, **kwargs):
    if autor not in _user_ctx:
        _user_ctx[autor] = {}
    _user_ctx[autor].update(kwargs)
    _salvar_ctx()

def _get_ctx(autor: str) -> dict:
    return _user_ctx.get(autor, {})

_carregar_ctx()  # carrega ao iniciar


# ── Metadados de arquivos recebidos ──────────────────────────────────────────
def _registrar_recebido(autor: str, nome: str, url: str):
    """Salva metadado (URL) do arquivo recebido — download só acontece quando pedido."""
    dados = {}
    if os.path.exists(RECEIVED_META):
        try:
            dados = json.load(open(RECEIVED_META, encoding="utf-8"))
        except Exception:
            pass
    if autor not in dados:
        dados[autor] = []
    dados[autor].append({
        "nome": nome,
        "url":  url,
        "ts":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    dados[autor] = dados[autor][-50:]  # mantém últimos 50 por usuário
    json.dump(dados, open(RECEIVED_META, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def _ultimo_arquivo_recebido(autor: str) -> dict | None:
    """Retorna metadado do último arquivo recebido (JSON persistido — sobrevive restart)."""
    if os.path.exists(RECEIVED_META):
        try:
            dados = json.load(open(RECEIVED_META, encoding="utf-8"))
            arquivos = dados.get(autor, [])
            if arquivos:
                return arquivos[-1]  # {"nome", "url", "ts"}
        except Exception:
            pass
    return None


def _history_file(autor: str) -> str:
    safe = autor.replace("/", "_").replace("\\", "_")
    return os.path.join(HISTORY_DIR, f"{safe}.json")


def carregar_historico(autor: str) -> list:
    path = _history_file(autor)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def salvar_historico(autor: str, historico: list):
    path = _history_file(autor)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)

# Cache de usuarios que enviaram mensagens (nome -> objeto user)
usuarios_cache = {}

# Arquivo de IDs persistidos
USERS_FILE = os.path.join(BASE_DIR, "usuarios_extra.json")


def salvar_usuario(nome: str, user_id: int):
    dados = {}
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, encoding="utf-8") as f:
            dados = json.load(f)
    dados[nome.lower()] = user_id
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2)


def carregar_usuarios_extra() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, encoding="utf-8") as f:
        return json.load(f)


from pathlib import Path as _Path
_NAV_STATE_FILE = _Path(BASE_DIR) / ".." / "nav_state.json"

def _carregar_nav_state(autor: str) -> str:
    """Retorna string com pasta atual + conteúdo real para injetar no prompt."""
    try:
        data = json.loads(_NAV_STATE_FILE.read_text(encoding="utf-8"))
        entrada = data.get(autor, None)
        if not entrada:
            return ""
        # Suporte ao formato antigo (string) e novo (dict)
        if isinstance(entrada, str):
            pasta = entrada
            itens: list[str] = []
        else:
            pasta = entrada.get("pasta", "")
            itens = entrada.get("itens", [])
        if not pasta:
            return ""
        bloco = f"\n\n---\n[CONTEXTO DE NAVEGACAO NO PC]\nPasta atual: {pasta}\n"
        if itens:
            bloco += "Conteudo (nomes exatos como aparecem no PC):\n"
            bloco += "\n".join(f"  - {nome}" for nome in itens)
            bloco += "\n"
        bloco += (
            "REGRA CRITICA: Se o usuario mencionar qualquer nome que aparece na lista acima, "
            "use o nome EXATAMENTE como esta listado, sem traduzir, corrigir ortografia ou interpretar. "
            "Trate como pedido de navegacao/envio de arquivo e use [SHEIKAH_SLATE: <acao> <nome_exato>]."
        )
        return bloco
    except Exception:
        pass
    return ""


def carregar_persona(ultima_resposta: str = "", autor: str = "") -> str:
    base = "Voce e Link. Responda em portugues do Brasil de forma natural e descontraida."
    try:
        with open(PERSONA_FILE, encoding="utf-8") as f:
            base = f.read()
    except Exception:
        pass
    if ultima_resposta:
        base += f"\n\n---\nSua ultima resposta foi: \"{ultima_resposta}\"\nNAO comece esta resposta da mesma forma."
    if autor:
        base += _carregar_nav_state(autor)
    return base


def _nome_display(username: str) -> str:
    """Retorna o nome amigavel do usuario (ex: OWNER, USER2) ou o username Discord."""
    # Busca pelo cache inverso: username Discord -> nome amigavel
    for nome_key, uid in USUARIOS.items():
        cached = usuarios_cache.get(nome_key.lower())
        if cached and cached.name.lower() == username.lower():
            return nome_key
    # Busca nos extras
    extras = carregar_usuarios_extra()
    for nome_extra, uid in extras.items():
        cached = usuarios_cache.get(nome_extra)
        if cached and cached.name.lower() == username.lower():
            return nome_extra.capitalize()
    return username


async def responder_com_ia(autor: str, mensagem: str) -> str:
    """Cloud primeiro (melhor persona), qwen local como último recurso."""
    global _fallback_modelo_idx, _fallback_key_idx

    if autor not in historico_ia:
        historico_ia[autor] = carregar_historico(autor)

    nome_display = _nome_display(autor)
    historico_ia[autor].append({"role": "user", "content": f"[Mensagem de {nome_display}]: {mensagem}"})
    if len(historico_ia[autor]) > 20:
        historico_ia[autor] = historico_ia[autor][-20:]

    ultima_resposta = ""
    for entry in reversed(historico_ia[autor]):
        if entry["role"] == "assistant":
            ultima_resposta = entry["content"][:120]
            break

    system = carregar_persona(ultima_resposta, autor)
    msgs   = [{"role": "system", "content": system}, *historico_ia[autor]]

    # ── 1. Cloud (gemma/llama/groq) — melhor para persona ────────────────────
    tentados = 0
    tentativas_total = sum(len(m["keys"]) for m in MODELOS_FALLBACK)
    while tentados < tentativas_total:
        modelo = MODELOS_FALLBACK[_fallback_modelo_idx % len(MODELOS_FALLBACK)]
        chave  = modelo["keys"][_fallback_key_idx % len(modelo["keys"])]
        try:
            async with aiohttp_client.ClientSession() as session:
                is_groq = "groq.com" in modelo["url"]
                headers = {"Authorization": f"Bearer {chave}", "Content-Type": "application/json"}
                if is_groq:
                    headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json",
                                    "Origin": "https://console.groq.com", "Referer": "https://console.groq.com/"})
                async with session.post(
                    modelo["url"], headers=headers,
                    json={"model": modelo["model"], "messages": msgs,
                          "max_tokens": 256, "temperature": 0.85},
                    timeout=aiohttp_client.ClientTimeout(total=12)
                ) as resp:
                    if resp.status in (401, 403):
                        _fallback_modelo_idx += 1; _fallback_key_idx = 0
                        tentados += len(modelo["keys"]); continue
                    if resp.status in (429, 503, 529):
                        _fallback_key_idx += 1
                        if _fallback_key_idx % len(modelo["keys"]) == 0:
                            _fallback_modelo_idx += 1
                        tentados += 1; continue
                    data = await resp.json()
                    resposta = data["choices"][0]["message"]["content"].strip()
                    primeira = resposta.split('\n')[0].lower().lstrip('*- ')
                    if any(primeira.startswith(rs) for rs in _REASON_STARTS):
                        print(f"[IA] {modelo['model']} CoT vazou, pulando...", flush=True)
                        _fallback_modelo_idx += 1; _fallback_key_idx = 0
                        tentados += len(modelo["keys"]); continue
                    print(f"[IA] fallback {modelo['model']}: {resposta[:60]}", flush=True)
                    historico_ia[autor].append({"role": "assistant", "content": resposta})
                    salvar_historico(autor, historico_ia[autor])
                    return resposta
        except Exception as e:
            print(f"[IA] fallback {modelo['model']} erro: {e}", flush=True)
            _fallback_key_idx += 1
            if _fallback_key_idx % len(modelo["keys"]) == 0:
                _fallback_modelo_idx += 1
            tentados += 1

    # ── 2. Último recurso: qwen local ────────────────────────────────────────
    try:
        async with aiohttp_client.ClientSession() as session:
            async with session.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "stream": False,
                      "options": {"temperature": 0.85, "top_p": 0.9,
                                  "repeat_penalty": 1.1, "num_predict": 120},
                      "messages": msgs},
                timeout=aiohttp_client.ClientTimeout(total=30)
            ) as resp:
                data = await resp.json()
                resposta = data.get("message", {}).get("content", "").strip()
                if resposta:
                    print(f"[IA] qwen local (fallback final): {resposta[:60]}", flush=True)
                    historico_ia[autor].append({"role": "assistant", "content": resposta})
                    salvar_historico(autor, historico_ia[autor])
                    return resposta
    except Exception as e:
        print(f"[IA] qwen local também falhou: {e}", flush=True)

    return "..."

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

client = discord.Client(intents=intents)


_TAG_RE      = re.compile(r'\[SHEIKAH_SLATE[^\]]*\]', re.IGNORECASE)
_TRIFORCE_RE = re.compile(r'\[TRIFORCE:\s*(.*?)\]', re.IGNORECASE | re.DOTALL)
_THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL | re.IGNORECASE)

# Prefixos que indicam raciocínio interno vazado (modelos de reasoning)
_REASON_STARTS = (
    "okay,", "ok,", "ok!", "let me", "first,", "first,", "looking at",
    "i need to", "wait,", "alright,", "so,", "now,", "hmm", "well,",
    "let's", "let me unpack", "i must", "i should", "in this case",
    "josh is asking", "the user", "from the", "according to",
    "important:", "note:", "task description", "so i should",
)

def sanitizar(texto: str) -> str:
    """Remove tags internas, think blocks e chain-of-thought vazado."""
    limpo = _THINK_RE.sub('', texto)        # <think>...</think>
    limpo = _TAG_RE.sub('', limpo)          # [SHEIKAH_SLATE: ...]
    limpo = _TRIFORCE_RE.sub('', limpo)     # [TRIFORCE: ...]

    # Se o texto começa com raciocínio, tenta extrair só a resposta real
    primeira = limpo.strip().split('\n')[0].lower().lstrip('*- ')
    if any(primeira.startswith(rs) for rs in _REASON_STARTS):
        # Tenta separar por parágrafo duplo (\n\n)
        paragrafos = [p.strip() for p in limpo.strip().split('\n\n') if p.strip()]
        # Pega o último parágrafo que NÃO começa com CoT e é curto (< 400 chars)
        candidato = None
        for p in reversed(paragrafos):
            p_lower = p.lower().lstrip('*- ')
            if not any(p_lower.startswith(rs) for rs in _REASON_STARTS) and len(p) < 400:
                candidato = p
                break
        if candidato:
            limpo = candidato
        elif paragrafos:
            # Se todos começam com CoT, pega o último que seja curto
            curtos = [p for p in paragrafos if len(p) < 400]
            limpo = curtos[-1] if curtos else paragrafos[-1]

    linhas = [l for l in limpo.splitlines() if l.strip()]
    return '\n'.join(linhas).strip()


def registrar(direcao: str, de: str, para: str, msg: str, anexos: list = None):
    hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {
        "time": hora,
        "direction": direcao,
        "from": de,
        "to": para,
        "msg": msg,
        "anexos": anexos or []
    }
    buffer.append(entry)
    if len(buffer) > 100:
        buffer.pop(0)

    linha = f"[{hora}] [{direcao}] {de} -> {para}: {msg}"
    if anexos:
        nomes = ", ".join(a["nome"] for a in anexos)
        linha += f" [ANEXO: {nomes}]"
    linha += "\n"

    with _log_lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(linha)
        print(linha, end="", flush=True)


def resolver_usuario(nome: str):
    """Resolve nome para chave do USUARIOS dict ou retorna None."""
    return next((k for k in USUARIOS if k.lower() == nome.lower()), None)


async def buscar_user(nome: str):
    """Busca user object: primeiro em USUARIOS, depois no cache, depois no arquivo persistido."""
    nome_key = resolver_usuario(nome)
    if nome_key:
        return await client.fetch_user(USUARIOS[nome_key])
    cached = usuarios_cache.get(nome.lower())
    if cached:
        return cached
    # Tenta carregar do arquivo persistido
    extras = carregar_usuarios_extra()
    uid = extras.get(nome.lower())
    if uid:
        try:
            user = await client.fetch_user(uid)
            usuarios_cache[nome.lower()] = user
            return user
        except Exception:
            pass
    return None


@client.event
async def on_ready():
    print(f"\n  Link Discord Online")
    print(f"  Bot: {client.user}")
    print(f"  HTTP: http://localhost:7331")
    print(f"  Log:  {LOG_FILE}")
    print(f"  Files: {FILES_DIR}")
    print(f"  Escutando DMs...\n")
    # Pre-carrega usuarios extras persistidos no cache
    extras = carregar_usuarios_extra()
    for nome, uid in extras.items():
        try:
            user = await client.fetch_user(uid)
            usuarios_cache[nome] = user
            print(f"  [cache] {nome} -> {user.name} ({uid})")
        except Exception:
            pass


@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if not isinstance(message.channel, discord.DMChannel):
        return

    autor   = message.author.name
    p_lower = (message.content or "").lower()

    # ── FASE 1: Captura passiva — só metadados, sem download ─────────────────
    # Download só acontece quando o usuário pedir explicitamente ("salva no desktop")
    # Isso evita desperdício de disco e mantém o controle com o usuário
    anexos_meta = []
    for att in message.attachments:
        meta = {
            "nome": att.filename,
            "url":  att.url,
            "tamanho_mb": round(att.size / 1024 / 1024, 2),
            "ts":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        anexos_meta.append(meta)
        _registrar_recebido(autor, att.filename, att.url)  # persiste só URL
        print(f"[RECEBIDO] {autor}: {att.filename} (metadado salvo)", flush=True)

    registrar("IN", autor, "Link", message.content,
              [{"nome": a["nome"], "url": a["url"]} for a in anexos_meta])
    usuarios_cache[autor.lower()] = message.author
    salvar_usuario(autor, message.author.id)

    # ── Comandos especiais (sem LLM) ─────────────────────────────────────────
    import unicodedata as _ud
    def _norm(t): return ''.join(c for c in _ud.normalize('NFD', t.lower()) if _ud.category(c) != 'Mn')
    _p_norm = _norm(message.content or "")

    if re.search(r'!link\s+acord', _p_norm):
        await message.channel.send("acordando tudo... um segundo")
        registrar("OUT", "Link", autor, "acordando tudo... um segundo")
        registrar("SYS", "Bot", "Claude", "[SHEIKAH_SLATE-PEDIDO] acorde sistema completo")
        return

    # ── TRIFORCE: escalação direta, sem passar pelo LLM ──────────────────────
    _txt = (message.content or "").strip()
    _txt_norm = _p_norm.strip()
    if re.match(r'^triforce\b', _txt_norm):
        # Extrai o pedido (tudo depois de "TRIFORCE")
        pedido_tf = re.sub(r'^triforce\s*', '', _txt, flags=re.IGNORECASE).strip()
        if not pedido_tf:
            pedido_tf = f"{autor} quer falar com a triforce"
        await message.channel.send("✨ acionando triforce...")
        registrar("OUT", "Link", autor, "acionando triforce...")
        registrar("SYS", "Bot", "Claude", f"[TRIFORCE-PEDIDO] {pedido_tf}")
        return

    # Atualiza contexto: último arquivo recebido (apenas metadado)
    if anexos_meta:
        _set_ctx(autor, last_file={
            "nome": anexos_meta[-1]["nome"],
            "url":  anexos_meta[-1]["url"],
        })

    # ── Retry — re-executa último pedido de arquivo (keyword confiável) ──────
    _kw_retry = ["tenta novamente", "tenta de novo", "de novo", "again", "retry",
                 "nao funcionou", "não funcionou", "falhou", "faz novamente",
                 "faça novamente", "refaz", "refaça", "novamente", "repete"]
    quer_retry = any(kw in p_lower for kw in _kw_retry)

    if quer_retry and not anexos_meta:
        from datetime import datetime as _dt
        ts = _dt.now().strftime('%H%M%S')
        arquivos_recentes = []
        if os.path.exists(RECEIVED_META):
            try:
                dados_meta = json.load(open(RECEIVED_META, encoding="utf-8"))
                arquivos_recentes = dados_meta.get(autor, [])[-3:]
            except Exception:
                pass
        if arquivos_recentes:
            for a in arquivos_recentes:
                registrar("SYS", "Bot", "Claude",
                          f"[SHEIKAH_SLATE-PEDIDO] salva no desktop URL:{a['url']} nome:{a['nome']} [retry:{ts}]")
            await message.channel.send("tentando de novo...")
            registrar("OUT", "Link", autor, "tentando de novo...")
            return
        ultimo_pedido = _get_ctx(autor).get("last_pedido")
        if ultimo_pedido:
            registrar("SYS", "Bot", "Claude",
                      f"[SHEIKAH_SLATE-PEDIDO] {ultimo_pedido} [retry:{ts}]")
            await message.channel.send("tentando de novo...")
            registrar("OUT", "Link", autor, "tentando de novo...")
            return

    # ── PC → Discord (frase explícita — não ambígua) ──────────────────────────
    _kw_enviar = ["pro discord", "para o discord", "no discord",
                  "manda pro discord", "envia pro discord", "passa pro discord"]
    quer_enviar = any(kw in p_lower for kw in _kw_enviar) and not anexos_meta
    if quer_enviar:
        # Extrai nome do arquivo do pedido (se mencionado)
        nome_match = re.search(
            r'(?:o arquivo|o|a foto|a imagem|o print|arquivo)\s+([\w\-\.]+\.[\w]{2,5})',
            p_lower)
        nome_arq = nome_match.group(1) if nome_match else None
        pedido = f"envia pro discord arquivo:{nome_arq}" if nome_arq else "envia pro discord o ultimo arquivo do Desktop"
        _set_ctx(autor, last_pedido=pedido, last_action="enviar_discord")
        registrar("SYS", "Bot", "Claude", f"[SHEIKAH_SLATE-PEDIDO] {pedido}")
        await message.channel.send("Procurando o arquivo aqui...")
        registrar("OUT", "Link", autor, "Procurando o arquivo aqui...")
        return

    # ── Fluxo normal: LLM responde ────────────────────────────────────────────
    # Inclui info dos anexos na mensagem para o LLM decidir naturalmente
    mensagem_llm = message.content or ""
    if anexos_meta:
        for a in anexos_meta:
            mensagem_llm += f"\n[ARQUIVO: {a['nome']} | URL: {a['url']}]"

    async with message.channel.typing():
        resposta = await responder_com_ia(autor, mensagem_llm)

    claude_match = re.search(r'\[SHEIKAH_SLATE:\s*(.*?)\]', resposta, re.IGNORECASE | re.DOTALL)
    if claude_match:
        pedido = claude_match.group(1).strip()
        _set_ctx(autor, last_pedido=pedido, last_action="llm")
        registrar("SYS", "Bot", "Claude", f"[SHEIKAH_SLATE-PEDIDO] {pedido}")

    triforce_match = _TRIFORCE_RE.search(resposta)
    if triforce_match:
        pedido_tf = triforce_match.group(1).strip()
        registrar("SYS", "Bot", "Claude", f"[TRIFORCE-PEDIDO] {pedido_tf}")

    resposta_limpa = sanitizar(resposta)
    if resposta_limpa:
        await message.channel.send(resposta_limpa)
        registrar("OUT", "Link", autor, resposta_limpa)


# --- HTTP API ---

async def rota_send(request):
    try:
        data = await request.json()
        nome = data.get("to", "").strip()
        msg  = data.get("msg", "").strip()

        if not nome or not msg:
            return web.json_response({"ok": False, "error": "Campos 'to' e 'msg' obrigatorios"}, status=400)

        msg = sanitizar(msg)
        if not msg:
            return web.json_response({"ok": True, "skipped": "mensagem vazia apos strip"})

        # ✨ é exclusivo do /triforce — strip aqui para o LLM não poder fingir
        while msg.startswith("✨"):
            msg = msg.lstrip("✨").strip()
        if not msg:
            return web.json_response({"ok": True, "skipped": "mensagem vazia apos strip"})

        user = await buscar_user(nome)
        if not user:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)

        await user.send(msg)
        registrar("OUT", "Link", user.name, msg)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_triforce(request):
    """Igual /send mas garante prefixo ✨ — identifica resposta do agente de código."""
    try:
        data = await request.json()
        nome = data.get("to", "").strip()
        msg  = data.get("msg", "").strip()

        if not nome or not msg:
            return web.json_response({"ok": False, "error": "Campos 'to' e 'msg' obrigatorios"}, status=400)

        if not msg.startswith("✨"):
            msg = f"✨ {msg}"
        msg = sanitizar(msg)

        user = await buscar_user(nome)
        if not user:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)

        await user.send(msg)
        registrar("OUT", "Link", user.name, msg)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_send_file(request):
    """
    Envia um arquivo pelo Discord DM.
    Body: {"to": "OWNER", "file": "caminho/absoluto", "msg": "opcional"}
    """
    try:
        data     = await request.json()
        nome     = data.get("to", "").strip()
        filepath = data.get("file", "").strip()
        msg      = data.get("msg", "")

        user = await buscar_user(nome)
        if not user:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)

        if not os.path.exists(filepath):
            return web.json_response({"ok": False, "error": f"Arquivo nao encontrado: {filepath}"}, status=404)

        tamanho_mb = os.path.getsize(filepath) / 1024 / 1024
        if tamanho_mb > 8:
            return web.json_response({
                "ok": False,
                "error": f"arquivo_grande",
                "tamanho_mb": round(tamanho_mb, 1),
                "limite_mb": 8
            }, status=413)

        await user.send(content=msg or None, file=discord.File(filepath))

        nome_arquivo = os.path.basename(filepath)
        registrar("OUT", "Link", user.name, f"[ARQUIVO: {nome_arquivo}] {msg}".strip())
        return web.json_response({"ok": True, "arquivo": nome_arquivo})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_download(request):
    """
    Baixa um arquivo de uma URL do Discord para a pasta files/.
    Body: {"url": "https://...", "filename": "nome.ext"}
    Retorna: {"ok": true, "path": "caminho/local"}
    """
    try:
        data     = await request.json()
        url      = data.get("url", "").strip()
        filename = data.get("filename", "").strip()

        if not url or not filename:
            return web.json_response({"ok": False, "error": "Campos 'url' e 'filename' obrigatorios"}, status=400)

        # Sanitiza nome do arquivo
        filename = os.path.basename(filename)
        dest = os.path.join(FILES_DIR, filename)

        async with aiohttp_client.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return web.json_response({"ok": False, "error": f"Erro ao baixar: HTTP {resp.status}"}, status=500)
                with open(dest, "wb") as f:
                    f.write(await resp.read())

        tamanho = round(os.path.getsize(dest) / 1024 / 1024, 2)
        print(f"[DOWNLOAD] {filename} ({tamanho} MB) -> {dest}\n", flush=True)
        return web.json_response({"ok": True, "path": dest, "tamanho_mb": tamanho})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_chat(request):
    """Console local — processa mensagem e retorna resposta sem enviar ao Discord."""
    try:
        data = await request.json()
        autor = data.get("from", "OWNER").strip()
        msg   = data.get("msg", "").strip()
        if not msg:
            return web.json_response({"ok": False, "error": "msg vazia"}, status=400)
        autor_key = autor.lower().replace(" ", "_")
        registrar("IN", autor, "Link", f"[CONSOLE] {msg}")
        resposta = await responder_com_ia(autor_key, msg)

        # Processa SHEIKAH_SLATE igual ao fluxo do Discord
        claude_match = re.search(r'\[SHEIKAH_SLATE:\s*(.*?)\]', resposta, re.IGNORECASE | re.DOTALL)
        if claude_match:
            pedido = claude_match.group(1).strip()
            _set_ctx(autor_key, last_pedido=pedido, last_action="llm")
            registrar("SYS", "Bot", "Claude", f"[SHEIKAH_SLATE-PEDIDO] {pedido}")

        triforce_match = _TRIFORCE_RE.search(resposta)
        if triforce_match:
            pedido_tf = triforce_match.group(1).strip()
            registrar("SYS", "Bot", "Claude", f"[TRIFORCE-PEDIDO] {pedido_tf}")

        resposta_limpa = sanitizar(resposta)
        registrar("OUT", "Link", autor, f"[CONSOLE] {resposta_limpa}")
        return web.json_response({"ok": True, "resposta": resposta_limpa})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_messages(request):
    limit = int(request.rel_url.query.get("limit", 20))
    return web.json_response(buffer[-limit:])


async def rota_history(request):
    try:
        nome  = request.rel_url.query.get("user", "")
        limit = int(request.rel_url.query.get("limit", 20))

        nome_key = resolver_usuario(nome)
        if not nome_key:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)

        user    = await client.fetch_user(USUARIOS[nome_key])
        channel = await user.create_dm()

        msgs = []
        async for m in channel.history(limit=limit, oldest_first=False):
            anexos = [{"nome": a.filename, "url": a.url, "tamanho_mb": round(a.size / 1024 / 1024, 2)} for a in m.attachments]
            msgs.append({
                "id":      str(m.id),
                "autor":   m.author.name,
                "meu":     m.author == client.user,
                "conteudo": m.content,
                "data":    m.created_at.astimezone(BRT).strftime("%d/%m/%Y %H:%M:%S"),
                "anexos":  anexos
            })

        return web.json_response({"ok": True, "usuario": nome_key, "mensagens": msgs})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_delete(request):
    try:
        data  = await request.json()
        nome  = data.get("to", "").strip()
        count = data.get("count", None)
        ids   = data.get("ids", None)

        nome_key = resolver_usuario(nome)
        if not nome_key:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)

        user    = await client.fetch_user(USUARIOS[nome_key])
        channel = await user.create_dm()

        deletadas = 0
        erros = []

        if ids:
            for mid in ids:
                try:
                    msg = await channel.fetch_message(int(mid))
                    if msg.author == client.user:
                        await msg.delete()
                        deletadas += 1
                        await asyncio.sleep(0.5)
                except discord.NotFound:
                    erros.append(f"ID {mid} nao encontrado")
                except discord.Forbidden:
                    erros.append(f"ID {mid} sem permissao")
                except Exception as e:
                    erros.append(f"ID {mid}: {e}")
        elif count:
            async for m in channel.history(limit=None):
                if m.author == client.user:
                    try:
                        await m.delete()
                        deletadas += 1
                        await asyncio.sleep(0.5)
                        if deletadas >= count:
                            break
                    except discord.HTTPException as e:
                        if e.status == 429:
                            await asyncio.sleep(e.retry_after if hasattr(e, "retry_after") else 5)
                        erros.append(str(e))
        else:
            return web.json_response({"ok": False, "error": "Informe 'count' ou 'ids'"}, status=400)

        return web.json_response({"ok": True, "deletadas": deletadas, "erros": erros})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_clear_history(request):
    """Limpa historico em memoria e no disco de um usuario ou de todos."""
    try:
        data = await request.json()
        user = data.get("user", "").strip()
        if user:
            historico_ia.pop(user, None)
            path = _history_file(user)
            if os.path.exists(path):
                os.remove(path)
            return web.json_response({"ok": True, "cleared": user})
        else:
            historico_ia.clear()
            import glob as _glob
            for f in _glob.glob(os.path.join(HISTORY_DIR, "*.json")):
                os.remove(f)
            return web.json_response({"ok": True, "cleared": "all"})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_edit(request):
    """Edita uma mensagem própria do bot. Body: {to, msg_id, novo_conteudo}"""
    try:
        data = await request.json()
        nome = data.get("to", "").strip()
        msg_id = int(data.get("msg_id", 0))
        novo = sanitizar(data.get("novo_conteudo", "").strip())
        if not nome or not msg_id or not novo:
            return web.json_response({"ok": False, "error": "Campos obrigatorios: to, msg_id, novo_conteudo"}, status=400)
        nome_key = resolver_usuario(nome)
        if not nome_key:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)
        user = await client.fetch_user(USUARIOS[nome_key])
        channel = await user.create_dm()
        msg = await channel.fetch_message(msg_id)
        if msg.author != client.user:
            return web.json_response({"ok": False, "error": "Nao posso editar mensagens de outros"}, status=403)
        await msg.edit(content=novo)
        registrar("OUT", "Link", user.name, f"[EDITADO] {novo}")
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_react(request):
    """Adiciona reacao a uma mensagem. Body: {to, msg_id, emoji}"""
    try:
        data = await request.json()
        nome = data.get("to", "").strip()
        msg_id = int(data.get("msg_id", 0))
        emoji = data.get("emoji", "👍").strip()
        nome_key = resolver_usuario(nome)
        if not nome_key:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)
        user = await client.fetch_user(USUARIOS[nome_key])
        channel = await user.create_dm()
        msg = await channel.fetch_message(msg_id)
        await msg.add_reaction(emoji)
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_pin(request):
    """Fixa uma mensagem. Body: {to, msg_id}"""
    try:
        data = await request.json()
        nome = data.get("to", "").strip()
        msg_id = int(data.get("msg_id", 0))
        nome_key = resolver_usuario(nome)
        if not nome_key:
            return web.json_response({"ok": False, "error": f"Usuario '{nome}' nao encontrado"}, status=404)
        user = await client.fetch_user(USUARIOS[nome_key])
        channel = await user.create_dm()
        msg = await channel.fetch_message(msg_id)
        await msg.pin()
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)}, status=500)


async def rota_status(request):
    return web.json_response({
        "online":              client.is_ready(),
        "bot":                 str(client.user) if client.is_ready() else None,
        "usuarios":            list(USUARIOS.keys()),
        "mensagens_em_buffer": len(buffer),
        "files_dir":           FILES_DIR
    })


async def start_http():
    app = web.Application()
    app.router.add_post("/send",          rota_send)
    app.router.add_post("/triforce",      rota_triforce)
    app.router.add_post("/send-file",     rota_send_file)
    app.router.add_post("/download",      rota_download)
    app.router.add_post("/delete",        rota_delete)
    app.router.add_post("/edit",          rota_edit)
    app.router.add_post("/react",         rota_react)
    app.router.add_post("/pin",           rota_pin)
    app.router.add_post("/chat",           rota_chat)
    app.router.add_get("/messages",       rota_messages)
    app.router.add_get("/history",        rota_history)
    app.router.add_get("/status",         rota_status)
    app.router.add_post("/clear-history", rota_clear_history)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 7331)
    await site.start()


async def main():
    await start_http()
    await client.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
