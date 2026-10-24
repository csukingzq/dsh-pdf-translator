param(
    [string]$Python = '',
    [string]$DataDir = '',
    [switch]$Force,
    [string]$TectonicUrl = 'https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-x86_64-pc-windows-msvc.zip',
    [string]$PandocUrl = 'https://github.com/jgm/pandoc/releases/download/3.12.1/pandoc-3.12.1-windows-x86_64.zip'
)
$ErrorActionPreference = 'Stop'
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

function Test-PythonVersion {
    param([string]$Exe, [string[]]$Arguments = @())
    & $Exe @Arguments -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
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
    throw 'Python 3.10+ is required. Install Python or use the Python runtime bundled with DSH Desktop.'
}

function Install-ZipPackage {
    param([string]$Name, [string]$Url, [string]$Destination, [string]$ExeName)
    $existing = Get-ChildItem -LiteralPath $Destination -Filter $ExeName -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($existing) {
        Write-Host "$Name already installed: $($existing.FullName)"
        return
    }
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $archive = Join-Path ([IO.Path]::GetTempPath()) ("dsh-pdf-$Name-" + [guid]::NewGuid().ToString('N') + '.zip')
    try {
        Write-Host "Downloading $Name ..."
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $archive
        Expand-Archive -LiteralPath $archive -DestinationPath $Destination -Force
    } catch {
        throw "Failed to download or extract $Name`: $($_.Exception.Message)`nCheck the network and retry, or download manually: $Url"
    } finally {
        if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
    }
    $installed = Get-ChildItem -LiteralPath $Destination -Filter $ExeName -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $installed) { throw "$Name installation failed: $ExeName was not found. Check the download URL: $Url" }
    Write-Host "$Name installed: $($installed.FullName)"
}

$DataDir = Resolve-DataDir -Requested $DataDir
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
$venvDir = Join-Path $DataDir '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$runtimeDir = Join-Path $DataDir 'runtime'
$configPath = Join-Path $DataDir 'config.json'

if ($Force -and (Test-Path -LiteralPath $venvDir)) {
    Write-Host "Recreating Python environment: $venvDir"
    Remove-Item -LiteralPath $venvDir -Recurse -Force
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $base = Find-BasePython
    $baseArgs = @($base.Args)
    Write-Host "Creating Python environment with $($base.Exe) ..."
    & $base.Exe @baseArgs -m venv $venvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        throw "Failed to create the Python environment. Verify Python 3.10+: $($base.Exe)"
    }
}

Write-Host 'Installing Python dependencies ...'
& $venvPython -m pip install --disable-pip-version-check -r (Join-Path $projectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed. Check the network or pip configuration.' }
& $venvPython -c "import pymupdf, bs4" 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies are not importable after installation.' }

Install-ZipPackage -Name 'tectonic' -Url $TectonicUrl -Destination (Join-Path $runtimeDir 'tectonic') -ExeName 'tectonic.exe'
Install-ZipPackage -Name 'pandoc' -Url $PandocUrl -Destination (Join-Path $runtimeDir 'pandoc') -ExeName 'pandoc.exe'

$createdConfig = $false
if (-not (Test-Path -LiteralPath $configPath)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot 'config.example.json') -Destination $configPath
    $createdConfig = $true
}

Write-Host ''
Write-Host 'PDF translator environment is ready.'
Write-Host "  Data directory: $DataDir"
Write-Host "  Python:         $venvPython"
Write-Host "  Config:         $configPath"
if ($createdConfig) {
    Write-Host 'Edit config.json and set base_url, model and api_key for a vision-capable API.'
}
Write-Host 'Restart or reload Harness, then run pdf_translator_doctor in a chat.'
