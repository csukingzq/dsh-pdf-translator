param(
    [string]$Python = '',
    [string]$DataDir = '',
    [switch]$Force,
    [switch]$OfficialOnly,
    [string[]]$PipIndexUrls = @('https://pypi.tuna.tsinghua.edu.cn/simple', 'https://mirrors.aliyun.com/pypi/simple/'),
    [string]$PipFallbackIndexUrl = 'https://pypi.org/simple'
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
} catch {}
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
$projectRoot = Split-Path $PSScriptRoot -Parent

function Resolve-DataDir {
    param([string]$Requested)
    if ($Requested) { return [IO.Path]::GetFullPath($Requested) }
    if ($env:DSH_PDF_DATA_DIR) { return [IO.Path]::GetFullPath($env:DSH_PDF_DATA_DIR) }
    if ((Test-Path -LiteralPath (Join-Path $projectRoot 'config.json')) -or
        (Test-Path -LiteralPath (Join-Path $projectRoot 'work\plugin-state.json'))) {
        return [IO.Path]::GetFullPath($projectRoot)
    }
    $homeDir = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE '.dsh' }
    return [IO.Path]::GetFullPath((Join-Path $homeDir 'dsh-pdf-translator'))
}

# Run a native command without letting stderr become a terminating error.
# Windows PowerShell 5.1 turns native stderr into an ErrorRecord, and with
# $ErrorActionPreference = 'Stop' any expected probe failure (for example
# "pdf2zh-next is not installed") would otherwise abort the whole setup.
function Invoke-NativeProbe {
    param([string]$Exe, [string[]]$Arguments = @())
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = (& $Exe @Arguments 2>$null)
        $exit = $LASTEXITCODE
    } catch {
        $output = $null
        $exit = -1
    } finally {
        $ErrorActionPreference = $previous
    }
    $text = if ($output -eq $null) { '' } else { ($output | Out-String).Trim() }
    return @{ Output = $text; ExitCode = $exit }
}

function Test-PythonVersion {
    param([string]$Exe, [string[]]$Arguments = @())
    $probe = Invoke-NativeProbe -Exe $Exe -Arguments ($Arguments + @('-c', 'import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,15) else 1)'))
    return $probe.ExitCode -eq 0
}

function Find-BasePython {
    $candidates = @(@{ Exe = (Join-Path $DataDir '.venv\Scripts\python.exe'); Args = @() })
    if ($Python) { $candidates += @{ Exe = $Python; Args = @() } }
    if ($env:DSH_PDF_PYTHON) { $candidates += @{ Exe = $env:DSH_PDF_PYTHON; Args = @() } }
    $dshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE '.dsh' }
    $bundled = Join-Path $dshHome 'dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundled) { $candidates += @{ Exe = $bundled; Args = @() } }
    foreach ($name in @('python', 'python3')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source -notlike '*\WindowsApps\*') {
            $candidates += @{ Exe = $command.Source; Args = @() }
        }
    }
    if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += @{ Exe = 'py'; Args = @('-3') } }
    foreach ($candidate in $candidates) {
        if (Test-PythonVersion -Exe $candidate.Exe -Arguments $candidate.Args) { return $candidate }
    }
    throw 'Python 3.11-3.14 is required. Install Python or use the Python runtime bundled with DSH Desktop.'
}

$DataDir = Resolve-DataDir -Requested $DataDir
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
# Prepare PDF2zh first without changing its virtual environment or model settings.
& (Join-Path $PSScriptRoot 'setup.ps1') -DataDir $DataDir -Python $Python -OfficialOnly:$OfficialOnly -PipIndexUrls $PipIndexUrls -PipFallbackIndexUrl $PipFallbackIndexUrl
$venvDir = Join-Path $DataDir '.venv-mineru'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$runtimeDir = if ($env:DSH_PDF_RUNTIME_DIR) { $env:DSH_PDF_RUNTIME_DIR } else { Join-Path $DataDir 'runtime' }
$configPath = Join-Path $DataDir 'config.json'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

if ($Force -and (Test-Path -LiteralPath $venvDir)) {
    Write-Host "Recreating Python environment: $venvDir"
    if ([IO.Path]::GetFullPath($venvDir) -ne [IO.Path]::Combine([IO.Path]::GetFullPath($DataDir), '.venv-mineru')) { throw 'Unsafe venv path.' }
    Remove-Item -LiteralPath $venvDir -Recurse -Force
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $base = Find-BasePython
    $baseArgs = @($base.Args)
    Write-Host "Creating Python environment with $($base.Exe) ..."
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $base.Exe @baseArgs -m venv $venvDir
        $venvExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($venvExit -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        throw "Failed to create the Python environment. Verify Python 3.11-3.14: $($base.Exe)"
    }
}

$pipIndexes = @()
if (-not $OfficialOnly) { $pipIndexes += $PipIndexUrls }
if ($PipFallbackIndexUrl) { $pipIndexes += $PipFallbackIndexUrl }
$pipIndexes = @($pipIndexes | Where-Object { $_ } | Select-Object -Unique)

function Invoke-PipInstall {
    param([string]$Label, [string]$Requirements, [string]$IndexUrl)
    $pipArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', '--timeout', '60', '--retries', '3')
    if ($IndexUrl) { $pipArgs += @('-i', $IndexUrl) }
    $pipArgs += @('-r', $Requirements)
    $source = if ($IndexUrl) { $IndexUrl } else { 'the default pip index' }
    Write-Host "$Label via $source ..."
    # pip warnings go to stderr; keep them from aborting the script under Stop.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $venvPython @pipArgs | Out-Host
        $exit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    return $exit
}

function Install-Requirements {
    param([string]$Label, [string]$Requirements)
    $exit = 1
    foreach ($pipIndex in $pipIndexes) {
        $exit = Invoke-PipInstall -Label $Label -Requirements $Requirements -IndexUrl $pipIndex
        if ($exit -eq 0) { return }
        if ($pipIndex -ne $pipIndexes[-1]) { Write-Host 'pip mirror failed, trying the next source ...' }
    }
    if ($pipIndexes.Count -eq 0) { $exit = Invoke-PipInstall -Label $Label -Requirements $Requirements }
    if ($exit -ne 0) { throw "$Label failed. Check the network or pip configuration." }
}

Install-Requirements -Label 'Installing MinerU' -Requirements (Join-Path $projectRoot 'requirements-mineru.txt')
$probe = Invoke-NativeProbe -Exe $venvPython -Arguments @('-c', "from mineru.parser import parse; from mineru.render import render_pdf; import importlib.metadata as m; print(m.version('mineru'))")
if ($probe.ExitCode -ne 0 -or $probe.Output -ne '4.2.3') { throw 'MinerU installation verification failed.' }
$markerJson = @{ version = $probe.Output; python = $venvPython; installedAt = (Get-Date).ToString('o') } | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $runtimeDir 'mineru.json'), $markerJson, [Text.UTF8Encoding]::new($false))
Write-Host 'PDF translator environment is ready.'
