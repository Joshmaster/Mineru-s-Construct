# Plano: Validar tools do OpenCode

## Contexto

Após configurar a persona Link com sucesso, o usuário quer confirmar que o OpenCode tem as mesmas tools do Claude Code funcionando: leitura de arquivos, edição, bash, glob, grep, etc.

## Abordagem

Usar `opencode run` (modo não-interativo) para enviar prompts que forçam uso de cada tool. O modelo Link responde e usa as tools — se executar sem erro, a tool está funcionando.

## Arquivo de teste temporário

Criar `C:\Users\OWNER\Agents\tool_test.txt` com conteúdo simples para servir de alvo dos testes.

## Testes a executar (sequencial via `opencode run`)

| Tool | Prompt de teste |
|------|----------------|
| **read** | "leia o arquivo C:\Users\OWNER\Agents\tool_test.txt e me diga o conteúdo" |
| **write** | "crie o arquivo C:\Users\OWNER\Agents\tool_result.txt com o texto 'Hyrule'" |
| **edit** | "edite tool_test.txt e adicione uma linha 'editado pelo Link'" |
| **bash** | "execute o comando 'echo Hyrule' e me mostre o resultado" |
| **glob** | "liste todos os arquivos .bat em C:\Users\OWNER\Agents\OPENCODE\" |
| **grep** | "procure a palavra 'MODEL' em C:\Users\OWNER\Agents\OPENCODE\link.bat" |

## Comando base

```batch
"%USERPROFILE%\Agents\OPENCODE\bin\opencode.exe" run -m "groq/meta-llama/llama-4-scout-17b-16e-instruct" "PROMPT AQUI"
```

## Verificação

- Cada tool retorna resultado esperado sem erros
- Arquivos criados/editados existem com conteúdo correto após os testes
- Limpar arquivos temporários ao final
