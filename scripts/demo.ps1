. "$PSScriptRoot/common.ps1"
Push-Location -LiteralPath $script:ProjectRoot
try {
    if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
    Invoke-Checked { docker compose up --build -d --wait --wait-timeout 180 } 'AgentFlow startup'
    $web = Get-ServiceUrl web 8080
    $api = Get-ServiceUrl api 8001
    $mcp = Get-ServiceUrl mcp 8002
    $health = Invoke-RestMethod "$web/api/v1/connections" -TimeoutSec 12
    if ($health.database.state -ne 'ok' -or $health.mcp.state -ne 'ok') { throw 'Core services are unavailable.' }
    Write-Host "Open $web"
    Write-Host "API docs $api/docs"
    Write-Host "MCP endpoint $mcp/mcp"
    Write-Host "Ollama: $($health.ollama.state). LangSmith: $($health.langsmith.state)."
    Write-Host 'Click Try demo: Checkout Conversion Drop, open the cited draft, approve it, and download Markdown.'
} finally { Pop-Location }
