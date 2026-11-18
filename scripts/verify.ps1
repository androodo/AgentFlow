. "$PSScriptRoot/common.ps1"
Push-Location -LiteralPath $script:ProjectRoot
try {
    & "$PSScriptRoot/demo.ps1"
    Invoke-Checked { docker compose --profile verify run --build --rm --no-deps verify } 'Backend lint, typing, and tests'

    if (Get-Command python -ErrorAction SilentlyContinue) {
        Invoke-Checked { python scripts/proof.py } 'Seed, restart, and outage verification'
    } else {
        Write-Warning 'Host Python is unavailable. Seed fingerprint, process restart, and outage proof skipped.'
    }
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npm) { $npm = Get-Command npm -ErrorAction SilentlyContinue }
    if ($npm) {
        $previousWeb = $env:AGENTFLOW_WEB_URL
        $env:AGENTFLOW_WEB_URL = Get-ServiceUrl web 8080
        try {
            Invoke-Checked { & $npm.Source --prefix web ci --no-audit --no-fund } 'Web dependency install'
            Invoke-Checked { & $npm.Source --prefix web run build } 'Frontend type check and production build'
            Invoke-Checked { & $npm.Source --prefix web exec -- playwright install chromium } 'Playwright Chromium install'
            Invoke-Checked { & $npm.Source --prefix web test } 'Playwright browser tests'
        } finally {
            $env:AGENTFLOW_WEB_URL = $previousWeb
        }
    } else {
        Write-Warning 'Host Node/npm is unavailable. Docker built the frontend. Playwright skipped.'
    }
    Write-Host 'AgentFlow verification finished. Review the command results and any explicit skips above.'
} finally { Pop-Location }
