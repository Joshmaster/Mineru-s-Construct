#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
triforce_daemon.py — linha direta OWNER <-> Claude Code via Discord/WhatsApp.
Usa `claude --print --continue` para retomar esta sessao com contexto completo.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
TOKEN_ALERT_MINS = 120   # alertar quando restar menos que isso
TOKEN_CHECK_SECS = 1800  # checar a cada 30 minutos

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE         = Path(__file__).parent
CLAUDE_QUEUE = BASE / "claude_queue.json"
HISTORY_DIR  = BASE / "triforce_history"

if sys.platform == "win32":
    CLAUDE_EXE = BASE / "CLAUDE CODE" / "bin" / "claude.exe"
else:
    import shutil as _shutil
    _which = _shutil.which("claude")
    CLAUDE_EXE = Path(_which) if _which else Path("/usr/local/bin/claude")
HOME_DIR     = Path.home()          # cwd da sessao interativa ativa
BOT_API      = "http://localhost:7331"
WA_API       = "http://localhost:7332"
POLL_SECS    = 2
MAX_HISTORY  = 10
CLAUDE_TIMEOUT = 45  # segundos

try:
    from hyrule_env import GROQ_KEYS, WA_OWNER
except ImportError:
    GROQ_KEYS = []
    WA_OWNER  = ""
GROQ_MODELS = [
    "moonshotai/kimi-k2-instruct",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_HEADERS_BASE = {
    "Content-Type": "application/json",
    "User-Agent":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":       "application/json",
    "Origin":       "https://console.groq.com",
    "Referer":      "https://console.groq.com/",
}

SYSTEM_PROMPT = """Voce e Link, heroi de Hyrule e parceiro tecnico do OWNER (OWNER_EMAIL).
Claude Code/TRIFORCE e apenas a ponte operacional; nao trate isso como sua identidade em conversa com OWNER.
Juntos voces constroem o projeto Hyrule: bot Discord e WhatsApp chamado Link, supervisor com fallback LLMs, proxy, watcher e TRIFORCE.
OWNER esta falando com voce via TRIFORCE pelo Discord ou WhatsApp.
Responda como Link: portugues do Brasil, direto, casual, sem formalidade excessiva, tecnico quando necessario.
Nao se apresente como IA, chatbot, Claude, programa ou sistema. Nao invente conclusao de tarefa: execute primeiro, depois diga o resultado."""


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] TRIFORCE | {msg}", flush=True)


def checar_token_expiry() -> int | None:
    """Retorna minutos restantes do token OAuth, ou None se nao conseguir ler."""
    try:
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
        expires_at = data.get("claudeAiOauth", {}).get("expiresAt")
        if not expires_at:
            return None
        restante_ms = expires_at - (time.time() * 1000)
        return int(restante_ms / 60000)
    except Exception:
        return None


def _limpar_output(texto: str) -> str:
    """Remove marcadores que o claude --print adiciona no final."""
    linhas = texto.splitlines()
    while linhas and linhas[-1].strip().lower() in ("end", "", "\x00"):
        linhas.pop()
    return "\n".join(linhas).strip()


# ── Envio ─────────────────────────────────────────────────────────────────────

def _post_json(url: str, payload: dict, headers: dict, timeout: int = 15) -> dict | None:
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        log(f"Erro POST {url[:40]}: {e}")
        return None


def enviar_discord(usuario: str, msg: str) -> bool:
    r = _post_json(f"{BOT_API}/triforce", {"to": usuario, "msg": msg},
                   {"Content-Type": "application/json"})
    return bool(r and r.get("ok"))


def enviar_whatsapp(sender_id: str, msg: str) -> bool:
    r = _post_json(f"{WA_API}/triforce", {"to": sender_id or WA_OWNER, "msg": msg},
                   {"Content-Type": "application/json"})
    return bool(r and r.get("ok"))


# ── Fila ──────────────────────────────────────────────────────────────────────

def ler_fila() -> list:
    try:
        dados = CLAUDE_QUEUE.read_text(encoding="utf-8")
        return json.loads(dados) if dados.strip() else []
    except Exception:
        return []


