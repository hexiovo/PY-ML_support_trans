param(
    [string]$Python = (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
    [Parameter(Mandatory = $true)][string]$SyntheticStudyExport,
    [Parameter(Mandatory = $true)][string]$ValidationRoot,
    [string]$SyntheticRawMat,
    [string]$MatlabExecutable,
    [string]$ManifestVersion = '0.1.0'
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$pythonPath = [System.IO.Path]::GetFullPath($Python)
$distRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'dist'))
$buildRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build'))
$releasePath = [System.IO.Path]::GetFullPath((Join-Path $distRoot 'PYfNIRs-DataConversion'))
$validationPath = [System.IO.Path]::GetFullPath($ValidationRoot)
$buildId = [Guid]::NewGuid().ToString('N')
$stagingRoot = Join-Path $distRoot ".pyfnirs-stage-$buildId"
$stagedRelease = Join-Path $stagingRoot 'PYfNIRs-DataConversion'
$workPath = Join-Path $buildRoot "pyfnirs-$buildId"

if (!(Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw "Build Python was not found: $pythonPath" }
if (!(Test-Path -LiteralPath (Join-Path $projectRoot 'pyfnirs.spec') -PathType Leaf)) { throw 'pyfnirs.spec is missing.' }
if (Test-Path -LiteralPath $releasePath) { throw "The release path already exists; refusing to overwrite it: $releasePath" }
if (Test-Path -LiteralPath $stagingRoot) { throw "The private staging directory already exists: $stagingRoot" }
if (Test-Path -LiteralPath $validationPath) { throw "Validation output already exists; choose a new path: $validationPath" }
if ($ManifestVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'ManifestVersion must use three numeric components.' }
if ([string]::IsNullOrWhiteSpace($SyntheticRawMat) -ne [string]::IsNullOrWhiteSpace($MatlabExecutable)) {
    throw 'SyntheticRawMat and MatlabExecutable must be provided together.'
}

$studyPath = $null
$studyItem = Get-Item -LiteralPath $SyntheticStudyExport
if ($studyItem.PSIsContainer) {
    $candidates = @(
        (Join-Path $studyItem.FullName 'export/study_export.json'),
        (Join-Path $studyItem.FullName 'study_export.json')
    )
    $studyPath = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
} else {
    $studyPath = $studyItem.FullName
}
if (!$studyPath -or [System.IO.Path]::GetFileName($studyPath) -ine 'study_export.json') {
    throw 'SyntheticStudyExport must identify a study_export.json file or its fixture directory.'
}
$studyPath = [System.IO.Path]::GetFullPath($studyPath)
$studyDirectory = [System.IO.Path]::GetDirectoryName($studyPath)
$fixtureRoot = if ([System.IO.Path]::GetFileName($studyDirectory) -ieq 'export') {
    [System.IO.Directory]::GetParent($studyDirectory).FullName
} else {
    $studyDirectory
}
$expectedPath = Join-Path $fixtureRoot 'expected.json'
if (!(Test-Path -LiteralPath $expectedPath -PathType Leaf)) { throw "The synthetic fixture oracle is missing: $expectedPath" }

$expected = Get-Content -LiteralPath $expectedPath -Raw -Encoding utf8 | ConvertFrom-Json
$featureIds = @($expected.feature_ids)
if ($featureIds.Count -lt 1 -or @($featureIds | Where-Object { !($_ -is [string]) -or [string]::IsNullOrWhiteSpace($_) }).Count -gt 0) {
    throw 'The synthetic fixture oracle must contain nonempty feature_ids.'
}

$pinned = Select-String -LiteralPath (Join-Path $projectRoot 'requirements-build.txt') -Pattern '^pyinstaller==([^\s;]+)' | Select-Object -First 1
if (!$pinned) { throw 'requirements-build.txt does not pin PyInstaller.' }
$expectedPyInstaller = $pinned.Matches[0].Groups[1].Value
$pythonVersion = (& $pythonPath --version 2>&1 | Out-String).Trim()
$pyInstallerVersion = (& $pythonPath -m PyInstaller --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $pyInstallerVersion -ne $expectedPyInstaller) {
    throw "PyInstaller must match requirements-build.txt ($expectedPyInstaller); found '$pyInstallerVersion'."
}

New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
New-Item -ItemType Directory -Path $validationPath | Out-Null
New-Item -ItemType Directory -Path $stagingRoot | Out-Null
New-Item -ItemType Directory -Path $workPath | Out-Null
Push-Location $projectRoot
try {
    & $pythonPath -m PyInstaller --noconfirm --clean --distpath $stagingRoot --workpath $workPath (Join-Path $projectRoot 'pyfnirs.spec')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed to build the PYfNIRs executable.' }

    $exePath = Join-Path $stagedRelease 'PYfNIRs-DataConversion.exe'
    if (!(Test-Path -LiteralPath $exePath -PathType Leaf)) { throw "The frozen entrypoint is missing: $exePath" }

    $guiReportPath = Join-Path $validationPath 'gui-smoke.json'
    $guiArguments = @('--package-smoke-gui', '--report', ('"' + $guiReportPath + '"'))
    $guiProcess = Start-Process -FilePath $exePath -ArgumentList $guiArguments -PassThru -Wait -WindowStyle Hidden
    if ($guiProcess.ExitCode -ne 0 -or !(Test-Path -LiteralPath $guiReportPath -PathType Leaf)) {
        throw "Frozen Qt window smoke failed with exit code $($guiProcess.ExitCode)."
    }
    $guiReport = Get-Content -LiteralPath $guiReportPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($guiReport.status -ne 'qt_window_smoke_passed' -or !$guiReport.rendered_size) {
        throw 'Frozen Qt window smoke report did not confirm a rendered window.'
    }

    $conversionReports = @{}
    $conversionOutputs = @{}
    foreach ($format in @('csv', 'xlsx')) {
        $featureSelections = @(
            foreach ($featureId in $featureIds) {
                @{
                    capability_id = 'study-defined'
                    feature_id = $featureId
                    source_path = 'study.Values'
                    axis_selection = @{}
                    summary_parameters = @{}
                }
            }
        )
        $selection = [ordered]@{
            source_adapter_id = 'pyfnirs.study_export.v1'
            identity = [ordered]@{
                observation_id_source_path = 'study.Observations.ObservationID'
                record_id_source_path = 'study.Observations.RecordID'
                subject_id_source_path = 'study.Observations.SubjectID'
                pair_observation_id_source_path = 'study.Observations.PairObservationID'
                pair_id_source_path = $null
                source_id_source_path = 'study.Observations.SourceID'
            }
            feature_selections = $featureSelections
            targets = @(@{ source_path = 'study.Observations.Group'; output_name = 'Group' })
            covariates = @(@{ source_path = 'study.Observations.Cov_AgeYears'; output_name = 'AgeYears' })
            output_format = $format
            merge_mode = 'per_file'
            collision_policy = 'skip'
        }
        $selectionPath = Join-Path $validationPath "$format-selection.json"
        $selection | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $selectionPath -Encoding utf8

        $outputPath = Join-Path $validationPath "$format-output"
        $reportPath = Join-Path $validationPath "$format-conversion.json"
        $convertArguments = @(
            '--package-smoke-convert',
            '--input', ('"' + $studyPath + '"'),
            '--selection', ('"' + $selectionPath + '"'),
            '--output-dir', ('"' + $outputPath + '"'),
            '--report', ('"' + $reportPath + '"')
        )
        $convertProcess = Start-Process -FilePath $exePath -ArgumentList $convertArguments -PassThru -Wait -WindowStyle Hidden
        $convertExitCode = $convertProcess.ExitCode
        if ($convertExitCode -ne 0 -or !(Test-Path -LiteralPath $reportPath -PathType Leaf)) {
            throw "Frozen $format conversion failed with exit code $convertExitCode."
        }
        $report = Get-Content -LiteralPath $reportPath -Raw -Encoding utf8 | ConvertFrom-Json
        $files = @($report.conversion_result.files)
        if ($report.status -ne 'conversion_passed' -or $files.Count -ne 1 -or $files[0].status -ne 'success') {
            throw "Frozen $format conversion did not report one successful input: $reportPath"
        }

        $conversionReports[$format] = $reportPath
        $conversionOutputs[$format] = @(
            Get-ChildItem -LiteralPath $outputPath -File -Recurse | ForEach-Object {
                [ordered]@{ path = $_.FullName; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
            }
        )
        if ($format -eq 'csv') {
            $matrixFiles = @(Get-ChildItem -LiteralPath $outputPath -File -Recurse -Filter 'FeatureMatrix.csv')
            if ($matrixFiles.Count -ne 1) { throw 'Frozen CSV conversion did not produce exactly one FeatureMatrix.csv.' }
            $conversionOutputs['csv_feature_matrix'] = $matrixFiles[0].FullName
        } else {
            $xlsxFiles = @(Get-ChildItem -LiteralPath $outputPath -File -Recurse -Filter '*.xlsx')
            if ($xlsxFiles.Count -ne 1) { throw 'Frozen XLSX conversion did not produce exactly one workbook.' }
            $conversionOutputs['xlsx_workbook'] = $xlsxFiles[0].FullName
        }
    }

    $matlabRelease = 'not-executed'
    if ($SyntheticRawMat) {
        $rawPath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $SyntheticRawMat).Path)
        $matlabPath = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $MatlabExecutable).Path)
        if (!(Test-Path -LiteralPath $rawPath -PathType Leaf) -or [System.IO.Path]::GetExtension($rawPath) -ine '.mat') {
            throw 'SyntheticRawMat must identify a MATLAB .mat file.'
        }
        if (!(Test-Path -LiteralPath $matlabPath -PathType Leaf)) { throw "MATLAB executable was not found: $matlabPath" }
        $matlabCheck = (& $matlabPath -batch "fprintf('MATLAB_RELEASE=%s\n', version('-release'));") | Out-String
        if ($LASTEXITCODE -ne 0 -or $matlabCheck -notmatch 'MATLAB_RELEASE=2023a') {
            throw "Raw MAT validation requires MATLAB R2023a; found: $matlabCheck"
        }
        $matlabRelease = '2023a'

        $rawFeatureSelections = @(
            @{
                capability_id = '24'; feature_id = 'PH-HBO-H0-PERSISTENCE';
                source_path = 'Results.data.PersistentHomology';
                axis_selection = @{ hemoglobin = 'HbO'; input_semantics = 'positive_similarity'; summary = 'H0:TotalPersistence' };
                summary_parameters = @{}
            },
            @{
                capability_id = '07'; feature_id = 'FC-HBO-ROI-A-ROI-B';
                source_path = 'Results.data.all';
                axis_selection = @{ algorithm = 'Pearson'; hemoglobin = 'HbO'; node_a = 'ROI-A'; node_b = 'ROI-B' };
                summary_parameters = @{}
            },
            @{
                capability_id = '14'; feature_id = 'MVAR-HBO-ROI-A-TO-ROI-B';
                source_path = 'Results.data.WithinBrainMVARGranger';
                axis_selection = @{ formula = 'conditional_log_residual_variance_ratio_v1'; hemoglobin = 'HbO'; source_node = 'ROI-A'; target_node = 'ROI-B' };
                summary_parameters = @{}
            },
            @{
                capability_id = '24'; feature_id = 'PH-HBR-H1-PERSISTENCE-MISSING';
                source_path = 'Results.data.PersistentHomology';
                axis_selection = @{ hemoglobin = 'HbR'; input_semantics = 'positive_similarity'; summary = 'H1:TotalPersistence' };
                summary_parameters = @{}
            }
        )
        $rawSelection = [ordered]@{
            source_adapter_id = 'pyfnirs.raw_results.v1'
            identity = [ordered]@{ observation_id_source_path = 'Results.ObservationID' }
            feature_selections = $rawFeatureSelections
            targets = @()
            covariates = @()
            output_format = 'csv'
            merge_mode = 'per_file'
            collision_policy = 'skip'
        }
        $rawSelectionPath = Join-Path $validationPath 'raw-mat-selection.json'
        $rawSelection | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $rawSelectionPath -Encoding utf8
        $rawOutputPath = Join-Path $validationPath 'raw-mat-output'
        $rawReportPath = Join-Path $validationPath 'raw-mat-conversion.json'
        $rawArguments = @(
            '--package-smoke-convert',
            '--input', ('"' + $rawPath + '"'),
            '--selection', ('"' + $rawSelectionPath + '"'),
            '--output-dir', ('"' + $rawOutputPath + '"'),
            '--report', ('"' + $rawReportPath + '"'),
            '--matlab', ('"' + $matlabPath + '"')
        )
        $rawProcess = Start-Process -FilePath $exePath -ArgumentList $rawArguments -PassThru -Wait -WindowStyle Hidden
        $rawExitCode = $rawProcess.ExitCode
        if ($rawExitCode -ne 0 -or !(Test-Path -LiteralPath $rawReportPath -PathType Leaf)) {
            throw "Frozen raw MAT conversion failed with exit code $rawExitCode."
        }
        $rawReport = Get-Content -LiteralPath $rawReportPath -Raw -Encoding utf8 | ConvertFrom-Json
        $rawFiles = @($rawReport.conversion_result.files)
        if ($rawReport.status -ne 'conversion_passed' -or $rawFiles.Count -ne 1 -or $rawFiles[0].status -ne 'success') {
            throw 'Frozen raw MAT conversion did not report one successful input.'
        }
        $rawMatrixFiles = @(Get-ChildItem -LiteralPath $rawOutputPath -File -Recurse -Filter 'FeatureMatrix.csv')
        if ($rawMatrixFiles.Count -ne 1) { throw 'Frozen raw MAT conversion did not produce exactly one FeatureMatrix.csv.' }
        $conversionReports['raw_mat'] = $rawReportPath
        $conversionOutputs['raw_mat_feature_matrix'] = $rawMatrixFiles[0].FullName
    }

    $internalRoot = Join-Path $stagedRelease '_internal'
    $registryPath = Join-Path $internalRoot 'pyfnirs_converter/capabilities.json'
    $studyHelperPath = Join-Path $internalRoot 'pyfnirs_converter/matlab/export_pyfnirs_mlinput.m'
    $rawHelperPath = Join-Path $internalRoot 'pyfnirs_converter/matlab/source_adapters/export_pyfnirs_raw_mat.m'
    if (!(Test-Path -LiteralPath $registryPath -PathType Leaf)) { throw 'Frozen capability registry is missing.' }
    if (!(Test-Path -LiteralPath $studyHelperPath -PathType Leaf)) { throw 'Frozen study MATLAB helper is missing.' }
    if (!(Test-Path -LiteralPath $rawHelperPath -PathType Leaf)) { throw 'Frozen raw MAT MATLAB helper is missing.' }

    $manifest = [ordered]@{
        schema_version = 1
        id = 'data-conversion'
        source_project = 'PYfNIRs'
        name = 'PYfNIRs 数据转换器'
        version = $ManifestVersion
        entrypoint = [ordered]@{ kind = 'executable'; path = 'PYfNIRs-DataConversion.exe' }
    }
    $manifestPath = Join-Path $stagedRelease 'pyml-plugin.json'
    if (Test-Path -LiteralPath $manifestPath) { throw 'A package manifest already exists in the staged release.' }
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText(
        $manifestPath,
        (($manifest | ConvertTo-Json -Depth 8) + "`n"),
        $utf8NoBom
    )

    if (Test-Path -LiteralPath $releasePath) { throw "The release path appeared during the build; refusing to overwrite it: $releasePath" }
    Move-Item -LiteralPath $stagedRelease -Destination $releasePath
    if ((Get-ChildItem -LiteralPath $stagingRoot -Force | Measure-Object).Count -eq 0) {
        Remove-Item -LiteralPath $stagingRoot -Force
    }

    [ordered]@{
        status = 'PASS'
        python_version = $pythonVersion
        pyinstaller_version = $pyInstallerVersion
        release_directory = $releasePath
        entrypoint = Join-Path $releasePath 'PYfNIRs-DataConversion.exe'
        manifest = Join-Path $releasePath 'pyml-plugin.json'
        manifest_version = $ManifestVersion
        manifest_source_project = 'PYfNIRs'
        registry_sha256 = (Get-FileHash -LiteralPath (Join-Path $releasePath '_internal/pyfnirs_converter/capabilities.json') -Algorithm SHA256).Hash.ToLowerInvariant()
        gui_smoke_report = $guiReportPath
        conversion_reports = $conversionReports
        conversion_outputs = $conversionOutputs
        matlab_release = $matlabRelease
        validation_temporary = $validationPath
        note = 'JSON conversion passed through the frozen executable without MATLAB; raw MAT requires external MATLAB R2023a.'
    } | ConvertTo-Json -Depth 12
} finally {
    Pop-Location
    $resolvedWorkPath = [System.IO.Path]::GetFullPath($workPath)
    $buildPrefix = $buildRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    $safeWorkPath = $resolvedWorkPath.StartsWith($buildPrefix, [System.StringComparison]::OrdinalIgnoreCase) -and
        [System.IO.Path]::GetFileName($resolvedWorkPath) -eq "pyfnirs-$buildId"
    if ($safeWorkPath -and (Test-Path -LiteralPath $resolvedWorkPath)) {
        Remove-Item -LiteralPath $resolvedWorkPath -Recurse -Force
    }
}
