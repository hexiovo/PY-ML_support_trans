param([string]$Python = "$PSScriptRoot/../.venv/Scripts/python.exe", [string]$Revision = 'r1')
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath("$PSScriptRoot/..")
Push-Location $projectRoot
try {
    if ($Revision -notmatch '^[a-zA-Z0-9-]+$') { throw '发行修订号只允许字母、数字和连字符。' }
    $distRoot = Join-Path $projectRoot "dist/HyperEEG-0.1.0-$Revision"
    $releasePath = Join-Path $distRoot 'PYML-DataConversion'
    $zipPath = Join-Path $projectRoot "dist/PYML-DataConversion-HyperEEG-0.1.0-$Revision-windows-x64.zip"
    if ((Test-Path -LiteralPath $releasePath) -or (Test-Path -LiteralPath $zipPath)) { throw '此修订已有产物，请使用新修订号，原发行不覆盖。' }
    & $Python -m PyInstaller --noconfirm --clean --distpath $distRoot packaging/hypereeg.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 构建失败。' }
    $shot = Join-Path $projectRoot 'build/frozen-window.png'
    if (Test-Path -LiteralPath $shot) { Remove-Item -LiteralPath $shot }
    $process = Start-Process -FilePath "$releasePath/PYML-DataConversion.exe" -ArgumentList @('--smoke', "`"$shot`"") -PassThru -Wait -WindowStyle Hidden
    if ($process.ExitCode -ne 0 -or !(Test-Path -LiteralPath $shot)) { throw 'EXE 窗口启动验证失败。' }
    # Publish the manifest only after a real executable successfully starts.
    @{
        schema_version = 1; id = 'data-conversion'; name = '数据转换 · HyperEEG'; version = '0.1.0'
        entrypoint = @{kind = 'executable'; path = 'PYML-DataConversion.exe'}
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$releasePath/pyml-plugin.json" -Encoding utf8
    $docsRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot '../docs'))
    Copy-Item -LiteralPath (Join-Path $docsRoot 'HyperEEG使用说明.md') -Destination "$releasePath/使用说明.md"
    if (Test-Path -LiteralPath (Join-Path $docsRoot 'validation-summary.md')) {
        Copy-Item -LiteralPath (Join-Path $docsRoot 'validation-summary.md') -Destination "$releasePath/validation-summary.md"
    }
    if (Test-Path -LiteralPath $zipPath) { throw "发行压缩包已经存在，请保留原包并选择新版本：$zipPath" }
    Compress-Archive -LiteralPath $releasePath -DestinationPath $zipPath
    Get-FileHash -LiteralPath $zipPath -Algorithm SHA256
} finally { Pop-Location }
