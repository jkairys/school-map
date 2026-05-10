from __future__ import annotations

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
from shapely.geometry import Polygon

from parcel_analytics.plotting import plot_hex_map, plot_parcel_size_map

matplotlib.use("Agg")


def _frame(column_name: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {column_name: [320.0, 540.0]},
        geometry=[
            Polygon([(0, 0), (0, 1), (1, 1), (1, 0)]),
            Polygon([(1, 0), (1, 1), (2, 1), (2, 0)]),
        ],
        crs="EPSG:4326",
    )


def test_plot_hex_map_accepts_existing_axis() -> None:
    hexes = _frame("median_area_sqm")
    localities = _frame("area_sqm")
    fig, ax = plt.subplots()

    returned = plot_hex_map(hexes, localities=localities, ax=ax)

    assert returned is ax
    assert ax.get_title() == "Median parcel size by hex"
    assert not ax.axison
    plt.close(fig)


def test_plot_parcel_size_map_accepts_existing_axis() -> None:
    parcels = _frame("area_sqm")
    localities = _frame("median_area_sqm")
    fig, ax = plt.subplots()

    returned = plot_parcel_size_map(parcels, localities=localities, ax=ax)

    assert returned is ax
    assert ax.get_title() == "Property size by parcel"
    assert not ax.axison
    plt.close(fig)
