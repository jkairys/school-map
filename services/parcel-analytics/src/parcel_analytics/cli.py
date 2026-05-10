from __future__ import annotations

import argparse

from .config import ProjectConfig, load_config
from .reports import dataset_paths_for_report, render_report
from .source_qld import fetch_localities_geojson, fetch_parcels_geojson, load_geodataframe


def main() -> None:
    parser = argparse.ArgumentParser(description="Queensland parcel analytics utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch-report-data")
    _add_common_arguments(fetch_parser)

    render_parser = subparsers.add_parser("render-report")
    _add_common_arguments(render_parser)

    args = parser.parse_args()
    config = load_config(args.config)
    report = _get_report(config, args.report)

    if args.command == "fetch-report-data":
        dataset_paths = dataset_paths_for_report(config, report)
        fetch_localities_geojson(
            dataset_paths.localities_path,
            localities=report.localities,
            lga=report.lga,
            bounds=report.bounds,
        )
        parcel_localities = report.localities
        if not parcel_localities and report.lga:
            localities = load_geodataframe(dataset_paths.localities_path)
            parcel_localities = sorted(localities["locality"].dropna().astype(str).unique().tolist())
        fetch_parcels_geojson(
            dataset_paths.parcels_path,
            localities=parcel_localities,
            bounds=report.bounds,
        )
        print(dataset_paths.localities_path)
        print(dataset_paths.parcels_path)
        return

    if args.command == "render-report":
        outputs = render_report(config, report, dataset_paths_for_report(config, report))
        print(outputs.histogram_csv)
        print(outputs.hex_geojson)
        return

    raise ValueError(f"Unsupported command: {args.command}")


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", required=True)
    parser.add_argument("--report", required=True)


def _get_report(config: ProjectConfig, report_name: str):
    try:
        return config.reports[report_name]
    except KeyError as exc:
        available = ", ".join(sorted(config.reports))
        raise KeyError(f"Unknown report '{report_name}'. Available: {available}") from exc


if __name__ == "__main__":
    main()
