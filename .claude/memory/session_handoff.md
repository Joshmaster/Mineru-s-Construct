---
name: Handoff de sessao
description: Estado da ultima sessao - lido ao iniciar para retomar sem perder contexto
type: project
---

## Feito nesta sessao

### Git e seguranca
- Historico Git foi sanitizado e enviado para o remoto com `--force-with-lease`.
- Removidos do historico:
  - arquivo local de config sensivel antigo;
  - metadados/caminhos pessoais;
  - URL assinada de anexo Discord usada em teste;
  - placeholders com formato de token.
- Varreduras finais no historico inteiro deram zero para:
  - padroes de token/API key;
  - caminhos/nomes pessoais procurados;
  - IDs/numeros reais especificos do WhatsApp;
  - alta entropia suspeita em arquivos rastreados.
- Config local deste repo ajustada para autor com e-mail neutro (`owner@example.local`).
- Criada memoria `feedback_git_security.md`: antes de push e depois de pull/fetch, validar estado atual e historico inteiro. Se algo parecer pessoal mas ambiguo, perguntar ao OWNER antes de commitar, limpar historico ou subir.

### Modelo local e `!z` / `!zpensa`
- Modelo Ollama local trocado para `qwen3:8b`.
- Referencias antigas a modelo pesado removidas dos bots e do core LLM.
- `LINK_CONTEXT.md` atualizado para ambiente Ubuntu/Linux/bash.
- `!zpensa` agora usa tools/web/imagem nos caminhos Discord e WhatsApp.

### WhatsApp: acesso, admin e identidade
- Criado `link-bot/bot/core/access.py`.
- Admin agora e somente dono via `OWNER`/`OWNER_IDS`; usuarios liberados continuam comuns.
- Numero fisico, ID interno/LID e JID sao tratados como aliases do mesmo contato via `contact_uid` na tabela SQLite `contacts`.
- Nome de contato e persistido no banco e usado para respostas como “quem sou eu?” / “lembra de mim?”.
- Corrigido bug em que usuario comum podia ser tratado como dono.
- Logs do WhatsApp usam fuso `America/Sao_Paulo`.
- O bot consegue avisar o dono usando aliases e servidores corretos:
  - numero fisico via `s.whatsapp.net`;
  - ID interno via `lid`;
  - fallback por aliases conhecidos.

### Fluxo de liberacao de acesso
- Novo fluxo:
  1. pessoa desconhecida manda mensagem;
  2. bot pergunta nome;
  3. bot envia pedido ao dono sem gerar/sugerir codigo;
  4. dono responde marcando a mensagem do pedido com o codigo escolhido;
  5. bot grava o codigo temporario;
  6. pessoa repete o codigo no chat dela;
  7. bot libera e remove o pendente/codigo.
- O bot nao grava codigo se o dono mandar mensagem solta; precisa ser resposta/marcacao ao pedido.
- O bot nao da dica/exemplo de codigo.
- `!acesso pendentes` mostra estado sem revelar codigo quando ainda esta aguardando o dono.
- `!acesso codigo [ID] [codigo]` existe para caso haja mais de um pedido pendente.

### Skills mais inteligentes
- Mensagem natural no WhatsApp passa por classificador de intencao com IA.
- Comandos explicitos (`!comando`) continuam indo direto para o router.
- Se a IA classificar como conversa (`null`), nao cai em skill por palavra solta.
- Isso evita falso positivo como “lembra de mim?” virar lembrete.

### Busca e envio de imagem
- Criada skill WhatsApp `imagem_buscar`.
- Pedido natural de imagem/foto no Discord e interceptado antes da LLM e enviado como arquivo.
- Busca de imagem agora usa IA em duas etapas:
  - extrai entidade/intencao visual/qualificadores;
  - ranqueia candidatos para evitar entidade errada, capa, logo, mapa, sprite, item, multipersonagem etc.
- O refinamento e generico, nao so para Link.
- Para “foto sua/dele” no contexto do bot, a IA resolve como personagem Link, e a busca usa fonte/ranking para evitar imagem com Zelda junto.
- A busca coleta varios candidatos e tem anti-repeticao em memoria RAM para evitar mandar sempre a mesma imagem quando houver alternativas.
- Arquivos baixados sao temporarios:
  - WhatsApp apaga depois de `reply_media`;
  - Discord usa `/send-file` com `delete_after`;
  - proxima busca pesquisa/baixa novamente.

### Mastersword/OpenCode
- Menu SSH atualizado com opcao OpenCode/Mastersword.
- Watcher Mastersword usa modelos baratos/gratis/remotos por padrao.
- Config local OpenCode atualizada para `qwen3:8b`, mas watcher nao usa local por padrao porque travava.

## Cuidados com dados sensiveis
- Nao commitar:
  - `link-bot/config/config.json`;
  - `link-bot/.linkbot/`;
  - `.linkbot/`;
  - bancos SQLite, sessoes, QR, logs e filas;
  - pedidos pendentes com nomes/numeros/codigos reais;
  - imagens baixadas/geradas em `DISCORD/files/link_*`.
- `.gitignore` foi reforcado para `.linkbot/` raiz e `DISCORD/files/link_*`.
- Handoff nao deve conter numeros reais, IDs reais, codigos de acesso, nomes de solicitantes reais ou tokens.

## Estado final
- Servicos rodando:
  - Hyrule Proxy;
  - Discord bot;
  - Supervisor;
  - WhatsApp bot;
  - TRIFORCE daemon;
  - MAJORA watcher;
  - MASTERSWORD watcher.
- Banco de contatos/IDs foi preservado localmente e nao deve ir para git.

## Pendente para testar
- Confirmar no WhatsApp:
  - dono responde marcando o pedido com codigo escolhido;
  - bot grava somente se for resposta marcada;
  - usuario repete codigo e e liberado;
  - codigo some do pendente depois da liberacao.
- Confirmar imagem:
  - pesquisa refinada por imagem;
  - sem reutilizar arquivo salvo;
  - sem mandar sempre a mesma imagem quando houver alternativas.

---
Atualizado ao encerrar cada sessao. Nao acumula - sobrescreve.
