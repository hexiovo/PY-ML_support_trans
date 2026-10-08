# HyperEEG conversion implementation plan

## Background and context

The host already launches manifest-v1 external plugins and imports CSV/XLSX/XLS.
The user authorized a working HyperEEG converter, Chinese window, Windows release,
verification and a scoped master commit/push. HexiPlan was explicitly disabled.
The source contract is the 2026-10-08 HyperEEG feature plan and current MATLAB code.
There are eight reference XLSX files and no real feature MAT files in that repo.

## Acceptance criteria

- Preserve source files, value precision, missingness and row identity.
- Pivot feature coordinates into columns; never treat channels/bands as subjects.
- Read MATLAB table/string/cell through MATLAB, not guessed HDF5 reconstruction.
- Support FeatureResult.longData, old analysis-long-table XLSX, current feature
  file manifests, single-channel feature/band/connectivity/network CSV, and explicit
  scalar-column MAT tables. Require mapping for ambiguous identities or arrays.
- Preserve all source columns as sidecars; metadata, QA and inferential statistics
  must not silently become EEG inputs. No invented labels, imputation or fitting.
- Validate unique sample/feature keys and exact many-to-one metadata joins.
- Provide preview, explicit mapping, recursion, per-file/merged output, progress,
  cancellation, isolated failures and complete counts. No silent overwrite/re-entry.
- Test synthetic values/coordinates, all eight reference workbooks, native v7/v7.3
  objects, host import/selection, GUI state and host plugin settings/launch.
- Publish an existing verified EXE/manifest, source and reproducible build steps;
  record real-data limitations and preserve unrelated changes in both repos.

## Implementation details

1. Add a standalone `hypereeg_converter` package, `launch.py`, native MATLAB
   bridge and CLI. Use pandas/openpyxl for table reading and PySide6 for the window.
2. Read raw table cells as text and serialize numeric values without reformatting.
   A schema describes sample columns, coordinate columns, value columns and role.
   The native bridge writes double values with 17 significant digits.
3. Build stable sample and feature keys without sorting the source rows. Reject
   duplicate cells and conflicting metadata rather than averaging or dropping.
   Write dataset.csv, valid_mask.csv, feature dictionary, raw tables and provenance.
4. MATLAB exports only explicitly selected tables or FeatureResult.longData; native
   objects are decoded by load. Arbitrary numeric tensors require a source-specific
   export mapping and are reported as unsupported, never flattened automatically.
5. Each batch writes to a unique run directory and commits completed file packages
   atomically. Merged output aligns by explicit sample keys and rejects conflicts.
6. Build an isolated one-directory Windows plugin using PyInstaller. Run targeted
   temporary tests, retain a validation summary/screenshots, then delete fixtures.
7. Save plugin settings through the real host dialog and verify the host action and
   detached window launch without rebuilding or editing the host.

## Risks and limits

MATLAB must be installed/licensed for native MAT conversion; CSV/XLSX conversion
works from the standalone EXE. No real exported MAT data are available, so native
MAT checks use synthetic MATLAB objects only. High-dimensional arrays and fitted
cross-subject representations are not interpreted without explicit axes/fit metadata.
