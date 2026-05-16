# 🗡️ Link Bot — Bot Pessoal de WhatsApp

Bot de WhatsApp pessoal com persona de **Link de Hyrule**.
Roda local, dados seus, sem mensalidade, sem servidor externo.

**28 comandos em 9 categorias**, todos respondendo no estilo Hyrule.
Modo atual: **offline-first, determinístico**, gratuito. LLM fica como **passo 3** futuro (descrito ao final).

---

## 📦 O que tem dentro

```
link-bot/
├── README.md
├── bot/
│   ├── main.py                  # launcher principal
│   ├── core/
│   │   ├── router.py            # matcher de palavra-chave natural
│   │   ├── context.py           # contexto passado pras skills
│   │   ├── storage.py           # SQLite (todos, notas, lembretes)
│   │   ├── timeparse.py         # parser de tempo natural PT-BR
│   │   ├── sticker.py           # FFmpeg + metadados WhatsApp
│   │   └── scheduler.py         # loop de lembretes async
│   └── skills/                  # 28 skills modulares
│       ├── ajuda.py             # menu Pergaminho do Aventureiro
│       ├── identidade.py        # quem é você
│       ├── status.py            # status do reino
│       ├── lembrete.py          # criar/listar/cancelar (3 skills)
│       ├── clima.py             # Open-Meteo
│       ├── cotacao.py           # AwesomeAPI
│       ├── hora.py              # timezone mundial
│       ├── noticias.py          # RSS G1+BBC
│       ├── cep.py               # ViaCEP
│       ├── figurinha.py         # FFmpeg + EXIF metadata WhatsApp
│       ├── bau.py               # salvar mídia recebida (2 skills)
│       ├── calc.py              # calculadora segura (sem eval)
│       ├── conversao.py         # peso/distância/temp/tempo/volume
│       ├── tradutor.py          # MyMemory API
│       ├── letra.py             # lyrics.ovh
│       ├── encurtar.py          # is.gd
│       ├── qr.py                # qrcode lib local
│       ├── aleatorio.py         # dados/moeda/sortear/senha (4 skills)
│       ├── todo.py              # lista de tarefas (4 skills)
│       ├── nota.py              # anotações com tags (3 skills)
│       └── manage.py            # ping/info/reload (3 skills)
├── config/
│   └── config.example.json
├── windows/
│   ├── instalar-atualizar.bat
│   ├── personalizar.bat
│   └── menu.bat                 # 🎮 launcher principal
└── android/
    ├── instalar-atualizar.sh
    ├── personalizar.sh
    └── menu.sh                  # 🎮 launcher principal
```

---

## 🎯 Como funciona

```
[zap manda msg] → [neonize escuta] → [router casa palavra-chave]
                                            ↓
                                    [skill executa]
                                            ↓
                                    [responde no zap]
```

**Palavra-chave natural** (não precisa de prefixo `/`):
- _"Link, qual o clima em POA?"_ → skill clima
- _"me lembra daqui 30min de tomar agua"_ → skill lembrete
- (manda imagem) _"vira figurinha"_ → skill figurinha
- _"meus lembretes"_ → skill listar lembretes

---

## 🚀 Começar — Windows

```batch
:: 1. Descompacta o zip
:: 2. Entra na pasta windows/
:: 3. Duplo clique:
instalar-atualizar.bat

:: 4. Quando terminar:
personalizar.bat
::    - digita seu numero (5511999999999)
::    - escolhe se ativa controle PC

:: 5. Duplo clique:
menu.bat
::    [1] Iniciar bot — primeira vez aparece QR
```

## 📱 Começar — Android (Xiaomi/Termux)

```bash
# 1. Copia o kit pro celular
cp -r /sdcard/Download/link-bot ~/

# 2. No Termux:
cd ~/link-bot/android
chmod +x *.sh

# 3. Instala
./instalar-atualizar.sh

# 4. Personaliza
./personalizar.sh

# 5. Abre o menu
./menu.sh
#    [1] Iniciar bot
```

---

## 📲 Pareamento via QR

`menu.sh/.bat` opção [1] inicia o bot. Primeira vez, aparece QR no terminal.

No celular com **WhatsApp Business**:
1. Configurações → **Aparelhos conectados**
2. **Conectar um aparelho**
3. Aponta câmera no QR

**Android com bot rodando no mesmo celular:**
- Outro celular escaneando o Termux, OU
- Long-press no Termux → Style → fonte grande → screenshot → escaneia da galeria

---

## 🎮 O Menu

```
===== ROTINA DIARIA =====
 [1] Iniciar bot                  <- mais usado
 [2] Re-parear WhatsApp
 [3] Status / config atual

===== MANUTENCAO =====
 [4] Atualizar dependencias
 [5] Reaplicar personalizacao
 [6] Editar config.json
 [7] Abrir pasta do bot

===== INFO =====
 [V] Versão Python e libs
 [S] Listar skills
 [B] Backup
 [W] Wake-lock (Android, anti-MIUI)

 [0] Sair
```

---

## 🗡️ Os 28 comandos

