param([string]$PythonPath)
$ErrorActionPreference = 'Stop'
if (-not $PythonPath) {
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundledPython) { $PythonPath = $bundledPython }
    else { $PythonPath = 'python' }
}
Push-Location $PSScriptRoot
try {
    & $PythonPath -m unittest -v test_cc_tools
    if ($LASTEXITCODE -ne 0) { throw 'Offline verification failed.' }
    $outputDir = Join-Path $PSScriptRoot ('runs\pilot-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    & $PythonPath cc_tools.py build --trace examples/pilot_trace.json --config examples/pilot_config.json --out $outputDir
    if ($LASTEXITCODE -ne 0) { throw 'Plan generation failed.' }
    & $PythonPath cc_tools.py summarize --plan (Join-Path $outputDir 'plan.json') --runs (Join-Path $outputDir 'runs_template.csv') --out (Join-Path $outputDir 'pending_report.json')
    if ($LASTEXITCODE -ne 0) { throw 'Template verification failed.' }
    Write-Output "Created offline plan: $outputDir"
} finally {
    Pop-Location
}
