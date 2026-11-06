param(
  [string]$DataDir = (Join-Path $env:USERPROFILE '.dsh\dsh-pdf-translator'),
  [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$engineRoot = Join-Path $DataDir 'structure-runtime'
& $Python -m venv $engineRoot
if ($LASTEXITCODE -ne 0) { throw 'Cannot create isolated structure environment.' }
$enginePython = Join-Path $engineRoot 'Scripts\python.exe'
$requirements = Join-Path $PSScriptRoot '..\requirements-structure.txt'
& $enginePython -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r $requirements
if ($LASTEXITCODE -ne 0) {
  & $enginePython -m pip install --index-url https://pypi.org/simple -r $requirements
  if ($LASTEXITCODE -ne 0) { throw 'Structure dependency installation failed.' }
}
& $enginePython -m pip install --index-url https://www.paddlepaddle.org.cn/packages/stable/cpu/ paddlepaddle==3.2.0
if ($LASTEXITCODE -ne 0) { throw 'Paddle CPU installation failed; configuration was not changed.' }
$configPath = Join-Path $DataDir 'config.json'
$config = if (Test-Path -LiteralPath $configPath) {
  Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
} else { [pscustomobject]@{} }
$config | Add-Member -NotePropertyName structure_python -NotePropertyValue $enginePython -Force
$config | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $configPath -Encoding UTF8
Write-Output 'Structure worker installed. The first extraction may download verified model assets.'
