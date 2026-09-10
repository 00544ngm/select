$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RestartScript = Join-Path $ProjectRoot 'scripts\restart-and-verify.ps1'

& $RestartScript
exit $LASTEXITCODE
