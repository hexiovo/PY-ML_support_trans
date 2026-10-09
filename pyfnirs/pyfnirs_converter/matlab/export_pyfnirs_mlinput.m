function export_pyfnirs_mlinput(inputMatPath, outputFolder)
%EXPORT_PYFNIRS_MLINPUT Export a PYfNIRsDA.Study MAT file as typed JSON.
%   MATLAB reads the v7.3 file so table and struct values retain their native
%   semantics. Numeric scalars are written as text (17 significant digits for
%   double) to make the interchange round-trip safe. Arrays keep their shape.
%
%   The function never modifies the source MAT file and refuses to overwrite
%   an existing output folder.

if nargin ~= 2
    error('PYfNIRs:Arguments', 'Expected input MAT path and output folder.');
end
inputMatPath = char(string(inputMatPath));
outputFolder = char(string(outputFolder));
if ~isfile(inputMatPath)
    error('PYfNIRs:InputMissing', 'Input MAT file does not exist: %s', inputMatPath);
end
if isfolder(outputFolder) || isfile(outputFolder)
    error('PYfNIRs:OutputExists', 'Refusing to overwrite existing output: %s', outputFolder);
end

loaded = load(inputMatPath, 'study');
if ~isfield(loaded, 'study') || ~isstruct(loaded.study) || ~isscalar(loaded.study)
    error('PYfNIRs:StudyMissing', 'MAT file must contain scalar struct study.');
end
study = loaded.study;
requiredFields = {'Kind', 'SchemaVersion', 'Sources', 'Observations', ...
    'PairLinks', 'FeatureDefinitions', 'Values', 'CovariateMetadata'};
for k = 1:numel(requiredFields)
    if ~isfield(study, requiredFields{k})
        error('PYfNIRs:StudyFieldMissing', 'study is missing field %s.', requiredFields{k});
    end
end
studyKind = scalarText(study.Kind, 'study.Kind');
if ~strcmp(studyKind, 'PYfNIRsDA.Study')
    error('PYfNIRs:WrongStudyKind', 'Expected study.Kind=PYfNIRsDA.Study.');
end
if ~isnumeric(study.SchemaVersion) || ~isscalar(study.SchemaVersion) || study.SchemaVersion ~= 1
    error('PYfNIRs:WrongSchemaVersion', 'Expected study.SchemaVersion=1.');
end
validateStudyTables(study);

[~, baseName, extension] = fileparts(inputMatPath);
tableExports = struct();
studyMetadata = struct();
studyFields = fieldnames(study);
for k = 1:numel(studyFields)
    fieldName = studyFields{k};
    if strcmp(fieldName, 'Kind') || strcmp(fieldName, 'SchemaVersion')
        continue;
    end
    fieldValue = study.(fieldName);
    if istable(fieldValue)
        tableExports.(fieldName) = encodeTable(fieldValue, fieldName);
    else
        studyMetadata.(fieldName) = encodeValue(fieldValue);
    end
end

if ~isfolder(fileparts(outputFolder))
    mkdir(fileparts(outputFolder));
end
[ok, message] = mkdir(outputFolder);
if ~ok
    error('PYfNIRs:OutputCreateFailed', 'Cannot create output folder: %s', message);
end

document = struct();
document.schema = 'pyfnirs.matlab-export/1';
document.study_kind = studyKind;
document.study_schema_version = 1;
document.source_file_name = [baseName, extension];
document.matlab_version = version;
document.matlab_release = version('-release');
document.exported_at = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
document.study_metadata = studyMetadata;
document.tables = tableExports;

jsonPath = fullfile(outputFolder, 'study_export.json');
fid = fopen(jsonPath, 'w', 'n', 'UTF-8');
if fid < 0
    error('PYfNIRs:ExportOpenFailed', 'Cannot create export JSON: %s', jsonPath);
end
fileCleanup = onCleanup(@() fclose(fid));
payload = jsonencode(document);
fwrite(fid, payload, 'char');
fwrite(fid, newline, 'char');
clear fileCleanup;
end

function requireColumns(value, required, label)
names = value.Properties.VariableNames;
for k = 1:numel(required)
    if ~ismember(required{k}, names)
        error('PYfNIRs:ColumnMissing', '%s is missing required column %s.', label, required{k});
    end
end
end

function validateStudyTables(study)
% Match the PYfNIRsDA schema field order and MATLAB column types.
validateBaseTable(study.Sources, ...
    {'SourceID','Kind','SchemaVersion','FilePath','PayloadPath', ...
    'Fingerprint','Adapter','Capability'}, ...
    {'string','string','double','string','string','string','string','string'}, ...
    'study.Sources', false);
