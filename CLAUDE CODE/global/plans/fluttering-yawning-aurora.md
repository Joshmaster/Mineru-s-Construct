# Plano: Migrar dados globais para Agents/

## Contexto
O usuário quer que todos os dados globais do Claude Code e do OpenCode vivam fisicamente dentro de `C:\Users\OWNER\Agents\`. Nenhuma das duas ferramentas tem flag `--config-dir` ou env var oficial para redirecionar seu diretório global. A solução é **Windows Directory Junctions (mklink /J)**: mover os dados para `Agents/`, depois criar atalhos simbólicos nos locais originais — as ferramentas continuam funcionando sem nenhuma alteração.

---

## CLAUDE CODE

### Diretório global atual
`C:\Users\OWNER\.claude\`

### Destino
`C:\Users\OWNER\Agents\CLAUDE CODE\global\`

### Passos
1. Copiar todo o conteúdo de `~/.claude/` → `Agents/CLAUDE CODE/global/`
2. Renomear `~/.claude/` para `~/.claude_backup/`
3. Criar junction: `~/.claude/` → `Agents/CLAUDE CODE/global/`

### Resultado final
```
Agents/CLAUDE CODE/
├── proxy.py
├── HYRULE.md
├── universal_agent.py
├── start.bat
├── ua.bat
├── .claude/settings.json       ← config de projeto
└── global/                     ← tudo que era ~/.claude/
    ├── settings.json
    ├── HYRULE.md
    ├── memory/
    ├── projects/
    ├── proxy.py (cópia original)
    └── ...
```
Junction: `C:\Users\OWNER\.claude\` → `Agents\CLAUDE CODE\global\`

---

## OPENCODE

### Diretórios globais atuais
| Original | Conteúdo |
|---|---|
| `~/.config/opencode/` | plugin node_modules |
| `~/.local/share/opencode/` | banco de dados (opencode.db), storage |
| `~/.local/state/opencode/` | estado da aplicação |
| `~/.cache/opencode/` | cache |
| `AppData\Roaming\opencode\` | config/persona globais |

### Destinos em `Agents/OPENCODE/`
| Subpasta | Origem |
|---|---|
| `plugin/` | `~/.config/opencode/` |
| `data/` | `~/.local/share/opencode/` |
| `state/` | `~/.local/state/opencode/` |
| `cache/` | `~/.cache/opencode/` |
| `roaming/` | `AppData\Roaming\opencode\` |

### Passos
1. Para cada diretório: mover conteúdo → subpasta em `Agents/OPENCODE/`
2. Renomear original para `_backup`
3. Criar junction apontando para a nova subpasta

### Resultado final
```
Agents/OPENCODE/
├── opencode.json       ← config local (já existe)
├── LINK_PERSONA.md     ← persona (já existe)
├── start.bat           ← launcher (já existe)
├── plugin/             ← junction ← ~/.config/opencode/
├── data/               ← junction ← ~/.local/share/opencode/
├── state/              ← junction ← ~/.local/state/opencode/
├── cache/              ← junction ← ~/.cache/opencode/
└── roaming/            ← junction ← AppData\Roaming\opencode\
```

---

## Verificação
- `claude` deve abrir normalmente (settings e histórico intactos)
- `opencode` deve abrir com histórico de sessões preservado
- `ls ~/.claude/` deve mostrar o conteúdo de `Agents/CLAUDE CODE/global/`
- `opencode.db` continua acessível via junction em `data/`
