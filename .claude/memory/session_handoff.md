---
name: Handoff de sessao
description: Estado da ultima sessao — lido ao iniciar para retomar sem perder contexto
type: project
---

## O que estava em andamento
Sessao de user2tencao completa do sistema Hyrule via SSH externo (Windows → mineru).

## O que foi feito

### 1. OpenCode (MASTERSWORD) — PATH corrigido
- Binario opencode existia em ~/.nvm/versions/node/v22.22.2/bin/opencode mas nao estava no PATH
- Criado symlink: sudo ln -sf ~/.nvm/versions/node/v22.22.2/bin/opencode /usr/local/bin/opencode
- Agora shutil.which(opencode) encontra normalmente

### 2. OpenRouter — chaves corrigidas
- Chave antiga expirada (401 User not found)
- Duas chaves Groq (GROQ_KEY) estavam erroneamente na lista OPENROUTER_KEYS
- Removidas as Groq de OPENROUTER_KEYS e movidas para GROQ_KEYS
- 3 novas chaves OpenRouter adicionadas e validadas (todas retornam OK)

### 3. Todos os modelos testados e validados
Testou TODOS os modelos disponiveis em ambas as APIs com mensagem oi:

OpenRouter free — funcionando (9 modelos):
  openai/gpt-oss-120b:free
  openai/gpt-oss-20b:free
  nvidia/nemotron-3-super-120b-a12b:free
  google/gemma-4-31b-it:free
  google/gemma-4-26b-a4b-it:free
  inclusionai/ling-2.6-1t:free
  liquid/lfm-2.5-1.2b-instruct:free
  openrouter/free
  openrouter/owl-alpha

Groq — funcionando (7 modelos):
  llama-3.3-70b-versatile
  meta-llama/llama-4-scout-17b-16e-instruct
  qwen/qwen3-32b
  groq/compound
  groq/compound-mini
  llama-3.1-8b-instant
  allam-2-7b

Removidos por falha:
  OpenRouter: arcee-ai/trinity-large-preview:free (nao esta mais free)
              meta-llama/llama-3.3-70b-instruct:free (provider error)
  Groq: moonshotai/kimi-k2-instruct (nao esta na API)
        openai/gpt-oss-20b e 120b (falham no Groq)

### 4. Fallback order atualizado (melhor para pior)
Logica ja existente: for model → for key (esgota todas as keys no melhor modelo antes de cair)

bot_supervisor.py — MODELOS (OpenRouter), ordem:
  1. gpt-oss-120b  2. gpt-oss-20b  3. nemotron-120b  4. gemma-31b  5. gemma-26b
  6. ling-2.6  7. openrouter/free  8. owl-alpha  9. lfm-1.2b

bot_supervisor.py — GROQ_MODELOS, ordem:
  1. llama-3.3-70b  2. llama-4-scout  3. qwen3-32b  4. compound
  5. compound-mini  6. llama-3.1-8b  7. allam-2-7b

### 5. OpenCode configs atualizados
Mesma lista validada em:
  ~/Agents/OPENCODE/mastersword.opencode.json
  ~/.config/opencode/opencode.json

### 6. Commit feito, push PENDENTE
- Commit ae235c4 criado com todas as mudancas
- git push falhou — sem token GitHub no servidor
- OWNER vai ao servidor fazer o push user2almente

## Estado dos servicos
Todos rodando apos startup_services.py restart:
  Hyrule Proxy: ok | Discord bot: ok | Supervisor: ok | WhatsApp bot: ok
  TRIFORCE: ok | MAJORA: ok | MASTERSWORD: ok (symlink corrigido)
  OpenRouter: ok (3 chaves novas) | Groq: ok (3 chaves) | Ollama qwen2.5:7b: ok

## Pendente
- git push origin master — commit ae235c4 local, nao subiu ao GitHub ainda
  Motivo: sem PAT (Personal Access Token) do GitHub no servidor
  Solucao: rodar git push com credenciais, ou salvar token em hyrule_env.py como GITHUB_TOKEN e configurar:
    git remote set-url origin https://{GITHUB_TOKEN}@github.com/OWNERmaster/Mineru-s-Construct.git

---
Atualizado ao encerrar cada sessao. Nao acumula — sobrescreve.