validateBaseTable(study.Observations, ...
    {'ObservationID','RecordID','SubjectID','PairObservationID','Group', ...
    'Condition','Session','Timepoint','Include','SourceID'}, ...
    {'string','string','string','string','string','string','string', ...
    'string','logical','string'}, 'study.Observations', true);
validateBaseTable(study.PairLinks, ...
    {'PairObservationID','PairID','RecordIDA','RecordIDB','SubjectIDA', ...
    'SubjectIDB','RoleA','RoleB','Condition','Session','Timepoint'}, ...
    {'string','string','string','string','string','string','string', ...
    'string','string','string','string'}, 'study.PairLinks', false);
validateBaseTable(study.FeatureDefinitions, ...
    {'FeatureID','Metric','Level','Hemoglobin','NodeA','NodeB','RoleA', ...
    'RoleB','FrequencyLowHz','FrequencyHighHz','WindowStartSeconds', ...
    'WindowEndSeconds','Scale','Unit','Transform','Direction','Dimension', ...
    'ParameterFingerprint','MappingFingerprint'}, ...
    {'string','string','string','string','string','string','string', ...
    'string','double','double','double','double','double','string', ...
    'string','string','string','string','string'}, ...
    'study.FeatureDefinitions', false);
validateBaseTable(study.Values, ...
    {'ObservationID','FeatureID','Value','IsValid','MissingReason','SourceID'}, ...
    {'string','string','double','logical','string','string'}, ...
    'study.Values', false);
validateBaseTable(study.CovariateMetadata, ...
    {'ColumnName','Level','Origin','DataKey'}, ...
    {'string','string','string','string'}, 'study.CovariateMetadata', false);
end

function validateBaseTable(value, expectedNames, expectedTypes, label, allowCovariates)
if ~istable(value)
    error('PYfNIRs:ExpectedTable', '%s must be a MATLAB table.', label);
end
names = value.Properties.VariableNames;
baseCount = numel(expectedNames);
if numel(names) < baseCount || ~isequal(names(1:baseCount), expectedNames)
    error('PYfNIRs:WrongTableSchema', ...
        '%s must begin with the schema columns in the documented order.', label);
end
extra = names(baseCount + 1:end);
if ~isempty(extra) && (~allowCovariates || ...
        ~all(startsWith(string(extra), "Cov_")))
    error('PYfNIRs:UnexpectedTableColumn', ...
        '%s has unsupported columns after the schema fields.', label);
end
for index = 1:baseCount
    name = expectedNames{index};
    if ~strcmp(class(value.(name)), expectedTypes{index})
        error('PYfNIRs:WrongColumnType', ...
            '%s.%s must have MATLAB class %s.', label, name, expectedTypes{index});
    end
end
for index = 1:numel(extra)
    column = value.(extra{index});
    if ~(isstring(column) || isnumeric(column) || islogical(column) || ...
            iscategorical(column)) || size(column, 2) ~= 1
        error('PYfNIRs:WrongCovariateType', ...
            '%s.%s must be a scalar string, numeric, logical, or categorical column.', ...
            label, extra{index});
    end
end
end

function result = scalarText(value, label)
if isstring(value) && isscalar(value) && ~ismissing(value)
    result = char(value);
elseif ischar(value) && (isrow(value) || isempty(value))
    result = value;
elseif iscategorical(value) && isscalar(value) && ~ismissing(value)
    result = char(string(value));
else
    error('PYfNIRs:TextExpected', '%s must be a non-missing text scalar.', label);
end
end

function exported = encodeTable(value, tableName)
names = value.Properties.VariableNames;
columns = cell(1, numel(names));
units = value.Properties.VariableUnits;
descriptions = value.Properties.VariableDescriptions;
for c = 1:numel(names)
    variable = value.(names{c});
    column = struct();
    column.name = names{c};
    column.matlab_class = class(variable);
    if numel(units) >= c
        column.units = units{c};
    else
        column.units = '';
    end
    if numel(descriptions) >= c
        column.description = descriptions{c};
    else
        column.description = '';
    end
    if iscategorical(variable)
        column.categories = cellstr(categories(variable));
        column.is_ordinal = isordinal(variable);
    elseif isdatetime(variable)
        column.format = variable.Format;
        column.time_zone = variable.TimeZone;
    elseif isduration(variable)
        column.format = variable.Format;
    end
    columns{c} = column;
end

rows = cell(height(value), 1);
for r = 1:height(value)
    row = struct();
    for c = 1:numel(names)
        variable = value.(names{c});
        row.(names{c}) = encodeValue(variable(r, :));
    end
    rows{r} = row;
