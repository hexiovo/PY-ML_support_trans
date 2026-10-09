function create_raw_results_fixture(outputDirectory)
%CREATE_RAW_RESULTS_FIXTURE Create a genuine synthetic PYfNIRs Results MAT.
%   The source is synthetic and must not be presented as research data. Run
%   this function in MATLAB with an output folder that does not yet exist.

if nargin ~= 1
    error('PYfNIRs:Fixture:Arguments', 'Expected output directory.');
end
outputDirectory = char(string(outputDirectory));
if isfile(outputDirectory) || isfolder(outputDirectory)
    error('PYfNIRs:Fixture:OutputExists', ...
        'Refusing to overwrite fixture directory: %s', outputDirectory);
end
mkdir(outputDirectory);

fixtureDirectory = fileparts(mfilename('fullpath'));
repoRoot = fileparts(fileparts(fileparts(fixtureDirectory)));
addpath(fullfile(repoRoot, 'pyfnirs_converter', 'matlab', 'source_adapters'));

Results = struct();
Results.Kind = 'PYfNIRs.Results';
Results.SchemaVersion = uint32(1);
Results.RecordID = 'REC-SYN-17';
Results.SubjectID = 'SUB-SYN-9';
Results.ObservationID = 'OBS-SYN-17';
Results.Availability = table( ...
    "REC-SYN-17", "SUB-SYN-9", "synthetic_case", true, "available", 12, 1.0, ...
    'VariableNames', {'RecordID', 'SubjectID', 'Group', 'IsAvailable', ...
    'Reason', 'ValidSampleCount', 'ValidFraction'});

Results.data = struct();
Results.data.all = struct( ...
    'HbO', [1.0, 0.25; 0.25, 1.0], ...
    'HbR', [1.0, -0.4; -0.4, 1.0]);

Results.ROIdetail = struct('ROI_name', ["ROI-A"; "ROI-B"], 'ROI_num', 2);

Results.Metadata = struct();
Results.Metadata.FC = struct( ...
    'Kind', 'static', ...
    'ModelIndex', 1, ...
    'ParameterFingerprint', 'SYNTHETIC-PEARSON-v1', ...
    'NodeOrder', ["ROI-A"; "ROI-B"]);

formula = 'conditional_log_residual_variance_ratio_v1';
options = struct('Order', 2, 'Window', struct('Enabled', false));
Results.Metadata.MVARGranger = struct( ...
    'FormulaVersion', formula, ...
    'DirectionConvention', 'row_source_column_target', ...
    'SamplingRate', 10, ...
    'NodeLabels', ["ROI-A"; "ROI-B"], ...
    'Options', options);
Results.data.WithinBrainMVARGranger = struct( ...
    'HbO', struct('Status', 'ok', 'GrangerStrength', [0, 0.3; 0.7, 0]), ...
    'HbR', struct('Status', 'ok', 'GrangerStrength', [0, 0.1; 0.2, 0]));

phOptions = struct( ...
    'InputSemantics', 'positive_similarity', ...
    'ExternalLibrary', 'none_internal_matlab', ...
    'Threshold', 0.5);
h0 = struct( ...
    'TotalPersistence', 2.5, ...
    'PersistenceEntropy', 0.75, ...
    'FinitePositiveIntervalCount', 2, ...
    'InfiniteIntervalCount', 0);
h1 = struct( ...
    'TotalPersistence', 0.5, ...
    'PersistenceEntropy', 0.25, ...
    'FinitePositiveIntervalCount', 1, ...
    'InfiniteIntervalCount', 0);
h1Missing = h1;
h1Missing.TotalPersistence = NaN;
Results.Metadata.PersistentHomology = struct( ...
    'Options', phOptions, ...
    'NodeLabels', ["ROI-A"; "ROI-B"], ...
    'DistanceFormula', 'one_minus_similarity_v1');
Results.data.PersistentHomology = struct( ...
    'HbO', struct('Status', 'ok', 'Features', struct('H0', h0, 'H1', h1)), ...
    'HbR', struct('Status', 'ok', 'Features', struct('H0', h0, 'H1', h1Missing)));

Results.Metadata.MissingnessAudit = struct( ...
    'SchemaVersion', uint32(1), 'Algorithm', 'SyntheticRawFeatures');

matPath = fullfile(outputDirectory, 'raw_results_synthetic.mat');
save(matPath, 'Results', '-v7.3');
exportPath = fullfile(outputDirectory, 'raw_results_synthetic.json');
export_pyfnirs_raw_mat(matPath, exportPath, 'pyfnirs.raw_results.v1');

expected = struct();
expected.label = 'SYNTHETIC only; not research data';
expected.mat_file = 'raw_results_synthetic.mat';
expected.json_file = 'raw_results_synthetic.json';
expected.matlab_version = version;
expected.matlab_release = version('-release');
expected.mat_file_format = '-v7.3';
expected.top_level_variables = {'Results'};
expected.results_size = size(Results);
expected.results_fields = fieldnames(Results)';
expected.availability_size = size(Results.Availability);
expected.data_fields = fieldnames(Results.data)';
expected.fc_node_order = Results.Metadata.FC.NodeOrder';
expected.mvar_node_order = Results.Metadata.MVARGranger.NodeLabels';
expected.persistent_homology_node_order = Results.Metadata.PersistentHomology.NodeLabels';
expected.observation_id = 'OBS-SYN-17';
expected.record_id = 'REC-SYN-17';
expected.static_fc_hbo_roi_a_roi_b = 0.25;
expected.mvar_hbo_source_roi_a_target_roi_b = 0.3;
expected.persistent_homology_hbo_h0_total_persistence = 2.5;
expected.static_fc_hbr_roi_a_roi_b = -0.4;
expected.mvar_hbr_source_roi_a_target_roi_b = 0.1;
expected.persistent_homology_hbr_h1_total_persistence = 'NaN';
expected.persistent_homology_hbr_h1_is_valid = false;
expected.persistent_homology_hbr_h1_missing_reason = 'source_nonfinite';
expected.linear_index_note = ...
    'Matrices are stored MATLAB column-major; directed MVAR uses row=source,column=target.';
fid = fopen(fullfile(outputDirectory, 'expected.json'), 'w', 'n', 'UTF-8');
if fid < 0
    error('PYfNIRs:Fixture:ExpectedOpen', 'Cannot write the fixture oracle.');
end
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, jsonencode(expected), 'char');
fwrite(fid, newline, 'char');
clear cleanup;
end
