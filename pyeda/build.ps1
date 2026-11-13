param(
    [string]$Python = 'python',
    [string]$BuildRoot = (Join-Path $PSScriptRoot 'build')
)
$ErrorActionPreference = 'Stop'
$version = (Get-Content -Raw (Join-Path $PSScriptRoot 'pyml-plugin.json') | ConvertFrom-Json).version
$name = 'PYEDA-DataConversion'
$output = Join-Path $BuildRoot $name
$archive = Join-Path $BuildRoot "$name-$version-windows-x64.zip"
if ((Test-Path -LiteralPath $output) -or (Test-Path -LiteralPath $archive)) {
    throw '请使用新的构建目录，以保留既有发布文件。'
}
New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
& $Python -m PyInstaller --noconfirm --clean --windowed --noupx --name $name `
    --distpath $BuildRoot --workpath (Join-Path $BuildRoot 'work') `
    --specpath $BuildRoot (Join-Path $PSScriptRoot 'launch_eda.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 构建失败。' }
$manifest = Get-Content -Raw (Join-Path $PSScriptRoot 'pyml-plugin.json') | ConvertFrom-Json
$manifest.entrypoint.kind = 'executable'
$manifest.entrypoint.path = "$name.exe"
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $output 'pyml-plugin.json')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README.md') -Destination $output
Compress-Archive -LiteralPath $output -DestinationPath $archive -CompressionLevel Optimal
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
"$hash  $(Split-Path -Leaf $archive)" | Set-Content -Encoding ascii (Join-Path $BuildRoot 'SHA256SUMS.txt')
Write-Output $archive
