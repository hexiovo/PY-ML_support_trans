"""Invoke MATLAB's lossless interchange exporters for native MAT inputs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Mapping
from typing import Any

from .contracts import ContractError


STUDY_MAT_ADAPTER_ID = "pyfnirs.study_mat.v1"
RAW_RESULTS_ADAPTER_ID = "pyfnirs.raw_results.v1"
RAW_MAT_EXPORT_SCHEMA = "pyfnirs.raw-mat-export/1"
RAW_MAT_EXPORT_FUNCTION = "export_pyfnirs_raw_mat"
STUDY_EXPORT_FUNCTION = "export_pyfnirs_mlinput"


class MatlabBridgeError(RuntimeError):
    """Raised when MATLAB cannot export a source file without data loss."""


class MatlabBridgeCancelled(MatlabBridgeError):
    """Raised when a batch cancellation terminates an active MATLAB process."""


def _matlab_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _resolve_matlab(executable: str | Path | None) -> str:
    if executable is not None:
        path = Path(executable).expanduser()
        if not path.is_file():
            raise MatlabBridgeError(f"MATLAB executable does not exist: {path}")
        return str(path.resolve())
    found = shutil.which("matlab")
    if found:
        return found
    raise MatlabBridgeError("MATLAB was not found; select its executable or provide a validated study_export.json")


def _temporary_root() -> Path | None:
    configured = os.environ.get("PYFNIRS_TEMP_DIR")
    if not configured:
        return None
    root = Path(configured).expanduser()
    if not root.is_dir():
        raise MatlabBridgeError(f"PYFNIRS_TEMP_DIR is not an existing directory: {root}")
    return root


def _run_matlab(
    executable: str,
    command: str,
    *,
    cwd: Path,
    cancel_event: threading.Event | None,
    timeout_seconds: float,
) -> str:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            [executable, "-batch", command],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
    except OSError as exc:
        raise MatlabBridgeError(f"Could not start MATLAB: {exc}") from exc

    deadline = time.monotonic() + timeout_seconds
    output = ""
    while True:
        if cancel_event is not None and cancel_event.is_set():
            process.terminate()
            try:
                output, _ = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate()
            raise MatlabBridgeCancelled("MATLAB export was cancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            process.kill()
            output, _ = process.communicate()
            raise MatlabBridgeError(f"MATLAB export timed out after {timeout_seconds:g} seconds")
        try:
            output, _ = process.communicate(timeout=min(0.5, remaining))
            break
        except subprocess.TimeoutExpired:
            continue
    if process.returncode != 0:
        details = output.strip()
        if len(details) > 2400:
            details = details[-2400:]
        raise MatlabBridgeError(
            "MATLAB export failed"
            + (f" (exit {process.returncode})" if process.returncode is not None else "")
            + (f": {details}" if details else ".")
        )
    return output


def export_mat_document(
    source_path: str | Path,
    *,
    matlab_executable: str | Path | None = None,
    source_adapter_id: str | None = None,
    cancel_event: threading.Event | None = None,
    timeout_seconds: float = 900.0,
) -> Mapping[str, Any]:
    """Read a native MAT file and return its validated schema-1 or raw envelope.

    ``pyfnirs.study_mat.v1`` uses the existing study-table exporter. Other IDs,
    use the lossless raw-tree exporter. With no ID, inspection tries the raw
    Results adapter first and falls back to the validated Study-table bridge.
    The raw exporter is implemented under ``matlab/source_adapters``.
    """
    source = Path(source_path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".mat":
        raise MatlabBridgeError(f"MAT source is not an existing .mat file: {source}")
    executable = _resolve_matlab(matlab_executable)
    matlab_root = Path(__file__).resolve().parent / "matlab"
    if not matlab_root.is_dir():
        raise MatlabBridgeError(f"MATLAB bridge directory does not exist: {matlab_root}")

    temp_root = _temporary_root()
    if source_adapter_id is None:
        try:
            return export_mat_document(
                source,
                matlab_executable=executable,
                source_adapter_id=RAW_RESULTS_ADAPTER_ID,
                cancel_event=cancel_event,
                timeout_seconds=timeout_seconds,
            )
        except MatlabBridgeError as raw_error:
            try:
                return export_mat_document(
                    source,
                    matlab_executable=executable,
                    source_adapter_id=STUDY_MAT_ADAPTER_ID,
                    cancel_event=cancel_event,
                    timeout_seconds=timeout_seconds,
                )
            except MatlabBridgeError as study_error:
                raise MatlabBridgeError(
                    "MAT input matched neither the supported raw Results adapter nor the schema-1 Study bridge; "
                    f"raw adapter: {raw_error}; Study bridge: {study_error}"
                ) from study_error

    with tempfile.TemporaryDirectory(
        prefix="pyfnirs-mat-", dir=str(temp_root) if temp_root else None
    ) as temporary_name:
        temporary_dir = Path(temporary_name)
        if source_adapter_id == STUDY_MAT_ADAPTER_ID:
            output_path = temporary_dir / "study_export.json"
            command = (
                f"addpath(genpath({_matlab_quote(matlab_root)}));"
                f"{STUDY_EXPORT_FUNCTION}({_matlab_quote(source)},{_matlab_quote(temporary_dir)});"
            )
        else:
            output_path = temporary_dir / "raw_source.json"
            adapter_arg = source_adapter_id
            command = (
                f"addpath(genpath({_matlab_quote(matlab_root)}));"
                f"{RAW_MAT_EXPORT_FUNCTION}({_matlab_quote(source)},{_matlab_quote(output_path)},"
                f"{_matlab_quote(adapter_arg)});"
            )
        _run_matlab(
            executable,
            command,
            cwd=temporary_dir,
            cancel_event=cancel_event,
            timeout_seconds=timeout_seconds,
        )
        if not output_path.is_file():
            raise MatlabBridgeError(f"MATLAB returned without creating the expected output file: {output_path.name}")
        try:
            document = json.loads(output_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise MatlabBridgeError(f"MATLAB output is not valid UTF-8 JSON: {exc}") from exc

    if not isinstance(document, Mapping):
        raise MatlabBridgeError("MATLAB export root must be an object")
    if document.get("schema") == "pyfnirs.matlab-export/1":
        try:
            from .contracts import validate_export_document

            validate_export_document(document)
        except ContractError as exc:
            raise MatlabBridgeError(f"MATLAB study export violates schema 1: {exc}") from exc
        return document
    if document.get("schema") == RAW_MAT_EXPORT_SCHEMA:
        variables = document.get("variables")
        if not isinstance(variables, Mapping) or not variables:
            raise MatlabBridgeError("Raw MAT export has no top-level variables")
        if not isinstance(document.get("source_file_name"), str):
            raise MatlabBridgeError("Raw MAT export has no source file name")
        if not isinstance(document.get("matlab_version"), str):
            raise MatlabBridgeError("Raw MAT export has no MATLAB version")
        if source_adapter_id is not None and document.get("source_adapter_id") != source_adapter_id:
            raise MatlabBridgeError("Raw MAT export adapter ID does not match the requested adapter")
        return document
    raise MatlabBridgeError(f"Unsupported MATLAB export schema: {document.get('schema')!r}")


__all__ = [
    "MatlabBridgeCancelled",
    "MatlabBridgeError",
    "RAW_RESULTS_ADAPTER_ID",
    "RAW_MAT_EXPORT_SCHEMA",
    "STUDY_MAT_ADAPTER_ID",
    "export_mat_document",
]
