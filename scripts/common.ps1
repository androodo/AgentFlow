$ErrorActionPreference = 'Stop'
$script:ProjectRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Label)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Label failed (exit $LASTEXITCODE)." }
}

function Get-ServiceUrl {
    param([string]$Service, [int]$Port)
    $binding = docker compose port $Service $Port
    if ($LASTEXITCODE -ne 0 -or -not $binding) { throw "No published port for $Service." }
    return "http://$($binding.Trim())"
}

function Read-LocalPort {
    param([string]$Name, [int]$Default)
    $value = [Environment]::GetEnvironmentVariable($Name)
    if (-not $value -and (Test-Path -LiteralPath '.env')) {
        $line = Get-Content -LiteralPath '.env' | Where-Object { $_ -match "^\s*$Name\s*=" } | Select-Object -Last 1
        if ($line -match '=\s*["'']?(\d+)') { $value = $Matches[1] }
    }
    if ($value) { return [int]$value }
    return $Default
}
