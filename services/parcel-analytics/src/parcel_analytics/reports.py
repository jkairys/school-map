from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from .analysis import (
    apply_bounds_filter,
    apply_locality_filter,
    build_hex_summary,
    clip_parcels_to_locality_geometries,
    filter_base_lot_parcels,
    normalize_area_sqm,
    summarise_suburb_histograms,
)
from .config import ProjectConfig, ReportDefinition
from .models import QueenslandDatasetPaths, ReportPaths
from .plotting import plot_hex_map, plot_histogram_table
from .source_qld import load_geodataframe


def dataset_paths_for_report(config: ProjectConfig, report: ReportDefinition) -> QueenslandDatasetPaths:
    return QueenslandDatasetPaths(
        localities_path=config.data_dir / "raw" / f"{report.name}_localities.geojson",
        parcels_path=config.data_dir / "raw" / f"{report.name}_parcels.geojson",
    )


def output_paths_for_report(config: ProjectConfig, report: ReportDefinition) -> ReportPaths:
    report_output_dir = config.output_dir / report.name
    report_output_dir.mkdir(parents=True, exist_ok=True)
    return ReportPaths(
        output_dir=report_output_dir,
        histogram_csv=report_output_dir / "histogram_counts.csv",
        histogram_png=report_output_dir / "histogram_counts.png",
        hex_geojson=report_output_dir / "median_block_hexes.geojson",
        hex_png=report_output_dir / "median_block_hexes.png",
    )


def render_report(
    config: ProjectConfig,
    report: ReportDefinition,
    datasets: QueenslandDatasetPaths,
) -> ReportPaths:
    localities = load_geodataframe(datasets.localities_path)
    parcels = load_geodataframe(datasets.parcels_path)

    if report.localities:
        localities = apply_locality_filter(localities, report.localities)
        parcels = apply_locality_filter(parcels, report.localities)
    if report.bounds:
        localities = apply_bounds_filter(localities, report.bounds)
        parcels = apply_bounds_filter(parcels, report.bounds)

    parcels = filter_base_lot_parcels(parcels)
    if not localities.empty:
        parcels = clip_parcels_to_locality_geometries(parcels, localities)
    parcels = normalize_area_sqm(parcels)

    histogram = summarise_suburb_histograms(
        parcels,
        bin_edges=config.bin_edges,
        bin_labels=config.bin_labels,
    )
    hexes = build_hex_summary(parcels, resolution=report.hex_resolution)

    outputs = output_paths_for_report(config, report)
    histogram.to_csv(outputs.histogram_csv)
    hexes.to_file(outputs.hex_geojson, driver="GeoJSON")

    histogram_ax = plot_histogram_table(histogram)
    histogram_ax.figure.savefig(outputs.histogram_png, dpi=200)
    histogram_ax.figure.clf()

    hex_ax = plot_hex_map(hexes, localities=localities)
    hex_ax.figure.savefig(outputs.hex_png, dpi=200)
    hex_ax.figure.clf()

    return outputs
