# Plano: Adicionar `.local\bin` ao PATH do usuário

## Context
O Claude Code exibe um aviso toda vez que é iniciado:
> `Warning: Native installation exists but C:\Users\OWNER\.local\bin is not in your PATH`

OWNER pediu várias vezes para resolver e nunca foi feito. A correção é simples: adicionar o diretório ao PATH permanente do usuário via registry do Windows.

## Implementação

**Um único comando PowerShell** que modifica o PATH do usuário no registry:

```powershell
[Environment]::SetEnvironmentVariable(
  "PATH",
  [Environment]::GetEnvironmentVariable("PATH", "User") + ";C:\Users\OWNER\.local\bin",
  "User"
)
```

Isso equivale a fazer user2almente via "System Properties → Environment Variables → Edit User PATH → New" — mas sem abrir janela nenhuma.

## Arquivo afetado
- Registry: `HKCU\Environment\PATH` (modificado via .NET, sem edição user2al)

## Lembrete importante
Claude Code deve estar instalado/funcionando a partir de:
`C:\Users\OWNER\Agents\CLAUDE CODE\bin\claude.exe`

Ao resolver o PATH, garantir que este diretório também esteja no PATH (ou que seja o executável principal usado).

## Verificação
Após executar:
1. Abrir novo terminal PowerShell
2. Rodar `claude` — aviso não deve mais aparecer
3. Confirmar com: `$env:PATH -split ";" | Select-String ".local"`
