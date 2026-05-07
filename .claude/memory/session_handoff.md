---
name: Handoff de sessao
description: Estado da ultima sessao — lido ao iniciar para retomar sem perder contexto
type: project
---

## O que estava em andamento
USER2tencao do Hyrule: FFmpeg/figurinhas WhatsApp, troca do LLM local Ollama e preparacao de git com cuidado para dados sensiveis.

## O que foi feito nesta sessao

### Figurinhas WhatsApp
- FFmpeg instalado via apt (`ffmpeg 8.0.1-3ubuntu2`) e validado gerando WebP.
- Pacote `webp` instalado para validacao (`webpinfo`/`webpmux`).
- `link-bot/bot/core/sticker.py` ajustado:
  - usa `ffmpeg` pelo PATH e fallback direto para `/usr/bin/ffmpeg`;
  - imagens e videos saem 512x512 em modo `cover` por padrao, sem borda;
  - escala Lanczos e qualidade reduzida gradualmente ate caber nos limites;
  - WebP estatico validado em 512x512, <100KB;
  - WebP animado validado com canvas 512x512, <500KB.
- `link-bot/bot/skills/figurinha.py` ajustado para usar modo sem borda por padrao.
- `startup_services.py status` agora mostra `FFmpeg: instalado/ausente`.

### Swap e modelo local
- Swap `/swap.img` ampliado de 4G para 10G e preservado no `/etc/fstab`.
- `qwen2.5:7b` removido do Ollama.
- `qwen3.5:9b` instalado no Ollama:
  - ID: `6488c96fa5fa`;
  - tamanho: 6.6GB;
  - arquitetura: `qwen35`;
  - parametros: 9.7B;
  - quantizacao: Q4_K_M;
  - capabilities: completion, vision, tools, thinking.
- `bot_supervisor.py` atualizado:
  - `OLLAMA_MODEL = "qwen3.5:9b"`;
  - `OLLAMA_ALL_TOOLS = True`;
  - chamadas Ollama com `think=False`, `temperature=0.3`;
  - timeout local aumentado para 180s;
  - `_selecionar_tools()` retorna todas as 17 tools quando `OLLAMA_ALL_TOOLS=True`.

### Testes feitos
- `ollama pull qwen3.5:9b` concluiu com sucesso.
- Tool calling direto no Ollama testado: modelo retornou `tool_calls` para tool `get_time`.
- Fluxo real do supervisor testado:
  - `executar_qwen_react("qual a data e hora do pc?", "OWNER")`;
  - qwen chamou `executar_comando`;
  - resposta final correta: data/hora em portugues.
- `python3 -m py_compile bot_supervisor.py` passou.
- Supervisor reiniciado e Hyrule status verde.

## Estado dos servicos
- Hyrule Proxy: rodando
- Discord bot: online
- Supervisor: rodando, reiniciado apos troca para qwen3.5
- WhatsApp bot: rodando
- TRIFORCE: rodando
- MAJORA: rodando
- MASTERSWORD: rodando
- Ollama: rodando com `qwen3.5:9b` carregado temporariamente apos teste

## Pendente
- Diff final revisado para dados sensiveis: sem chaves/tokens/telefone real nos arquivos atuais.
- Commit git criado com as mudancas desta sessao.
- Historico local reescrito novamente com `git filter-repo` para remover referencia antiga de telefone/username que ainda estava no handoff anterior.
- Varredura final no historico para telefone/username real nao retorna resultados.
- Pendente antigo ainda vale: remote/push do historico reescrito para GitHub depende de credencial/remote e exige force push.

---
Atualizado ao encerrar cada sessao. Nao acumula — sobrescreve.
