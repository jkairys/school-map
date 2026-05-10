from __future__ import annotations

from collections.abc import Sequence

import geopandas as gpd
import pandas as pd
from h3.api.basic_str import cell_to_boundary, latlng_to_cell
from shapely.geometry import Point, Polygon, box

from .config import Bounds, DEFAULT_BIN_EDGES, DEFAULT_BIN_LABELS

AREA_CRS = "EPSG:3577"
WGS84_CRS = "EPSG:4326"


def filter_base_lot_parcels(
    parcels: gpd.GeoDataFrame,
    *,
    cover_column: str = "cover_typ",
    parcel_type_column: str = "parcel_typ",
) -> gpd.GeoDataFrame:
    if cover_column not in parcels.columns or parcel_type_column not in parcels.columns:
        return parcels.copy()

    mask = (parcels[cover_column] == "Base") & (
        parcels[parcel_type_column] == "Lot Type Parcel"
    )
    return parcels.loc[mask].copy()


def apply_bounds_filter(
    frame: gpd.GeoDataFrame,
    bounds: Bounds | None,
) -> gpd.GeoDataFrame:
    if bounds is None:
        return frame.copy()

    bounds_geom = box(bounds.min_lon, bounds.min_lat, bounds.max_lon, bounds.max_lat)
    if frame.crs is None:
        raise ValueError("GeoDataFrame must have a CRS before applying bounds")

    target = frame.to_crs(WGS84_CRS)
    return target.loc[target.intersects(bounds_geom)].copy()


def apply_locality_filter(
    frame: gpd.GeoDataFrame,
    localities: Sequence[str],
    *,
    locality_column: str = "locality",
) -> gpd.GeoDataFrame:
    if not localities:
        return frame.copy()

    wanted = {value.casefold() for value in localities}
    mask = frame[locality_column].fillna("").map(str.casefold).isin(wanted)
    return frame.loc[mask].copy()


def normalize_area_sqm(
    parcels: gpd.GeoDataFrame,
    *,
    area_column: str = "lot_area",
    output_column: str = "area_sqm",
) -> gpd.GeoDataFrame:
    normalized = parcels.copy()

    if normalized.crs is None:
        raise ValueError("GeoDataFrame must have a CRS before computing area")

    computed = normalized.to_crs(AREA_CRS).geometry.area
    if area_column in normalized.columns:
        source_values = pd.to_numeric(normalized[area_column], errors="coerce")
        normalized[output_column] = source_values.where(source_values.gt(0), computed)
    else:
        normalized[output_column] = computed

    return normalized


def assign_size_bins(
    area_sqm: pd.Series,
    *,
    bin_edges: Sequence[float] = DEFAULT_BIN_EDGES,
    bin_labels: Sequence[str] = DEFAULT_BIN_LABELS,
) -> pd.Series:
    return pd.cut(
        area_sqm,
        bins=list(bin_edges),
        labels=list(bin_labels),
        right=False,
        include_lowest=True,
        ordered=True,
    )


def summarise_suburb_histograms(
    parcels: gpd.GeoDataFrame,
    *,
    locality_column: str = "locality",
    area_column: str = "area_sqm",
    bin_edges: Sequence[float] = DEFAULT_BIN_EDGES,
    bin_labels: Sequence[str] = DEFAULT_BIN_LABELS,
) -> pd.DataFrame:
    if locality_column not in parcels.columns:
        raise KeyError(f"Missing locality column: {locality_column}")
    if area_column not in parcels.columns:
        raise KeyError(f"Missing area column: {area_column}")

    working = parcels[[locality_column, area_column]].copy()
    working["size_bin"] = assign_size_bins(
        working[area_column],
        bin_edges=bin_edges,
        bin_labels=bin_labels,
    )
    summary = (
        working.groupby([locality_column, "size_bin"], observed=False)
        .size()
        .rename("parcel_count")
        .reset_index()
    )

    pivot = (
        summary.pivot(index=locality_column, columns="size_bin", values="parcel_count")
        .fillna(0)
        .astype(int)
    )
    return pivot.reindex(columns=list(bin_labels), fill_value=0).sort_index()


def clip_parcels_to_locality_geometries(
    parcels: gpd.GeoDataFrame,
    localities: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    if parcels.crs is None or localities.crs is None:
        raise ValueError("Both GeoDataFrames must have a CRS")

    aligned_localities = localities.to_crs(parcels.crs)
    locality_union = aligned_localities.union_all()
    clipped = parcels.loc[parcels.intersects(locality_union)].copy()
    return clipped


def build_hex_summary(
    parcels: gpd.GeoDataFrame,
    *,
    resolution: int = 8,
    area_column: str = "area_sqm",
) -> gpd.GeoDataFrame:
    if parcels.crs is None:
        raise ValueError("GeoDataFrame must have a CRS")
    if area_column not in parcels.columns:
        raise KeyError(f"Missing area column: {area_column}")

    projected = parcels.to_crs(AREA_CRS)
    centroids = gpd.GeoSeries(projected.geometry.centroid, crs=AREA_CRS).to_crs(WGS84_CRS)
    as_wgs84 = parcels.to_crs(WGS84_CRS).copy()
    as_wgs84["hex_id"] = [
        latlng_to_cell(point.y, point.x, resolution) if isinstance(point, Point) else None
        for point in centroids
    ]

    aggregated = (
        as_wgs84.groupby("hex_id", dropna=True)
        .agg(
            parcel_count=(area_column, "size"),
            median_area_sqm=(area_column, "median"),
        )
        .reset_index()
    )
    aggregated["geometry"] = aggregated["hex_id"].map(_hex_polygon)
    return gpd.GeoDataFrame(aggregated, geometry="geometry", crs=WGS84_CRS)


def _hex_polygon(cell_id: str) -> Polygon:
    boundary = cell_to_boundary(cell_id)
    return Polygon((lng, lat) for lat, lng in boundary)
