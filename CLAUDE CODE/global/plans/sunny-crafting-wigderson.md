# Plano: Apagar pasta .local (instalação nativa anterior)

## Contexto
Após mover o `claude.exe` nativo para `Agents\CLAUDE CODE\bin\`, sobrou a estrutura de `.local\` com apenas symlinks apontando para dentro de `Agents\CLAUDE CODE\`. Não há nada único em `.local\` — é seguro apagar tudo.

## Resultado da validação

`.local\` contém **apenas symlinks e uma pasta vazia**:

| Caminho | O que é | Aponta para |
|---|---|---|
| `.local\share\claude` | symlink | `Agents\CLAUDE CODE\share\claude` |
| `.local\share\opencode` | symlink | `Agents\OPENCODE\data` |
| `.local\share\opentui\` | pasta vazia | — |
| `.local\state\claude` | symlink | `Agents\CLAUDE CODE\state` |
| `.local\state\opencode` | symlink | `Agents\OPENCODE\state` |

**Nenhum arquivo real está em `.local\` — tudo fica em `Agents\`.** Apagar symlinks não afeta os alvos.

## Execução

Único comando:
```bash
rm -rf "C:/Users/OWNER/.local/"
```

## Verificação
```bash
ls "C:/Users/OWNER/.local/" 2>/dev/null || echo "removida com sucesso"
where claude  # deve continuar apontando para Agents\CLAUDE CODE\bin\claude.exe
```