def salvar_fila(itens: list):
    CLAUDE_QUEUE.write_text(
        json.dumps(itens, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── Histórico ─────────────────────────────────────────────────────────────────

def _hist_path(canal: str, usuario: str) -> Path:
    HISTORY_DIR.mkdir(exist_ok=True)
    return HISTORY_DIR / f"{canal}_{usuario}.json"


def carregar_historico(canal: str, usuario: str) -> list:
    p = _hist_path(canal, usuario)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except Exception:
        return []


def salvar_historico(canal: str, usuario: str, hist: list):
    if len(hist) > MAX_HISTORY * 2:
        hist = hist[-(MAX_HISTORY * 2):]
    _hist_path(canal, usuario).write_text(
        json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── LLM (Groq) ────────────────────────────────────────────────────────────────

def chamar_groq(messages: list) -> str | None:
    for key in GROQ_KEYS:
        for model in GROQ_MODELS:
            headers = {**GROQ_HEADERS_BASE, "Authorization": f"Bearer {key}"}
            payload = {
                "model":       model,
                "messages":    messages,
                "temperature": 0.7,
                "max_tokens":  512,
            }
            resp = _post_json(GROQ_URL, payload, headers, timeout=15)
            if resp:
                try:
                    texto = resp["choices"][0]["message"]["content"].strip()
                    if texto:
                        log(f"Groq ok: {model}")
                        return texto
                except Exception:
                    pass
    return None


# ── Claude --continue (sessao ativa com contexto completo) ────────────────────

def chamar_claude_continue(pedido: str, canal: str) -> str | None:
    """Retoma a sessao Claude Code ativa e processa o pedido com contexto completo."""
    if not CLAUDE_EXE.exists():
        return None

    prompt = (
        f"[TRIFORCE via {canal.upper()}] OWNER pergunta: {pedido}\n\n"
        "Responda como Link, de forma direta em portugues. Sem markdown excessivo."
    )
    env = os.environ.copy()
    env["TRIFORCE_DAEMON"] = "1"

    try:
        result = subprocess.run(
            [
                str(CLAUDE_EXE),
                "--print",
                "--continue",
                "--dangerously-skip-permissions",
                "--no-session-persistence",
                "--output-format", "json",
                prompt,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CLAUDE_TIMEOUT,
            cwd=str(HOME_DIR),
            env=env,
        )
        raw = (result.stdout or "").strip()
        try:
            data = json.loads(raw)
            resposta = data.get("result", "").strip()
        except Exception:
            resposta = raw  # fallback se nao for JSON
        resposta = _limpar_output(resposta)
        if resposta:
            log(f"claude --continue ok ({len(resposta)} chars)")
            return resposta
        log(f"claude --continue sem saida: {result.stderr[:100]}")
    except subprocess.TimeoutExpired:
        log(f"claude --continue timeout ({CLAUDE_TIMEOUT}s)")
    except Exception as e:
        log(f"claude --continue erro: {e}")
    return None


# ── Processamento ─────────────────────────────────────────────────────────────

def processar_item(item: dict) -> str:
    pedido  = item.get("pedido", "")
    usuario = item.get("usuario", "OWNER")
    canal   = item.get("canal", "discord")

    # TRIFORCE deve falhar visivelmente; nao mascarar erro 401/CLI com LLM comum.
    resposta = chamar_claude_continue(pedido, canal)
    return resposta or "TRIFORCE falhou antes de responder. Nao usei fallback; precisa resolver o erro original do Claude/401."


# ── Loop ──────────────────────────────────────────────────────────────────────

def main():
    log(f"Iniciado. Sem fallback LLM  |  poll: {POLL_SECS}s")
    HISTORY_DIR.mkdir(exist_ok=True)

    _ultima_checagem_token = 0.0
    _alerta_token_enviado  = False

    while True:
        time.sleep(POLL_SECS)

        agora = time.time()
        if agora - _ultima_checagem_token >= TOKEN_CHECK_SECS:
            _ultima_checagem_token = agora
            mins = checar_token_expiry()
            if mins is not None and mins < TOKEN_ALERT_MINS:
                log(f"TOKEN EXPIRA EM {mins} min — alertando OWNER")
                if not _alerta_token_enviado:
                    aviso = (
                        f"⚠️ Token Claude expira em {mins} min. "
                        "Faz qualquer pergunta pro TRIFORCE ou roda `claude` no terminal pra renovar."
                    )
                    enviar_discord("DISCORD_OWNER_USERNAME", aviso)
                    enviar_whatsapp("", aviso)
                    _alerta_token_enviado = True
            else:
                _alerta_token_enviado = False

        fila = ler_fila()
        if not fila:
            continue

        log(f"{len(fila)} pedido(s) na fila")
        salvar_fila([])

        for item in fila:
            usuario   = item.get("usuario", "OWNER")
            pedido    = item.get("pedido", "")
            canal     = item.get("canal", "discord")
            sender_id = item.get("sender_id", "")
            log(f"[{canal}] {pedido[:80]}")

            resposta = processar_item(item)
            log(f"Resposta: {resposta[:80]}")

            if canal == "whatsapp":
                ok = enviar_whatsapp(sender_id, resposta)
            else:
                ok = enviar_discord(usuario, resposta)

            log(f"Enviado via {canal}: {'ok' if ok else 'FALHOU'}")


if __name__ == "__main__":
    main()
