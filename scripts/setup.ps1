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
    $probe = Invoke-NativeProbe -Exe $Exe -Arguments ($Arguments + @('-c', 'import sys; raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,14) else 1)'))
    return $probe.ExitCode -eq 0
}

function Find-BasePython {
    $candidates = @()
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
    throw 'Python 3.10-3.13 is required. Install Python or use the Python runtime bundled with DSH Desktop.'
}

$DataDir = Resolve-DataDir -Requested $DataDir
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
$venvDir = Join-Path $DataDir '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$runtimeDir = Join-Path $DataDir 'runtime'
$configPath = Join-Path $DataDir 'config.json'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

if ($Force -and (Test-Path -LiteralPath $venvDir)) {
    Write-Host "Recreating Python environment: $venvDir"
    if ([IO.Path]::GetFullPath($venvDir) -ne [IO.Path]::Combine([IO.Path]::GetFullPath($DataDir), '.venv')) { throw 'Unsafe venv path.' }
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
        throw "Failed to create the Python environment. Verify Python 3.10-3.13: $($base.Exe)"
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

$engineRequirements = Join-Path $projectRoot 'requirements-engine.txt'
$requiresEngine = Test-Path -LiteralPath $engineRequirements

Install-Requirements -Label 'Installing Python dependencies' -Requirements (Join-Path $projectRoot 'requirements.txt')
$importProbe = Invoke-NativeProbe -Exe $venvPython -Arguments @('-c', 'import pymupdf, pypdf')
if ($importProbe.ExitCode -ne 0) { throw 'Python dependencies are not importable after installation.' }

if ($requiresEngine) {
    $versionProbe = Invoke-NativeProbe -Exe $venvPython -Arguments @('-c', "import importlib.metadata as m; print(m.version('pdf2zh-next'))")
    $installedVersion = $versionProbe.Output
    if ($versionProbe.ExitCode -ne 0 -or $installedVersion -ne '2.10.2') {
        Install-Requirements -Label 'Installing the translation engine' -Requirements $engineRequirements
    } else {
        Write-Host "pdf2zh-next already installed: $installedVersion"
    }
    $engineProbe = Invoke-NativeProbe -Exe $venvPython -Arguments @('-c', 'import pymupdf, pypdf, pdf2zh_next')
    if ($engineProbe.ExitCode -ne 0) { throw 'The translation engine is not importable after installation.' }
    $versionProbe = Invoke-NativeProbe -Exe $venvPython -Arguments @('-c', "import importlib.metadata as m; print(m.version('pdf2zh-next'))")
    $installedVersion = $versionProbe.Output
    if ($versionProbe.ExitCode -ne 0 -or -not $installedVersion) { throw 'The translation engine version cannot be read after installation.' }
    $markerJson = @{
        version = $installedVersion
        python = $venvPython
        installedAt = (Get-Date).ToString('o')
    } | ConvertTo-Json
    # Write UTF-8 without a BOM: Windows PowerShell's -Encoding utf8 adds one,
    # and JSON.parse on the plugin side would then fail on the marker.
    [IO.File]::WriteAllText((Join-Path $runtimeDir 'pdf2zh.json'), $markerJson,
        (New-Object System.Text.UTF8Encoding($false)))
}

$createdConfig = $false
if ((-not (Test-Path -LiteralPath $configPath)) -or ((Get-Item -LiteralPath $configPath).Length -eq 0)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot 'config.example.json') -Destination $configPath
    $createdConfig = $true
}

Write-Host ''
Write-Host 'PDF translator environment is ready.'
Write-Host "  Data directory: $DataDir"
Write-Host "  Python:         $venvPython"
Write-Host "  Config:         $configPath"
if ($createdConfig) {
    Write-Host 'Edit config.json and set base_url, model and api_key.'
}
Write-Host 'Restart or reload Harness, then run pdf_translator_doctor in a chat.'
