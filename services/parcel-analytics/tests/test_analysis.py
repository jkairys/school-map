from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Polygon

from parcel_analytics.analysis import (
    assign_size_bins,
    build_hex_summary,
    filter_base_lot_parcels,
    normalize_area_sqm,
    summarise_suburb_histograms,
)


def _parcel_frame() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "locality": ["Alpha", "Alpha", "Beta", "Beta"],
            "lot_area": [250.0, 520.0, 610.0, 0.0],
            "cover_typ": ["Base", "Base", "Base", "Base"],
            "parcel_typ": [
                "Lot Type Parcel",
                "Lot Type Parcel",
                "Lot Type Parcel",
                "Road Type Parcel",
            ],
        },
        geometry=[
            Polygon([(0, 0), (0, 0.0001), (0.0001, 0.0001), (0.0001, 0)]),
            Polygon([(1, 1), (1, 1.0001), (1.0001, 1.0001), (1.0001, 1)]),
            Polygon([(2, 2), (2, 2.0001), (2.0001, 2.0001), (2.0001, 2)]),
            Polygon([(3, 3), (3, 3.0001), (3.0001, 3.0001), (3.0001, 3)]),
        ],
        crs="EPSG:4326",
    )


def test_filter_base_lot_parcels_excludes_non_lot_rows() -> None:
    filtered = filter_base_lot_parcels(_parcel_frame())

    assert list(filtered["parcel_typ"]) == [
        "Lot Type Parcel",
        "Lot Type Parcel",
        "Lot Type Parcel",
    ]


def test_assign_size_bins_uses_expected_labels() -> None:
    bins = assign_size_bins(
        gpd.pd.Series([250, 350, 450, 550, 650, 750, 850]),
    )

    assert list(map(str, bins.astype(str))) == [
        "<300",
        "300-400",
        "400-500",
        "500-600",
        "600-700",
        "700-800",
        "800+",
    ]


def test_normalize_area_sqm_uses_geometry_when_source_area_missing() -> None:
    parcels = _parcel_frame()
    parcels.loc[0, "lot_area"] = 0.0

    normalized = normalize_area_sqm(parcels)

    assert normalized.loc[0, "area_sqm"] > 0
    assert normalized.loc[1, "area_sqm"] == 520.0


def test_summarise_suburb_histograms_returns_fixed_bin_counts() -> None:
    parcels = normalize_area_sqm(filter_base_lot_parcels(_parcel_frame()))

    summary = summarise_suburb_histograms(parcels)

    assert summary.loc["Alpha", "<300"] == 1
    assert summary.loc["Alpha", "500-600"] == 1
    assert summary.loc["Beta", "600-700"] == 1
    assert summary.loc["Beta", "800+"] == 0


def test_build_hex_summary_groups_parcels_into_hexes() -> None:
    parcels = normalize_area_sqm(filter_base_lot_parcels(_parcel_frame()))

    hexes = build_hex_summary(parcels, resolution=5)

    assert not hexes.empty
    assert {"hex_id", "parcel_count", "median_area_sqm"}.issubset(hexes.columns)
    assert int(hexes["parcel_count"].sum()) == len(parcels)
