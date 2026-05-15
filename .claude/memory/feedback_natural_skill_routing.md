---
name: Roteamento natural de skills
description: Regra permanente para WhatsApp/Discord: conversa natural tem prioridade sobre comandos; comandos com ! existem como fallback e alias interno para LLMs
type: feedback
---

## Regra principal

O OWNER quer usar as funções conversando naturalmente. Prefixos `!` devem existir como fallback, não como caminho principal.

Prioridade correta de roteamento:
1. Frase natural clara do usuário
2. Detecção determinística local para intents comuns
3. Classificador LLM de skill
4. `!comando` como fallback
5. Chat normal

## Intencao do OWNER

O objetivo nao e apenas aceitar meia duzia de frases hardcoded. O sistema deve entender o sentido natural do pedido.

Exemplos do comportamento desejado:
- OWNER: "toca lost woods via yutube" -> buscar/baixar YouTube por texto.
- OWNER: "manda uma musica do zelda pelo spotify" -> buscar/baixar musica pelo Spotify por texto.
- OWNER responde uma musica enviada: "outra famosa" -> usar a banda/artista/musica anterior como contexto.
- OWNER responde uma musica enviada: "manda uma braba deles" -> interpretar como outra faixa conhecida da mesma banda/artista.
- OWNER responde uma musica enviada: "tem outra conhecida?", "uma classica dessa banda", "a mais estourada deles", "uma parecida" -> manter o contexto musical anterior.

O roteamento programado e guarda-corpo. A interpretacao flexivel deve ficar com o LLM, usando contexto e aliases internos.

## Uso interno do `!`

LLMs podem usar aliases `!` internamente para raciocinar e escolher a skill. Exemplo:
- usuário: "toca lost woods no youtube"
- LLM pode mapear internamente para `!yt lost woods`
- sistema executa `delirius_dl` sem exigir que o usuário digite `!yt`

Não responder pedindo `!comando` quando a intenção estiver clara.

Se o LLM achar mais seguro usar `!yt`, `!spot`, `!img`, etc. como representacao interna, tudo bem. Isso e detalhe operacional. O usuario continua falando normal.

## Grupo WhatsApp

No grupo, o OWNER pode acionar funções por conversa natural sem `!` e sem link obrigatório quando a skill aceita busca por texto.
Outros usuários continuam precisando mencionar o bot ou usar comando, para evitar ruído no grupo.

## Música/mídia

Pedido de música via YouTube deve aceitar busca por texto:
- "toca lost woods via yutube"
- "toca zelda lost woods no youtube"
- "manda uma música do zelda pelo spotify"

YouTube e Spotify aceitam busca por texto; link é opcional quando a API/skill consegue resolver por busca.

## Musica contextual por reply

Quando OWNER responde/cita uma musica que o bot mandou e pede outra musica por contexto, o sistema deve usar o contexto anterior.

Sinais programados comuns:
- "outra famosa"
- "outro famoso"
- "mais uma"
- "mais famosa"
- "da mesma banda"
- "desse artista"
- "dessa banda"
- "parecida com essa"
- "nesse estilo"

Mas a regra e semantica, nao so textual. Frases diferentes com o mesmo sentido tambem devem funcionar via LLM:
- "manda uma braba deles"
- "tem outra conhecida?"
- "pega uma classica dessa banda"
- "a mais estourada deles"
- "uma no mesmo clima"
- "outra desse cara"

Implementacao atual:
- `whatsapp-bridge/index.js` envia `quotedText`, `quotedParticipant` e `quotedMsgId` no webhook quando a mensagem e reply/citacao.
- `link-bot/bot/core/whatsapp_client.py` faz `send_audio()` retornar o ID da mensagem enviada.
- `link-bot/bot/core/context.py` permite registrar contexto musical enviado por ID.
- `link-bot/bot/main.py` guarda contexto de musicas enviadas pelo bot por ate 6h em `sent_music_context`.
- `link-bot/bot/main.py` injeta `Contexto musical anterior:` quando OWNER responde uma musica com pedido contextual.
- `link-bot/bot/core/llm.py` instrui o rewriter Spotify a usar esse contexto para escolher outra musica famosa relacionada.
- `link-bot/bot/skills/delirius_dl.py` tem fallback programado: se o LLM falhar, extrai artista do contexto e busca `Artist popular songs` / `Artist greatest hits`, evitando busca aleatoria por "outra famosa".

Ponto importante para outra IA analisando:
Nao reduzir isso a uma lista fechada de palavras. A lista existe para ativacao rapida e fallback, mas a decisao principal deve considerar contexto conversacional e intencao semantica.

## Arquivos principais

- `link-bot/bot/main.py`: roteamento natural, contexto por reply, regra de grupo, `!` como fallback.
- `link-bot/bot/core/llm.py`: classificador natural e rewriter de busca Spotify contextual.
- `link-bot/bot/skills/delirius_dl.py`: YouTube/Spotify por busca textual, fallback contextual.
- `link-bot/bot/core/context.py`: contexto da mensagem e registro de musica enviada.
- `link-bot/bot/core/whatsapp_client.py`: retorno de ID ao enviar audio.
- `whatsapp-bridge/index.js`: extracao de quoted text/context do WhatsApp.
