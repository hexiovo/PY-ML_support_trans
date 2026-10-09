function export_pyfnirs_raw_mat(inputMatPath, outputJsonPath, sourceAdapterId)
%EXPORT_PYFNIRS_RAW_MAT Export a raw PYfNIRs Results MAT as typed JSON.
% The exporter preserves MATLAB shapes, struct/cell positions, table columns,
% and complex components. It does not select features or infer identities.

if nargin ~= 3
    error('PYfNIRs:RawExport:Arguments', ...
        'Expected input MAT path, output JSON path, and source adapter ID.');
end
inputMatPath = char(string(inputMatPath));
outputJsonPath = char(string(outputJsonPath));
sourceAdapterId = char(string(sourceAdapterId));
if ~strcmp(sourceAdapterId, 'pyfnirs.raw_results.v1')
    error('PYfNIRs:RawExport:Adapter', ...
        'Unsupported raw PYfNIRs source adapter ID.');
end
if ~isfile(inputMatPath)
    error('PYfNIRs:RawExport:InputMissing', ...
        'Input MAT file does not exist: %s', inputMatPath);
end
if isfile(outputJsonPath) || isfolder(outputJsonPath)
    error('PYfNIRs:RawExport:OutputExists', ...
        'Refusing to overwrite existing output: %s', outputJsonPath);
end

inventory = whos('-file', inputMatPath);
if ~any(strcmp({inventory.name}, 'Results'))
    error('PYfNIRs:RawExport:ResultsMissing', ...
        'Raw PYfNIRs MAT input must contain top-level variable Results.');
end
loaded = load(inputMatPath, 'Results');
if ~isstruct(loaded.Results) || ~isscalar(loaded.Results)
    error('PYfNIRs:RawExport:ResultsShape', ...
        'Top-level Results must be a scalar MATLAB struct.');
end
if isfield(loaded.Results, 'Kind') && ...
        ~strcmp(scalarText(loaded.Results.Kind, 'Results.Kind'), 'PYfNIRs.Results')
    error('PYfNIRs:RawExport:ResultsKind', ...
        'Results.Kind is present but is not PYfNIRs.Results.');
end

[~, baseName, extension] = fileparts(inputMatPath);
document = struct();
document.schema = 'pyfnirs.raw-mat-export/1';
document.source_adapter_id = sourceAdapterId;
document.source_file_name = [baseName, extension];
document.matlab_version = version;
document.matlab_release = version('-release');
document.exported_at = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
document.variables = struct('Results', encodeValue(loaded.Results));

parent = fileparts(outputJsonPath);
if ~isempty(parent) && ~isfolder(parent)
    mkdir(parent);
end
fid = fopen(outputJsonPath, 'w', 'n', 'UTF-8');
if fid < 0
    error('PYfNIRs:RawExport:OutputOpen', ...
        'Cannot create raw MAT export: %s', outputJsonPath);
end
cleanup = onCleanup(@() fclose(fid));
payload = jsonencode(document);
fwrite(fid, payload, 'char');
fwrite(fid, newline, 'char');
clear cleanup;
end

function encoded = encodeValue(value)
% Encode one MATLAB value without flattening its recorded MATLAB shape.
className = class(value);
shape = size(value);
if istable(value)
    encoded = struct('matlab_class', 'table', 'shape', shape, ...
        'table', encodeTable(value));
elseif isstruct(value)
    if isscalar(value)
        fields = struct();
        names = fieldnames(value);
        for index = 1:numel(names)
            fields.(names{index}) = encodeValue(value.(names{index}));
        end
        encoded = struct('matlab_class', 'struct', 'shape', shape, ...
            'fields', fields);
    else
        elements = cell(numel(value), 1);
        for index = 1:numel(value)
            elements{index} = encodeValue(value(index));
        end
        encoded = struct('matlab_class', 'struct', 'shape', shape, ...
            'elements', {elements});
    end
