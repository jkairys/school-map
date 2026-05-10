"""Shared models for parcel analytics data sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ArcGISLayer:
    """Describes a single ArcGIS REST feature layer."""

    name: str
    service_url: str
    layer_id: int
    object_id_field: str = "objectid"
    max_record_count: int = 10_000
    default_order_by: tuple[str, ...] = ("objectid",)

    @property
    def query_url(self) -> str:
        """Return the ArcGIS REST query endpoint for the layer."""

        return f"{self.service_url.rstrip('/')}/{self.layer_id}/query"


@dataclass(frozen=True, slots=True)
class ArcGISQuery:
    """Represents a paginated ArcGIS feature query."""

    where: str = "1=1"
    out_fields: tuple[str, ...] = ("*",)
    page_size: int = 10_000
    return_geometry: bool = True
    output_format: str = "geojson"
    order_by_fields: tuple[str, ...] = ("objectid",)
    extra_params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ArcGISFeaturePage:
    """One page of ArcGIS query results."""

    features: tuple[Mapping[str, Any], ...]
    exceeded_transfer_limit: bool = False


@dataclass(slots=True)
class QueenslandDatasetPaths:
    localities_path: Path
    parcels_path: Path


@dataclass(slots=True)
class ReportPaths:
    output_dir: Path
    histogram_csv: Path
    histogram_png: Path
    hex_geojson: Path
    hex_png: Path
