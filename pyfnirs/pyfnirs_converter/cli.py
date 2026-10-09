"""Command-line entry points that call the same public API as the GUI."""
from __future__ import annotations

import argparse
from dataclasses import asdict, fields
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from . import api


def _selection_from_json(path: str | Path) -> api.ConversionSelection:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read selection JSON {source}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Selection JSON root must be an object")
    allowed = {
        "source_adapter_id", "identity", "feature_selections", "targets", "covariates",
        "output_format", "merge_mode", "collision_policy",
    }
    unknown = set(data).difference(allowed)
    missing = allowed.difference(data)
    if unknown or missing:
        raise ValueError(f"Selection JSON keys mismatch; missing={sorted(missing)}, unknown={sorted(unknown)}")
    identity_data = data["identity"]
    if not isinstance(identity_data, dict):
        raise ValueError("Selection identity must be an object")
    identity_fields = {field.name for field in fields(api.IdentityMapping)}
    if set(identity_data).difference(identity_fields):
        raise ValueError(f"Unknown identity fields: {sorted(set(identity_data).difference(identity_fields))}")
    identity = api.IdentityMapping(**identity_data)

    def mappings(name: str, role: str) -> tuple[api.FieldMapping, ...]:
        value = data[name]
        if not isinstance(value, list):
            raise ValueError(f"Selection {name} must be a list")
        result: list[api.FieldMapping] = []
        for index, item in enumerate(value):
            if not isinstance(item, dict) or set(item) != {"source_path", "output_name"}:
                raise ValueError(f"{name}[{index}] must contain source_path and output_name")
            result.append(api.FieldMapping(item["source_path"], item["output_name"], role))
        return tuple(result)

    raw_features = data["feature_selections"]
    if not isinstance(raw_features, list) or not raw_features:
        raise ValueError("Selection feature_selections must be a nonempty list")
    feature_fields = {field.name for field in fields(api.FeatureSelection)}
    features: list[api.FeatureSelection] = []
    for index, item in enumerate(raw_features):
        if not isinstance(item, dict):
            raise ValueError(f"feature_selections[{index}] must be an object")
        if set(item).difference(feature_fields):
            raise ValueError(f"feature_selections[{index}] has unknown fields: {sorted(set(item).difference(feature_fields))}")
        missing_fields = {"capability_id", "feature_id", "source_path", "axis_selection", "summary_parameters"}.difference(item)
        if missing_fields:
            raise ValueError(f"feature_selections[{index}] is missing {sorted(missing_fields)}")
        features.append(api.FeatureSelection(**item))
    return api.ConversionSelection(
        source_adapter_id=data["source_adapter_id"],
        identity=identity,
        feature_selections=tuple(features),
        targets=mappings("targets", "target"),
        covariates=mappings("covariates", "covariate"),
        output_format=data["output_format"],
        merge_mode=data["merge_mode"],
        collision_policy=data["collision_policy"],
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyfnirs-converter", description="PYfNIRs → PY-ML explicit conversion API")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect one .mat or validated .json source")
    inspect_parser.add_argument("input", type=Path)
    inspect_parser.add_argument("--adapter-id")
    inspect_parser.add_argument("--matlab", type=Path)

    preview_parser = subparsers.add_parser("preview", help="Preview an explicit selection without writing files")
    preview_parser.add_argument("input", type=Path)
    preview_parser.add_argument("--selection", required=True, type=Path)
    preview_parser.add_argument("--matlab", type=Path)

    convert_parser = subparsers.add_parser("convert", help="Convert files or directories using an explicit selection")
    convert_parser.add_argument("inputs", nargs="+", type=Path)
    convert_parser.add_argument("--selection", required=True, type=Path)
    convert_parser.add_argument("--output-dir", required=True, type=Path)
    convert_parser.add_argument("--recursive", action="store_true")
    convert_parser.add_argument("--matlab", type=Path)
    convert_parser.add_argument("--quiet-progress", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inspect":
            result = api.inspect_source(
                args.input,
                source_adapter_id=args.adapter_id,
                matlab_executable=args.matlab,
            )
            print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2, allow_nan=False))
            return 0
        selection = _selection_from_json(args.selection)
        if args.command == "preview":
            result = api.preview_conversion(args.input, selection, matlab_executable=args.matlab)
            print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2, allow_nan=False))
            return 0

        def report_progress(event: api.ProgressEvent) -> None:
            if not args.quiet_progress:
                print(
                    f"{event.index}/{event.total} {event.percent:.0f}% {event.phase}: {event.source_path} — {event.message}",
                    file=sys.stderr,
                )

        result = api.convert_batch(
            api.BatchRequest(
                input_paths=tuple(args.inputs),
                output_dir=args.output_dir,
                selection=selection,
                matlab_executable=args.matlab,
                recursive=args.recursive,
            ),
            progress_callback=report_progress,
        )
        print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2, allow_nan=False))
        failed = any(item.status in {"failed", "cancelled", "not_processed"} for item in result.files)
        return 1 if failed or result.cancelled else 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
