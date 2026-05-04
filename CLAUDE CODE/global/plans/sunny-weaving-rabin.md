# Plano — Simplificar logo do link.bat para "LINK"

## Contexto
O link.bat tem uma logo ASCII art com dois blocos: "LINK" (esquerda) + bloco extra (direita), mais o subtítulo "H  Y  R  U  L  E". O usuário pediu para deixar apenas "LINK" — sem o bloco da direita e sem o subtítulo.

O bloco esquerdo atual já forma exatamente "LINK" (L, I, N, K em 6 linhas). Basta remover o bloco direito e a linha do subtítulo.

## O que fazer

### 1. Substituir bloco de echo no link.bat
Trocar as linhas de echo atuais (8 linhas incluindo subtítulo) por apenas o bloco "LINK":

```bat
echo.
echo   ██╗     ██╗███╗   ██╗██╗  ██╗
echo   ██║     ██║████╗  ██║██║ ██╔╝
echo   ██║     ██║██╔██╗ ██║█████╔╝
echo   ██║     ██║██║╚██╗██║██╔═██╗
echo   ███████╗██║██║ ╚████║██║  ██╗
echo   ╚══════╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝
echo.
```

### 2. Replicar em bin\link.bat
Aplicar a mesma mudança em `C:\Users\OWNER\.claude\bin\link.bat`.

### 3. Atualizar ZIP
Recriar `C:\Users\OWNER\Documents\hyrule_stack_handoff.zip` incluindo os dois link.bat atualizados.

## Arquivos modificados
- `C:\Users\OWNER\.claude\link.bat`
- `C:\Users\OWNER\.claude\bin\link.bat`
- `C:\Users\OWNER\Documents\hyrule_stack_handoff.zip`

## Verificação
Executar `link` no CMD/PowerShell e confirmar que a logo exibe apenas "LINK" sem bloco direito nem subtítulo.
