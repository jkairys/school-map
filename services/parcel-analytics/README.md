# parcel-analytics

Minimal `uv`-managed notebook workspace for parcel geospatial analysis.

## What is included

- A Python package scaffold under `src/parcel_analytics`
- A starter notebook in `notebooks/`
- Jupyter Lab and kernel support
- Core geospatial dependencies for tabular, vector, and map-based exploration

## Requirements

- Python 3.11+
- `uv`

## Usage

From `services/parcel-analytics`:

```bash
task install
task start
```

Optional:

```bash
task smoke
task test
task fetch-report-data REPORT=sunshine_coast_demo
task render-report REPORT=sunshine_coast_demo
task kernel
```

## Workflow

1. Edit `config/reports.example.yaml` to define the suburb list, LGA, or bounds you care about.
2. Run `task fetch-report-data REPORT=<report-name>` to download official Queensland locality and parcel data into `data/raw/`.
3. Run `task render-report REPORT=<report-name>` to generate histogram and hex-map outputs in `output/<report-name>/`.
4. Run `task start` and open `notebooks/01_qld_parcel_report.ipynb` for interactive exploration.

For example, `sunshine_coast_region` fetches every locality in the `Sunshine Coast Regional` LGA.

The workspace also includes `notebooks/00_workspace_smoke_test.ipynb`, which is self-contained and does not require external data.
