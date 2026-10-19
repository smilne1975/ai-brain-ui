param(
    [string]$Projects = "",
    [int]$Port = 8741,
    [switch]$Replace
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Invoke-Python {
    param([string[]]$PyArgs)
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 @PyArgs
        return
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python @PyArgs
        return
    }
    throw "Python 3.11+ is required. Install it from https://www.python.org/downloads/ and check 'Add python.exe to PATH'."
}

function Test-PortBusy {
    param([int]$CheckPort)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $wait = $client.BeginConnect("127.0.0.1", $CheckPort, $null, $null)
        if (-not $wait.AsyncWaitHandle.WaitOne(400, $false)) {
            return $false
        }
        $client.EndConnect($wait) | Out-Null
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-ListeningPid {
    param([int]$CheckPort)
    try {
        $lines = & netstat.exe -ano -p tcp
    } catch {
        return $null
    }
    foreach ($line in $lines) {
        if ($line -match "127\.0\.0\.1:$CheckPort\s+\S+\s+LISTENING\s+(\d+)") {
            return [int]$Matches[1]
        }
    }
    return $null
}

function Test-AiBrainPid {
    param([int]$ProcessId)
    if (-not $ProcessId) { return $false }
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
    } catch {
        return $false
    }
    $cmd = [string]$proc.CommandLine
    return ($cmd -match "uvicorn" -and $cmd -match "backend\.app\.main")
}

function Test-InteractivePrompt {
    try {
        if ([Console]::IsInputRedirected -or [Console]::IsOutputRedirected) { return $false }
    } catch {
        return $false
    }
    return $true
}

function Find-FreePort {
    param([int]$Start, [int]$Count = 20)
    for ($p = $Start; $p -lt ($Start + $Count); $p++) {
        if (-not (Test-PortBusy $p)) { return $p }
    }
    throw "No free port from $Start through $($Start + $Count - 1). Close the program using those ports, or pass -Port with a free one."
}

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating .venv"
    Invoke-Python @("-m", "venv", ".venv")
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $Root "requirements.txt")

$distIndex = Join-Path $Root "frontend\dist\index.html"
if (-not (Test-Path $distIndex)) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "Node.js 20+ is required the first time, to build the UI. Install it from https://nodejs.org/ and run this script again."
    }
    Push-Location (Join-Path $Root "frontend")
    npm install
    npm run build
    Pop-Location
}

if ($Projects) {
    $resolved = Resolve-Path -LiteralPath $Projects
    $env:BRAIN_ROOT = $resolved.Path
} else {
    $env:BRAIN_ROOT = Join-Path $Root "demo-projects"
}

$chosen = $Port
if (Test-PortBusy $chosen) {
    $owner = Get-ListeningPid $chosen
    $ours = Test-AiBrainPid $owner
    $stopped = $false
    if ($ours -and ($Replace -or (Test-InteractivePrompt))) {
        $stop = [bool]$Replace
        if (-not $stop) {
            Write-Host ""
            Write-Host "Port $chosen is already used by AI Brain (PID $owner)."
            Write-Host "Leaving it running would keep the browser on the old folder."
            $answer = Read-Host "Stop that AI Brain and reuse port $chosen? [Y/n]"
            $stop = ($answer -eq "" -or $answer -match "^[Yy]")
        }
        if ($stop) {
            Write-Host "Stopping PID $owner"
            Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
            for ($i = 0; $i -lt 15; $i++) {
                Start-Sleep -Milliseconds 200
                if (-not (Test-PortBusy $chosen)) {
                    $stopped = $true
                    break
                }
            }
            if (-not $stopped) {
                Write-Host "Port $chosen is still busy."
            }
        }
    } elseif ($ours) {
        Write-Host "Port $chosen is already used by AI Brain (PID $owner)."
    } elseif ($owner) {
        Write-Host "Port $chosen is in use by another program (PID $owner). Leaving that process alone."
    } else {
        Write-Host "Port $chosen is already in use."
    }
    if (-not $stopped) {
        $chosen = Find-FreePort ($chosen + 1)
        Write-Host "Using port $chosen instead."
    }
}

Write-Host ""
Write-Host "AI Brain is mapping $env:BRAIN_ROOT"
Write-Host "Open http://127.0.0.1:$chosen"
Write-Host "The page comes up while the folder is still being read."
Write-Host ""

& $venvPython -m uvicorn backend.app.main:app --host 127.0.0.1 --port $chosen