elseif iscell(value)
    elements = cell(numel(value), 1);
    for index = 1:numel(value)
        elements{index} = encodeValue(value{index});
    end
    encoded = struct('matlab_class', 'cell', 'shape', shape, ...
        'elements', {elements});
elseif ischar(value) && (isrow(value) || isempty(value))
    encoded = struct('matlab_class', 'char', 'shape', shape, ...
        'value', value, 'is_missing', false);
elseif isstring(value) || iscategorical(value) || isdatetime(value) || isduration(value)
    if isscalar(value)
        missing = ismissing(value);
        if missing
            text = '';
        elseif iscategorical(value)
            text = char(string(value));
        else
            text = char(value);
        end
        encoded = struct('matlab_class', className, 'shape', shape, ...
            'value', text, 'is_missing', missing);
        if isdatetime(value)
            encoded.format = value.Format;
            encoded.time_zone = value.TimeZone;
        elseif isduration(value)
            encoded.format = value.Format;
        end
    else
        elements = cell(numel(value), 1);
        for index = 1:numel(value)
            elements{index} = encodeValue(value(index));
        end
        encoded = struct('matlab_class', className, 'shape', shape, ...
            'elements', {elements});
    end
elseif isnumeric(value) || islogical(value)
    if ~isreal(value)
        realParts = cell(numel(value), 1);
        imagParts = cell(numel(value), 1);
        for index = 1:numel(value)
            realParts{index} = numericText(real(value(index)));
            imagParts{index} = numericText(imag(value(index)));
        end
        encoded = struct('matlab_class', className, 'shape', shape, ...
            'real_elements', {realParts}, 'imag_elements', {imagParts});
    elseif isscalar(value)
        encoded = struct('matlab_class', className, 'shape', shape, ...
            'value', numericText(value), 'is_missing', false);
    else
        elements = cell(numel(value), 1);
        for index = 1:numel(value)
            elements{index} = encodeValue(value(index));
        end
        encoded = struct('matlab_class', className, 'shape', shape, ...
            'elements', {elements});
    end
else
    error('PYfNIRs:RawExport:UnsupportedMatlabClass', ...
        'MATLAB class %s needs a registered lossless encoder.', className);
end
end

function exported = encodeTable(value)
names = value.Properties.VariableNames;
columns = cell(1, numel(names));
units = value.Properties.VariableUnits;
descriptions = value.Properties.VariableDescriptions;
for index = 1:numel(names)
    column = struct('name', names{index}, ...
        'matlab_class', class(value.(names{index})), ...
        'units', '', 'description', '');
    if numel(units) >= index && ~isempty(units{index})
        column.units = units{index};
    end
    if numel(descriptions) >= index && ~isempty(descriptions{index})
        column.description = descriptions{index};
    end
    columns{index} = column;
end
rows = cell(height(value), 1);
for rowIndex = 1:height(value)
    row = struct();
    for columnIndex = 1:numel(names)
        columnValues = value.(names{columnIndex});
        row.(names{columnIndex}) = encodeValue(columnValues(rowIndex, :));
    end
    rows{rowIndex} = row;
end
exported = struct('row_count', height(value), 'columns', {columns}, ...
    'rows', {rows}, 'row_names', {value.Properties.RowNames});
end

function text = scalarText(value, label)
if isstring(value) && isscalar(value) && ~ismissing(value)
    text = char(value);
elseif ischar(value) && (isrow(value) || isempty(value))
    text = value;
elseif iscategorical(value) && isscalar(value) && ~ismissing(value)
    text = char(string(value));
else
    error('PYfNIRs:RawExport:TextExpected', ...
        '%s must be a non-missing text scalar.', label);
end
end

function text = numericText(value)
if islogical(value)
    if value, text = 'true'; else, text = 'false'; end
elseif isinteger(value)
    text = char(string(value));
elseif isnan(value)
    text = 'NaN';
elseif isinf(value)
    if value > 0, text = 'Inf'; else, text = '-Inf'; end
elseif isa(value, 'single')
    text = sprintf('%.9g', value);
else
    text = sprintf('%.17g', value);
end
end
