# Plano: Finalizar isolamento dos binários em Agents/

## Context
O usuário quer que Claude Code e OpenCode funcionem exclusivamente a partir de `C:\Users\OWNER\Agents\`, com binários reais (não junctions/symlinks) e PATH atualizado para apontar diretamente para essas pastas.

## O que já foi feito
- `claude.exe` restaurado em `Agents/CLAUDE CODE/bin/` (versão .old renomeada)
- `link.bat` movido de `~/.claude/bin/` para `Agents/OPENCODE/`
- Junctions removidas:
  - `~/.local/bin` → já removido
  - WinGet `SST.opencode...` folder → já removido

## Passos restantes

### 1. Atualizar Windows User PATH
Remover entradas antigas e adicionar Agents:
- **Remover:** `C:\Users\OWNER\.local\bin`
- **Remover:** `C:\Users\OWNER\AppData\Local\Microsoft\WinGet\Packages\SST.opencode_Microsoft.Winget.Source_8wekyb3d8bbwe`
- **Remover:** `C:\Users\OWNER\.claude\bin`
- **Adicionar:** `C:\Users\OWNER\Agents\CLAUDE CODE\bin`
- **Adicionar:** `C:\Users\OWNER\Agents\OPENCODE\bin`

### 2. Limpar arquivo .old
- Deletar `Agents/CLAUDE CODE/bin/claude.exe.old.1775817690724`

### 3. Limpar diretórios vazios
- Remover `~/.local/bin` (diretório vazio após junction removida) — só se vazio
- Remover `~/.claude/bin` (vazio após mover link.bat)

## Verificação
- `claude --version` no terminal novo deve funcionar
- `opencode --version` no terminal novo deve funcionar
- PATH não deve mais conter as entradas antigas
