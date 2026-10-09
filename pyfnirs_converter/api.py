"""Frozen public API for PYfNIRs-to-PY-ML conversion.

GUI, CLI, adapters, and automation should use these public types and
functions. The implementation is intentionally supplied by the core module.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any, Literal, TypeAlias


OutputRole: TypeAlias = Literal["target", "covariate"]
OutputFormat: TypeAlias = Literal["csv", "xlsx"]
MergeMode: TypeAlias = Literal["per_file", "merge"]
CollisionPolicy: TypeAlias = Literal["skip", "rename"]
ComplexProjection: TypeAlias = Literal["real", "imag", "magnitude", "phase"]
FileStatus: TypeAlias = Literal[
    "success", "failed", "skipped", "cancelled", "not_processed"
]
MLInput: TypeAlias = Mapping[str, Any]


@dataclass(frozen=True)
class FieldMapping:
    """Explicitly map one inspected source field to a named output column."""

    source_path: str
    output_name: str
    role: OutputRole


@dataclass(frozen=True)
class IdentityMapping:
    """Explicit source paths for observation and related identity fields."""

    observation_id_source_path: str
    record_id_source_path: str | None = None
    subject_id_source_path: str | None = None
    pair_observation_id_source_path: str | None = None
    pair_id_source_path: str | None = None
    source_id_source_path: str | None = None


@dataclass(frozen=True)
class FeatureSelection:
    """One registry-backed feature and all explicit scientific parameters.

    ``feature_id`` is the explicit identifier carried into the output. It is
    never inferred from row order, file names, or a capability label.
    """

    capability_id: str
    feature_id: str
    source_path: str
    axis_selection: Mapping[str, str | int]
    summary_parameters: Mapping[str, float | int | str]
    frequency_band_hz: tuple[float, float] | None = None
    time_window_seconds: tuple[float, float] | None = None
    complex_projection: ComplexProjection | None = None
    summary_method: str | None = None


@dataclass(frozen=True)
class ConversionSelection:
    """Frozen user choices shared by preview and conversion."""

    source_adapter_id: str
    identity: IdentityMapping
    feature_selections: tuple[FeatureSelection, ...]
    targets: tuple[FieldMapping, ...]
    covariates: tuple[FieldMapping, ...]
    output_format: OutputFormat
    merge_mode: MergeMode
    collision_policy: CollisionPolicy


@dataclass(frozen=True)
class BatchRequest:
    """Inputs and output destination for one batch conversion."""

    input_paths: tuple[Path, ...]
    output_dir: Path
    selection: ConversionSelection
    matlab_executable: Path | None = None
    recursive: bool = False


@dataclass(frozen=True)
class SourceField:
    """A source field reported by inspection, without inferred semantics."""

    path: str
    shape: tuple[int, ...]
    matlab_class: str
    sample_grain: str | None


@dataclass(frozen=True)
class FeatureCandidate:
    """A candidate feature and only the registered choices it permits.

    ``axes`` maps each axis name to its permitted values. A selection chooses
    one value per required axis in ``FeatureSelection.axis_selection``.
    Frequency bands and time windows are not assumed; a user may supply them
    explicitly in ``FeatureSelection`` and the adapter validates permission.
    """

    capability_id: str
    source_path: str
    shape: tuple[int, ...]
    unit: str | None
    axes: Mapping[str, tuple[str | int, ...]]
    allowed_summaries: tuple[str, ...]
    allowed_complex_projections: tuple[ComplexProjection, ...]
    status: str
    reason: str


@dataclass(frozen=True)
class SourceInspection:
    """Read-only inventory of a source file and its explicit candidates."""

    source_path: Path
    source_format: str
    available_adapters: tuple[str, ...]
    fields: tuple[SourceField, ...]
    feature_candidates: tuple[FeatureCandidate, ...]
    identity_candidates: tuple[str, ...]
    target_candidates: tuple[str, ...]
    covariate_candidates: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ConversionPreview:
    """A no-write preview for the exact selection that conversion will use."""

    sample_count: int
    selected_feature_ids: tuple[str, ...]
    output_columns: tuple[str, ...]
    targets: tuple[FieldMapping, ...]
    covariates: tuple[FieldMapping, ...]
    missing_count: int
    rejected_features: tuple[str, ...]
    merge_conflicts: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ProgressEvent:
    """Progress from one file within a batch."""

    index: int
    total: int
    source_path: Path
    phase: str
    percent: float
    message: str


@dataclass(frozen=True)
class FileResult:
    """Outcome for one source file; errors remain attached to that file."""

    source_path: Path
    status: FileStatus
    output_paths: tuple[Path, ...]
    sample_count: int | None
    feature_ids: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True)
class BatchResult:
    """Ordered per-file outcomes and whether the user cancelled the batch."""

    files: tuple[FileResult, ...]
    cancelled: bool


def inspect_source(
    path: Path,
    *,
    source_adapter_id: str | None = None,
    matlab_executable: Path | None = None,
) -> SourceInspection:
    """Inspect a source without guessing identity, target, or feature choices."""
    from .core import inspect_source as implementation

    return implementation(
        path,
        source_adapter_id=source_adapter_id,
        matlab_executable=matlab_executable,
    )


def preview_conversion(
    path: Path,
    selection: ConversionSelection,
    *,
    matlab_executable: Path | None = None,
) -> ConversionPreview:
    """Preview a conversion without writing files."""
    from .core import preview_conversion as implementation

    return implementation(path, selection, matlab_executable=matlab_executable)


def convert_export(
    document: Mapping[str, Any],
    selection: ConversionSelection,
) -> MLInput:
    """Convert a validated schema-1 MATLAB export into an in-memory MLInput."""
    from .core import convert_export as implementation

    return implementation(document, selection)


def convert_batch(
    request: BatchRequest,
    *,
    progress_callback: Callable[[ProgressEvent], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> BatchResult:
    """Convert files with per-file isolation, progress, and cooperative cancel."""
    from .batch import convert_batch as implementation

    return implementation(request, progress_callback=progress_callback, cancel_event=cancel_event)


__all__ = [
    "BatchRequest",
    "BatchResult",
    "CollisionPolicy",
    "ComplexProjection",
    "ConversionPreview",
    "ConversionSelection",
    "FeatureCandidate",
    "FeatureSelection",
    "FieldMapping",
    "FileStatus",
    "FileResult",
    "IdentityMapping",
    "MLInput",
    "MergeMode",
    "OutputFormat",
    "OutputRole",
    "ProgressEvent",
    "SourceField",
    "SourceInspection",
    "convert_batch",
    "convert_export",
    "inspect_source",
    "preview_conversion",
]
