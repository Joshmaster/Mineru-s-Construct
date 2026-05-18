---
name: Padrao do card Boss Mundial
description: Regras fixas para o card/aviso de Boss Mundial estilo Diablo
type: feedback
---

## Regra do OWNER

O card de Boss Mundial/Diablo deve ser enviado somente no Discord, nunca no WhatsApp.

O aviso automatico continua disparando 5 minutos antes do boss, mas o texto visivel do card e a legenda nao podem mostrar countdown, "faltam X minutos", "em 5 minutos", "encerra em" ou contador relativo.

Padrao visual pedido:
- mostrar o dia/data do boss;
- mostrar a hora grande do boss;
- se o boss estiver dentro da janela ativa, manter o horario do boss atual;
- depois da janela ativa, mostrar o proximo boss;
- legenda curta no Discord: `Boss Mundial - DD/MM as HH:MM`.

## Implementacao atual

- `world_boss_notify.py` dispara na janela configurada por `REMINDER_MIN = 5`, usando somente `http://localhost:7331/send-file`.
- `world_boss_card.py` renderiza o card sem countdown.
- A janela ativa usa `BOSS_DURATION_MIN = 15`; durante esse periodo o card mostra o boss atual, depois avanca para o proximo.

## Why

OWNER ja corrigiu varias vezes: o card nao deve parecer contagem regressiva. Ele quer saber o horario real do boss, por dia e hora, com aviso antes apenas como mecanismo de envio.
