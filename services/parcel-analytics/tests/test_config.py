from __future__ import annotations

from pathlib import Path

from parcel_analytics.config import load_config


def test_load_config_reads_report_lga(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "reports.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "\n".join(
            [
                "data_dir: data",
                "output_dir: output",
                "reports:",
                "  sunshine_coast_region:",
                "    lga: Sunshine Coast Regional",
                "    hex_resolution: 9",
            ]
        )
    )

    config = load_config(config_path)

    assert config.reports["sunshine_coast_region"].lga == "Sunshine Coast Regional"
    assert config.reports["sunshine_coast_region"].hex_resolution == 9
