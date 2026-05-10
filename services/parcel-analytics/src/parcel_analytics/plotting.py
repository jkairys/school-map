from __future__ import annotations

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd


def plot_histogram_table(
    histogram_counts: pd.DataFrame,
    *,
    figsize: tuple[int, int] = (12, 6),
) -> plt.Axes:
    ax = histogram_counts.plot(kind="bar", figsize=figsize)
    ax.set_xlabel("Locality")
    ax.set_ylabel("Parcel count")
    ax.set_title("Parcel-size distribution by locality")
    ax.legend(title="Block size (m²)")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    return ax


def plot_single_locality_histogram(
    histogram_counts: pd.Series,
    *,
    locality_name: str,
    color: str = "#4C6A92",
    figsize: tuple[int, int] = (10, 5),
    bar_width: float = 0.72,
) -> plt.Axes:
    values = histogram_counts.astype(int)
    positions = range(len(values))

    fig, ax = plt.subplots(figsize=figsize)
    ax.bar(positions, values.values, color=color, width=bar_width)
    ax.set_xticks(list(positions), list(values.index))
    ax.set_xlabel("Block size (m²)")
    ax.set_ylabel("Parcel count")
    ax.set_title(f"Parcel-size distribution in {locality_name}")
    ax.grid(axis="y", alpha=0.2)
    plt.tight_layout()
    return ax


def plot_hex_map(
    hexes: gpd.GeoDataFrame,
    localities: gpd.GeoDataFrame | None = None,
    *,
    figsize: tuple[int, int] = (10, 10),
    column: str = "median_area_sqm",
    cmap: str = "YlGnBu",
    ax: plt.Axes | None = None,
) -> plt.Axes:
    created_figure = ax is None
    if ax is None:
        _, ax = plt.subplots(figsize=figsize)

    hexes.plot(
        column=column,
        cmap=cmap,
        legend=True,
        linewidth=0.1,
        edgecolor="#666666",
        ax=ax,
    )
    ax.set_title("Median parcel size by hex")
    ax.set_axis_off()

    if localities is not None and not localities.empty:
        localities.to_crs(hexes.crs).boundary.plot(ax=ax, color="black", linewidth=0.6)

    if created_figure:
        ax.figure.tight_layout()
    return ax


def plot_parcel_size_map(
    parcels: gpd.GeoDataFrame,
    localities: gpd.GeoDataFrame | None = None,
    *,
    figsize: tuple[int, int] = (10, 10),
    column: str = "area_sqm",
    cmap: str = "RdYlGn",
    ax: plt.Axes | None = None,
) -> plt.Axes:
    created_figure = ax is None
    if ax is None:
        _, ax = plt.subplots(figsize=figsize)

    if not parcels.empty:
        parcels.plot(
            column=column,
            cmap=cmap,
            legend=True,
            linewidth=0,
            ax=ax,
        )

    ax.set_title("Property size by parcel")
    ax.set_axis_off()

    if localities is not None and not localities.empty:
        localities.to_crs(parcels.crs).boundary.plot(ax=ax, color="black", linewidth=0.6)

    if created_figure:
        ax.figure.tight_layout()
    return ax
