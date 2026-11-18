[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [string]$WorkDirectory,
    [ValidateRange(0.01, 2.0)][double]$Pace = 1
)

. "$PSScriptRoot/common.ps1"
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $script:ProjectRoot 'demo/video' }
if (-not $WorkDirectory) { $WorkDirectory = Join-Path $script:ProjectRoot 'web/test-results' }
$output = (New-Item -ItemType Directory -Path $OutputDirectory -Force).FullName
$project = 'agentflow-recording-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$capture = (New-Item -ItemType Directory -Path (Join-Path $WorkDirectory $project) -Force).FullName

function Get-RecordingPort {
    $socket = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try { $socket.Start(); return $socket.LocalEndpoint.Port }
    finally { $socket.Stop() }
}

function Format-VideoTime([double]$Seconds, [string]$Format) {
    return [TimeSpan]::FromSeconds($Seconds).ToString($Format, [Globalization.CultureInfo]::InvariantCulture)
}

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) { $npm = Get-Command npm -ErrorAction Stop }
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
$ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
$ports = @()
while ($ports.Count -lt 3) {
    $candidate = Get-RecordingPort
    if ($candidate -notin $ports) { $ports += $candidate }
}
$values = @{
    WEB_PORT = [string]$ports[0]; API_PORT = [string]$ports[1]; MCP_PORT = [string]$ports[2]
    OLLAMA_MODEL = ''; OLLAMA_JUDGE_MODEL = ''; OPENAI_API_KEY = ''; OPENAI_MODEL = ''
    ANTHROPIC_API_KEY = ''; ANTHROPIC_MODEL = ''; AGENTFLOW_JUDGE_PROVIDER = 'ollama'
    AGENTFLOW_LANGSMITH = 'false'; LANGSMITH_API_KEY = ''
}
$previous = @{}
$compose = @('compose', '-f', 'compose.yml', '--env-file', '.env.example', '-p', $project)
$startupAttempted = $false

Push-Location -LiteralPath $script:ProjectRoot
try {
    foreach ($name in $values.Keys) {
        $previous[$name] = [Environment]::GetEnvironmentVariable($name)
        [Environment]::SetEnvironmentVariable($name, $values[$name])
    }
    if (-not (Test-Path -LiteralPath 'web/node_modules/@playwright/test')) {
        Invoke-Checked { & $npm.Source --prefix web ci --no-audit --no-fund } 'Install recording dependencies'
    }
    Invoke-Checked { & $npm.Source --prefix web exec -- playwright install chromium } 'Prepare Chromium'
    $startupAttempted = $true
    Invoke-Checked { docker @compose up --build -d --wait --wait-timeout 180 web } 'Start isolated recording stack'
    $url = "http://127.0.0.1:$($ports[0])"
    $health = Invoke-RestMethod "$url/api/v1/connections" -TimeoutSec 12
    if ($health.api.state -ne 'ok' -or $health.database.state -ne 'ok' -or $health.mcp.state -ne 'ok') {
        throw 'The API, database, and MCP service must be ready before capture.'
    }
    $optional = @('openai', 'anthropic', 'ollama', 'judge', 'langsmith')
    if ($optional | Where-Object { $health.$_.state -ne 'not_configured' }) {
        throw 'The isolated stack unexpectedly configured an optional provider.'
    }
    $paceText = $Pace.ToString([Globalization.CultureInfo]::InvariantCulture)
    Invoke-Checked { node web/scripts/record-demo.mjs $url $capture $paceText } 'Capture live investigation'
} finally {
    try {
        if ($startupAttempted) {
            Invoke-Checked { docker @compose down --volumes } 'Stop the isolated recording stack'
        }
    } finally {
        foreach ($name in $previous.Keys) {
            [Environment]::SetEnvironmentVariable($name, $previous[$name])
        }
        Pop-Location
    }
}