### ⚔️ ESSENCIAIS
- `ajuda` / `menu` — Pergaminho do Aventureiro
- `quem é você` — apresentação
- `status` — uptime e contagens

### ⏰ PERGAMINHOS DO TEMPO
- `me lembra daqui 30min de X` — criar lembrete
- `me lembra todo dia 22h de X` — recorrente diário
- `toda segunda 9h me lembra X` — semanal
- `meus lembretes` — listar
- `cancela lembrete 5` — destruir

### 🗺️ CONSULTAR O REINO
- `clima POA` — Open-Meteo
- `cotação dólar` / `bitcoin agora` — AwesomeAPI
- `que horas em Tóquio?` — timezone
- `notícias` / `notícias tecnologia` — RSS feeds
- `CEP 90010-150` — ViaCEP

### 🎨 FORJA DE RUNAS
- (envia mídia) `vira figurinha` — sticker WhatsApp
- (envia mídia) `guarda no baú` — salvar local
- `meu baú` — listar guardados

### 📜 DIÁRIO DO AVENTUREIRO
- `adiciona X na lista` — TODO
- `minhas tarefas` — listar
- `feito 5` — concluir
- `remove tarefa 5` — apagar
- `anota: X` — nota livre
- `minhas anotações` / `anotações sobre X` — buscar
- `apaga anotação 5`

### 🧰 UTILIDADES DO HERÓI
- `calcula 152 * 38` — math seguro
- `converte 100 km em milhas` — peso/distância/temp/tempo/volume
- `traduz pra inglês: bom dia` — MyMemory
- `letra Imagine - John Lennon` — lyrics.ovh
- `encurta https://...` — is.gd
- `gera qr <texto>` — qrcode local
- `joga dado` / `d20` — dados
- `cara ou coroa`
- `sorteia entre A, B, C`
- `gera senha 16` — secrets

### ⚙️ MANUTENÇÃO
- `ping`, `info técnica`, `reload`

---

## 🔐 Segurança

✅ **`ALLOW_FROM`** com seu número = blindagem (default deny — vazio bloqueia tudo)
✅ **`ENABLE_PC_CONTROL=false`** por padrão
✅ **Calculadora via AST**, não `eval` (sem injeção)
✅ **Storage local SQLite**, nada na nuvem
✅ **Sem API keys** (todas APIs usadas são gratuitas e sem registro)

⚠️ Use **número WhatsApp Business dedicado**. Bridge não-oficial tem risco de
ban (baixo pra uso pessoal, não zero).

---

## 🗺️ Roadmap — LLM como passo 3 futuro

Hoje o bot é **rule-based puro**. Quando bater alguma palavra-chave, executa
a skill. Quando NÃO bate, responde "não entendi". Esse "não entendi" é
exatamente o ponto de extensão pra LLM no futuro.

**Plano:**

1. ✅ **Fase 1 (atual)**: rule-based, 28 skills, sem LLM, gratuito
2. **Fase 2**: hot-reload de skills, agendamento mais rico, melhorar parser PT
3. **Fase 3 — LLM**: adicionar fallback inteligente
   - Quando router não match, em vez de "não entendi" → manda pra LLM
   - LLM responde com persona Link injetada via system prompt
   - Comandos rápidos/determinísticos continuam funcionando direto (sem
     pagar token, sem latência), só conversa livre passa pela LLM
   - Provider: OpenRouter (uma key, todos modelos), `claude-haiku-4-5`
     pra economizar ou `claude-sonnet-4-5` pra qualidade

**O hook já tá lá** no `bot/main.py`, no `_on_message` quando `router.match`
retorna `None`. Só substituir o "não entendi" por uma chamada à LLM.

---

## 🧪 Testar sem WhatsApp

Pra debugar skills antes de parear, dá pra mexer no `bot/main.py` e adicionar
um modo CLI. Hoje não tem direto, mas pode rodar Python interativo:

```python
from bot.core.router import Router
from bot.core.storage import Storage

# carrega skills, testa router.match("Link, calcula 2+2"), etc
```

(Modo CLI integrado tá no roadmap da Fase 2.)

---

## 🆘 Troubleshooting

**Bot não responde mensagens minhas**
→ Confere `ALLOW_FROM` no `config.json` — seu número precisa estar lá no
formato `5511999999999` (sem `+`, sem espaços).

**"Sessão desconectada"**
→ Menu opção [2] Re-parear WhatsApp. WhatsApp expira sessões inativas após
~14 dias.

**Figurinha não funciona**
→ Falta FFmpeg. Windows: `winget install Gyan.FFmpeg`. Termux: `pkg install ffmpeg`.

**Termux morrendo no MIUI**
→ Battery → sem restrições, lock no recents, e menu [W] Wake-lock antes do bot.

**Erro ao baixar mídia (figurinha/baú)**
→ APIs do neonize variam entre versões. O código tenta `download_any`,
`download` e `download_media` — se nenhum funcionar, abre issue ou
manda o erro pra eu ajustar.

---

🔱 Boa jornada, aventureiro. ⚔️
