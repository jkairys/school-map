from __future__ import annotations

import json

import httpx

from parcel_analytics.config import Bounds
from parcel_analytics.source_qld import (
    build_locality_where,
    build_parcel_where,
    bounds_to_query_params,
    fetch_parcels_geojson,
    fetch_all_features,
    fetch_feature_count,
    fetch_object_ids,
)


def test_build_locality_where_escapes_quotes() -> None:
    where = build_locality_where(["O'Brien", "Little Mountain"])

    assert where == "locality = 'O''Brien' OR locality = 'Little Mountain'"


def test_build_locality_where_supports_lga_filter() -> None:
    where = build_locality_where(
        ["Little Mountain", "Baringa"],
        lga="Sunshine Coast Regional",
    )

    assert where == (
        "lga = 'Sunshine Coast Regional' AND "
        "(locality = 'Little Mountain' OR locality = 'Baringa')"
    )


def test_build_parcel_where_adds_lot_type_filter() -> None:
    where = build_parcel_where(localities=["Little Mountain"])

    assert where == "parcel_typ = 'Lot Type Parcel' AND locality IN ('Little Mountain')"


def test_bounds_to_query_params_returns_arcgis_envelope_params() -> None:
    params = bounds_to_query_params(Bounds(153.0, -27.6, 153.1, -27.5))

    assert params == {
        "geometry": "153.0,-27.6,153.1,-27.5",
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": "4326",
    }


def test_fetch_all_features_paginates_until_transfer_limit_clears() -> None:
    responses = [
        {
            "type": "FeatureCollection",
            "features": [{"id": 1}, {"id": 2}],
            "exceededTransferLimit": True,
        },
        {
            "type": "FeatureCollection",
            "features": [{"id": 3}],
            "exceededTransferLimit": False,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("resultOffset", "0"))
        payload = responses[0] if offset == 0 else responses[1]
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    features = list(
        fetch_all_features(
            "https://example.test/query",
            {"f": "geojson"},
            client=client,
            page_size=2,
        )
    )

    assert features == [{"id": 1}, {"id": 2}, {"id": 3}]


def test_fetch_feature_count_reads_count_payload() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"count": 9232})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    count = fetch_feature_count("https://example.test/query", {"where": "1=1"}, client=client)

    assert count == 9232
    assert calls[0].url.params["returnCountOnly"] == "true"


def test_fetch_object_ids_reads_object_ids_payload() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"objectIds": [11, 12, 13]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    object_ids = fetch_object_ids("https://example.test/query", {"where": "1=1"}, client=client)

    assert object_ids == [11, 12, 13]
    assert calls[0].url.params["returnIdsOnly"] == "true"


def test_fetch_parcels_geojson_batches_large_locality_lists(tmp_path, monkeypatch) -> None:
    seen_wheres: list[str] = []
    seen_object_id_batches: list[list[int]] = []

    def fake_fetch_object_ids(url: str, params: dict[str, str], *, client=None) -> list[int]:
        seen_wheres.append(params["where"])
        return [1, 2]

    def fake_fetch_features_by_object_ids(
        url: str,
        params: dict[str, str],
        object_ids: list[int],
        *,
        client=None,
        batch_size: int,
    ):
        seen_object_id_batches.append(object_ids)
        yield {"type": "Feature", "properties": {"where": params["where"]}, "geometry": None}

    monkeypatch.setattr("parcel_analytics.source_qld.fetch_object_ids", fake_fetch_object_ids)
    monkeypatch.setattr(
        "parcel_analytics.source_qld.fetch_features_by_object_ids",
        fake_fetch_features_by_object_ids,
    )

    output_path = tmp_path / "parcels.geojson"
    fetch_parcels_geojson(
        output_path,
        localities=["Alpha", "Beta", "Gamma"],
        locality_batch_size=2,
    )

    payload = json.loads(output_path.read_text())

    assert seen_wheres == [
        "parcel_typ = 'Lot Type Parcel' AND locality IN ('Alpha', 'Beta')",
        "parcel_typ = 'Lot Type Parcel' AND locality IN ('Gamma')",
    ]
    assert seen_object_id_batches == [[1, 2], [1, 2]]
    assert len(payload["features"]) == 2
