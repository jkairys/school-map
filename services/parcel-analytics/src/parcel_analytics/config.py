from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_BIN_EDGES = [0, 300, 400, 500, 600, 700, 800, float("inf")]
DEFAULT_BIN_LABELS = [
    "<300",
    "300-400",
    "400-500",
    "500-600",
    "600-700",
    "700-800",
    "800+",
]


@dataclass(slots=True)
class Bounds:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    @classmethod
    def from_sequence(cls, values: list[float]) -> "Bounds":
        if len(values) != 4:
            raise ValueError("Bounds must contain exactly four values")
        return cls(*map(float, values))


@dataclass(slots=True)
class ReportDefinition:
    name: str
    localities: list[str] = field(default_factory=list)
    lga: str | None = None
    bounds: Bounds | None = None
    hex_resolution: int = 8


@dataclass(slots=True)
class ProjectConfig:
    data_dir: Path
    output_dir: Path
    reports: dict[str, ReportDefinition]
    default_hex_resolution: int = 8
    bin_edges: list[float] = field(default_factory=lambda: list(DEFAULT_BIN_EDGES))
    bin_labels: list[str] = field(default_factory=lambda: list(DEFAULT_BIN_LABELS))


def load_config(config_path: str | Path) -> ProjectConfig:
    path = Path(config_path).resolve()
    raw = yaml.safe_load(path.read_text()) or {}
    project_root = path.parent.parent

    reports: dict[str, ReportDefinition] = {}
    default_hex_resolution = int(raw.get("default_hex_resolution", 8))
    for report_name, report_values in (raw.get("reports") or {}).items():
        report_values = report_values or {}
        bounds_values = report_values.get("bounds")
        reports[report_name] = ReportDefinition(
            name=report_name,
            localities=list(report_values.get("localities") or []),
            lga=report_values.get("lga"),
            bounds=Bounds.from_sequence(bounds_values) if bounds_values else None,
            hex_resolution=int(report_values.get("hex_resolution", default_hex_resolution)),
        )

    return ProjectConfig(
        data_dir=(project_root / Path(raw.get("data_dir", "data"))).resolve(),
        output_dir=(project_root / Path(raw.get("output_dir", "output"))).resolve(),
        reports=reports,
        default_hex_resolution=default_hex_resolution,
        bin_edges=list(raw.get("bin_edges", DEFAULT_BIN_EDGES)),
        bin_labels=list(raw.get("bin_labels", DEFAULT_BIN_LABELS)),
    )
