. "$PSScriptRoot/common.ps1"
Push-Location -LiteralPath $script:ProjectRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install Docker Desktop with the WSL 2 backend.' }
    Invoke-Checked { docker compose version } 'Docker Compose'
    $daemon = docker info --format '{{.ServerVersion}} {{.OSType}}'
    if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop and wait for its Linux engine.' }
    if (-not $daemon.EndsWith('linux')) { throw 'Switch Docker Desktop to Linux containers.' }
    Write-Host "Docker engine $daemon"
    $memory = Get-CimInstance Win32_OperatingSystem
    Write-Host ('Host memory: {0:N1} GiB total, {1:N1} GiB free' -f
        ($memory.TotalVisibleMemorySize / 1MB), ($memory.FreePhysicalMemory / 1MB))
    $drive = (Get-Item -LiteralPath $script:ProjectRoot).PSDrive
    Write-Host ('Project drive: {0:N1} GiB free. Initial images and optional browser downloads need disk space.' -f ($drive.Free / 1GB))

    $ports = @((Read-LocalPort WEB_PORT 3001), (Read-LocalPort API_PORT 8001), (Read-LocalPort MCP_PORT 8002))
    if (($ports | Select-Object -Unique).Count -ne 3 -or ($ports | Where-Object { $_ -lt 1024 -or $_ -gt 65535 })) {
        throw 'Configure three distinct non-privileged ports in .env.'
    }
    $listening = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue)
    $composePorts = @(
        foreach ($service in @(@('web',8080), @('api',8001), @('mcp',8002))) {
            $binding = docker compose port $service[0] $service[1] 2>$null
            if ($binding -match ':(\d+)$') { [int]$Matches[1] }
        }
    )
    foreach ($port in $ports) {
        if ($composePorts -contains $port) { Write-Host "Port ${port}: AgentFlow" }
        elseif ($listening.LocalPort -contains $port) { Write-Warning "Port $port is occupied. Choose an available port in .env." }
        else { Write-Host "Port ${port}: available" }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) { python --version } else { Write-Host 'Host Python unavailable. Container tests remain available.' }
    if (Get-Command node -ErrorAction SilentlyContinue) { node --version } else { Write-Host 'Host Node unavailable. Docker builds the UI. Install Node for Playwright verification.' }
    try {
        $tags = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
        Write-Host "Optional Ollama: host API reachable, $(@($tags.models).Count) installed model(s)."
    } catch {
        Write-Host 'Optional Ollama: host API unavailable. Demo mode is ready without Ollama.'
    }
} finally { Pop-Location }
