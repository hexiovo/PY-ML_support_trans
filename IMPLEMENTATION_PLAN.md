# Optional data conversion plugin

## Background and context

PY-ML loads CSV/XLSX/XLS tables and now has a manifest-v1 external plugin interface.
The user requests optional batch data conversion, with the plugin code and package
in this repository. User datasets are converted locally for PY-ML, not uploaded.

## Acceptance criteria

- The top menu order is File, Analysis, Plugins, Help.
- Data conversion is disabled until a valid configured plugin is detected.
- Plugin settings remain available, including when no plugin is installed.
- Folder settings persist independently of experiments and existing preferences.
- Opening a menu only inspects configuration and files; it never executes a plugin.
- A missing or incompatible plugin is reported and leaves the main app usable.
- Source installations and future rebuilt EXEs can launch a separate plugin.
- Targeted unit and Qt integration checks cover these behaviors.
- Batch converter acceptance criteria require the user's source formats and layout.

## Implementation details

1. Add a small host module and settings dialog to PY-ML without new dependencies.
2. Read a versioned `pyml-plugin.json` from the configured folder. Support a
   separate executable or a Python script with an external Python interpreter.
3. Launch explicitly using QProcess.startDetached, with an argument array and
   the plugin folder as working directory.
4. Add the menu between Analysis and Help. Save settings to a separate JSON file
   beside the application preferences. Recheck on startup and menu opening.
5. Record host integration and its verification in both version records.
6. Implement the real batch converter only after source formats, data layout and
   export rules are specified. Rebuild and validate EXEs when the converter is ready.

Host files: `src/pyml_workbench/plugins.py`, `plugin_dialog.py`, a scoped addition
to `gui.py`, README and version records. Preserve existing uncommitted changes.

Tests use synthetic temporary plugin folders, isolated settings, and Qt offscreen
mode. Cover unset/invalid settings, missing files, incompatible manifests,
interpreter selection, paths containing Chinese/spaces, persistence, menu order,
disabled/enabled state and a detached synthetic process launch. Delete temporary
scripts and generated data after verification.

## HyperEEG implementation

The HyperEEG converter is implemented. Its scoped design, actual source-to-table
mapping and validation are documented in `docs/hypereeg-design.md`,
`docs/HyperEEG使用说明.md` and `docs/validation-summary.md`. Other projects remain
separate future work; no format is inferred merely from a project name.
