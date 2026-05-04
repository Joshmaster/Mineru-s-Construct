# setup_pagefile.ps1 — Configura page file fixo de 8GB no C: via Registry
# Requer execucao como Administrador

Write-Host "=== Configurando Page File (via Registry) ===" -ForegroundColor Cyan

$regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management"

# 1. Desabilita gerenciamento automatico
Set-ItemProperty -Path $regPath -Name "AutomaticManagedPagefile" -Value 0 -Type DWord
Write-Host "[OK] Gerenciamento automatico desativado." -ForegroundColor Green

# 2. Define page file fixo: C:\pagefile.sys 8192 8192
Set-ItemProperty -Path $regPath -Name "PagingFiles" -Value "C:\pagefile.sys 8192 8192" -Type MultiString
Write-Host "[OK] Page file configurado: C:\pagefile.sys 8192MB inicial / 8192MB maximo." -ForegroundColor Green

# 3. Confirma lendo o registro
$auto = (Get-ItemProperty -Path $regPath -Name "AutomaticManagedPagefile").AutomaticManagedPagefile
$pf   = (Get-ItemProperty -Path $regPath -Name "PagingFiles").PagingFiles

Write-Host "`n[Configuracao no Registro]" -ForegroundColor Cyan
Write-Host "  AutomaticManagedPagefile : $auto  (0 = user2al)"
Write-Host "  PagingFiles              : $pf"

Write-Host "`n[OK] Tudo configurado. REINICIE o PC para ativar o swap de 8GB." -ForegroundColor Yellow