Push-Location -LiteralPath $capture
try {
    $timing = Get-Content -LiteralPath 'timing.json' -Raw | ConvertFrom-Json
    $subtitle = @'
[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Chapter,Segoe UI,27,&H00E5CDCB,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,96,96,0,1
Style: Caption,Segoe UI,26,&H00F7F3F2,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,96,96,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'@
    $events = foreach ($item in $timing.beats) {
        $begin = Format-VideoTime $item.start 'h\:mm\:ss\.ff'
        $end = Format-VideoTime $item.end 'h\:mm\:ss\.ff'
        "Dialogue: 0,$begin,$end,Chapter,,0,0,0,,{\an7\pos(96,991)}$($item.title)"
        "Dialogue: 0,$begin,$end,Caption,,0,0,0,,{\an7\pos(96,1029)}$($item.caption)"
    }
    @($subtitle; $events) | Set-Content -LiteralPath 'captions.ass' -Encoding utf8
    $i = 0
    $captions = foreach ($item in $timing.beats) {
        $i++
        "$i"
        "$(Format-VideoTime $item.start 'hh\:mm\:ss\,fff') --> $(Format-VideoTime $item.end 'hh\:mm\:ss\,fff')"
        $item.caption
        ''
    }
    $captions | Set-Content -LiteralPath 'agentflow_captions.srt' -Encoding utf8

    $name = 'agentflow_demo.webm'
    if ($ffmpeg -and $ffprobe) {
        $filter = 'scale=1728:972:flags=lanczos,pad=1920:1080:96:8:color=0x141725,ass=captions.ass,fps=30'
        Invoke-Checked { & $ffmpeg.Source -hide_banner -loglevel error -y -i capture.webm -an -vf $filter -c:v libx264 -preset fast -crf 19 -threads 3 -pix_fmt yuv420p -movflags +faststart agentflow_demo.mp4 } 'Encode captioned MP4'
        $name = 'agentflow_demo.mp4'
        Invoke-Checked { & $ffmpeg.Source -hide_banner -loglevel error -xerror -threads 2 -i $name -map 0:v:0 -f null - } 'Decode and check the complete MP4'
        $probe = & $ffprobe.Source -v error -show_streams -show_format -of json $name | ConvertFrom-Json
        if ($LASTEXITCODE -ne 0) { throw 'Video inspection failed.' }
        $video = $probe.streams | Where-Object codec_type -eq 'video' | Select-Object -First 1
        $duration = [double]::Parse($probe.format.duration, [Globalization.CultureInfo]::InvariantCulture)
        if ($video.codec_name -ne 'h264' -or $video.width -ne 1920 -or $video.height -ne 1080 -or
            $video.pix_fmt -ne 'yuv420p' -or $duration -le 0 -or ($probe.streams | Where-Object codec_type -eq 'audio')) {
            throw 'The encoded video did not meet its format specification.'
        }
        $format = "1920 × 1080, 30 fps, H.264/yuv420p MP4, no audio. Full-stream decode passed."
    } else {
        Copy-Item -LiteralPath 'capture.webm' -Destination $name
        $duration = $timing.duration
        $format = '1600 × 900 Chromium WebM, no audio. Captions are supplied as a separate SRT.'
        Write-Warning 'FFmpeg and ffprobe are required for a captioned MP4 and full decode verification.'
    }
    $runtime = Format-VideoTime $duration 'm\:ss'
    $chapterLines = $timing.chapters | ForEach-Object { "$(Format-VideoTime $_.at 'm\:ss') $($_.title)" }
    @(
        '# AgentFlow | Multi-Agent Operations Analysis with LangGraph + MCP'
        ''
        'Follow a checkout conversion investigation at Northstar Shop, a fictional retailer. AgentFlow routes the case to specialist branches, reads evidence through MCP, audits the figures, and pauses for human review. After approval, it exports a cited Markdown report. The closing benchmark compares sequential and parallel execution on a seeded case suite.'
        ''
        'The recording uses synthetic data and rule-based decisions. No LLM, external tracing, or paid provider was used.'
        ''
        "Runtime $runtime. $format"
        ''
        '## Chapters'
        ''
        ($chapterLines | ForEach-Object { "- $_" })
    ) | Set-Content -LiteralPath 'agentflow_video_details.md' -Encoding utf8
    foreach ($file in @($name, 'agentflow_preview.png', 'agentflow_captions.srt', 'agentflow_video_details.md')) {
        Copy-Item -LiteralPath $file -Destination (Join-Path $output $file)
    }
    Write-Host "Video: $(Join-Path $output $name) ($runtime)."
    Write-Host "Capture and timing files: $capture"
} finally { Pop-Location }

