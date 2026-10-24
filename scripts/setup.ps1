param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$bundledPython = Join-Path $projectRoot 'runtime\python\python.exe'
if (Test-Path -LiteralPath $bundledPython) { $Python = $bundledPython }
& $Python -m venv (Join-Path $projectRoot '.venv')
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ is required.' }
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $venvPython -m pip install -r (Join-Path $projectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
$runtimePath = Join-Path $projectRoot 'runtime'
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
$packages = @(
    @{ Name='tectonic'; Exe='tectonic\tectonic.exe'; Url='https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-x86_64-pc-windows-msvc.zip' },
    @{ Name='pandoc'; Exe='pandoc\pandoc-3.12.1\pandoc.exe'; Url='https://github.com/jgm/pandoc/releases/download/3.12.1/pandoc-3.12.1-windows-x86_64.zip' }
)
foreach ($package in $packages) {
    if (!(Test-Path -LiteralPath (Join-Path $runtimePath $package.Exe))) {
        $archivePath = Join-Path $runtimePath ($package.Name + '.zip')
        Invoke-WebRequest $package.Url -OutFile $archivePath
        Expand-Archive -LiteralPath $archivePath -DestinationPath (Join-Path $runtimePath $package.Name) -Force
    }
}
$configPath = Join-Path $projectRoot 'config.json'
if (!(Test-Path -LiteralPath $configPath)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot 'config.example.json') -Destination $configPath
}
Write-Host 'Ready. Configure config.json with a vision-capable API. No local OCR models are required.'
