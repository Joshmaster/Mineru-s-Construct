# Executar DEPOIS de fechar o Claude Code
# Clique com botao direito > Executar com PowerShell

$source = "$env:USERPROFILE\.claude"
$backup = "$env:USERPROFILE\.claude_bak"
$target = "C:\Users\OWNER\Agents\CLAUDE CODE\global"

Write-Host ""
Write-Host "  Claude Code - Finalizar Migracao" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $target)) {
    Write-Host "[ERRO] Pasta global nao encontrada: $target" -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit 1
}

# Verifica se ja e junction
$item = Get-Item $source -Force -ErrorAction SilentlyContinue
if ($item -and $item.LinkType -eq "Junction") {
    Write-Host "[OK] Junction ja existe. Migracao ja foi concluida!" -ForegroundColor Green
    Read-Host "Pressione Enter para sair"
    exit 0
}

# Renomeia .claude para .claude_bak
Write-Host "Renomeando $source para $backup ..."
try {
    Rename-Item $source $backup -ErrorAction Stop
} catch {
    Write-Host "[ERRO] Nao foi possivel renomear .claude: $_" -ForegroundColor Red
    Write-Host "Certifique-se de que o Claude Code esta FECHADO." -ForegroundColor Yellow
    Read-Host "Pressione Enter para sair"
    exit 1
}

# Cria junction
Write-Host "Criando junction: $source -> $target ..."
try {
    New-Item -ItemType Junction -Path $source -Target $target -ErrorAction Stop | Out-Null
    Write-Host ""
    Write-Host "[OK] Migracao concluida!" -ForegroundColor Green
    Write-Host "  ~/.claude agora aponta para: $target" -ForegroundColor Green
    Write-Host "  Backup original em: $backup" -ForegroundColor Gray
} catch {
    Write-Host "[ERRO] Falha ao criar junction: $_" -ForegroundColor Red
    Write-Host "Revertendo..." -ForegroundColor Yellow
    Rename-Item $backup ".claude"
}

Write-Host ""
Read-Host "Pressione Enter para sair"