end

rowNames = value.Properties.RowNames;
exported = struct();
exported.table_name = tableName;
exported.row_count = height(value);
exported.columns = columns;
exported.rows = rows;
exported.row_names = rowNames;
end

function encoded = encodeValue(value)
className = class(value);
shape = size(value);
if istable(value)
    encoded = struct('matlab_class', 'table', 'shape', shape, 'table', encodeTable(value, 'nested'));
elseif isstruct(value)
    if isscalar(value)
        fields = struct();
        names = fieldnames(value);
        for k = 1:numel(names)
            fields.(names{k}) = encodeValue(value.(names{k}));
        end
        encoded = struct('matlab_class', 'struct', 'shape', shape, 'fields', fields);
    else
        elements = cell(numel(value), 1);
        for k = 1:numel(value)
            elements{k} = encodeValue(value(k));
        end
        encoded = struct('matlab_class', 'struct', 'shape', shape, 'elements', {elements});
    end
elseif iscell(value)
    elements = cell(numel(value), 1);
    for k = 1:numel(value)
        elements{k} = encodeValue(value{k});
    end
    encoded = struct('matlab_class', 'cell', 'shape', shape, 'elements', {elements});
elseif ischar(value) && (isrow(value) || isempty(value))
    encoded = struct('matlab_class', 'char', 'shape', shape, 'value', value, 'is_missing', false);
elseif isstring(value)
    if isscalar(value)
        missing = ismissing(value);
        if missing
            text = '';
        else
            text = char(value);
        end
        encoded = struct('matlab_class', 'string', 'shape', shape, 'value', text, 'is_missing', missing);
    else
        elements = cell(numel(value), 1);
        for k = 1:numel(value)
            elements{k} = encodeValue(value(k));
        end
        encoded = struct('matlab_class', 'string', 'shape', shape, 'elements', {elements});
    end
elseif iscategorical(value)
    if isscalar(value)
        missing = ismissing(value);
        if missing
            text = '';
        else
            text = char(string(value));
        end
        encoded = struct('matlab_class', 'categorical', 'shape', shape, 'value', text, 'is_missing', missing);
    else
        elements = cell(numel(value), 1);
        for k = 1:numel(value)
            elements{k} = encodeValue(value(k));
        end
        encoded = struct('matlab_class', 'categorical', 'shape', shape, 'elements', {elements});
    end
elseif isdatetime(value)
    if isscalar(value)
        missing = ismissing(value);
        if missing
            text = '';
        else
            text = char(value);
        end
        encoded = struct('matlab_class', 'datetime', 'shape', shape, 'value', text, ...
            'is_missing', missing, 'format', value.Format, 'time_zone', value.TimeZone);
    else
        elements = cell(numel(value), 1);
        for k = 1:numel(value)
            elements{k} = encodeValue(value(k));
        end
        encoded = struct('matlab_class', 'datetime', 'shape', shape, 'elements', {elements});
    end
elseif isduration(value)
    if isscalar(value)
        missing = ismissing(value);
        if missing
            text = '';
        else
            text = char(value);
        end
        encoded = struct('matlab_class', 'duration', 'shape', shape, 'value', text, ...
            'is_missing', missing, 'format', value.Format);
    else
        elements = cell(numel(value), 1);
        for k = 1:numel(value)
            elements{k} = encodeValue(value(k));
        end
        encoded = struct('matlab_class', 'duration', 'shape', shape, 'elements', {elements});
    end
elseif isnumeric(value) || islogical(value)
    if ~isreal(value)
        error('PYfNIRs:ComplexValue', 'Complex MATLAB values require an explicitly defined scientific mapping.');
    end
    if isscalar(value)
        encoded = struct('matlab_class', className, 'shape', shape, ...
            'value', numericText(value), 'is_missing', false);
    else
        elements = cell(numel(value), 1);
        for k = 1:numel(value)
            elements{k} = encodeValue(value(k));
        end
        encoded = struct('matlab_class', className, 'shape', shape, 'elements', {elements});
    end
else
    error('PYfNIRs:UnsupportedMatlabClass', ...
        'MATLAB class %s needs a registered lossless encoder before it can be exported.', className);
end
end

function result = numericText(value)
if islogical(value)
    if value
        result = 'true';
    else
        result = 'false';
    end
elseif isinteger(value)
    result = char(string(value));
elseif isnan(value)
    result = 'NaN';
elseif isinf(value)
    if value > 0
        result = 'Inf';
    else
        result = '-Inf';
    end
elseif isa(value, 'single')
    result = sprintf('%.9g', value);
else
    result = sprintf('%.17g', value);
end
end
