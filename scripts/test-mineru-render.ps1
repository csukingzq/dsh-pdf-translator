param([string]$Python = 'python', [string]$Environment = '')
$ErrorActionPreference = 'Stop'
if (-not $Environment) { $Environment = Join-Path $env:TEMP 'dsh-mineru-render-tests' }
& $Python -m venv $Environment
if ($LASTEXITCODE -ne 0) { throw 'Cannot create isolated renderer test environment.' }
$rendererPython = Join-Path $Environment 'Scripts/python.exe'
$installed = $false
foreach ($index in @('https://pypi.tuna.tsinghua.edu.cn/simple', 'https://pypi.org/simple')) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $rendererPython -m pip install --disable-pip-version-check --no-input --timeout 30 --retries 1 -i $index -r (Join-Path (Split-Path $PSScriptRoot -Parent) 'requirements-mineru-render.txt')
        $installed = $LASTEXITCODE -eq 0
    } finally { $ErrorActionPreference = $previous }
    if ($installed) { break }
}
if (-not $installed) { throw 'Cannot install MinerU PDF renderer dependencies.' }
& $rendererPython -m unittest discover -s (Join-Path (Split-Path $PSScriptRoot -Parent) 'work') -p test_mineru_math.py
if ($LASTEXITCODE -ne 0) { throw 'MinerU formula rendering tests failed.' }
