from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path

import geopandas as gpd
import httpx

from .config import Bounds

LOCALITY_QUERY_URL = (
    "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
    "Boundaries/AdministrativeBoundaries/MapServer/2/query"
)
PARCEL_QUERY_URL = (
    "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
    "PlanningCadastre/LandParcelPropertyFramework/MapServer/8/query"
)
DEFAULT_PAGE_SIZE = 1000
LOCALITY_OUT_FIELDS = "objectid,locality,lga,ca_area_sqkm"
PARCEL_OUT_FIELDS = "objectid,lotplan,lot_area,cover_typ,parcel_typ,locality"
PARCEL_LOCALITY_BATCH_SIZE = 10
PARCEL_OBJECT_ID_BATCH_SIZE = 100


def build_locality_where(
    localities: Sequence[str] | None = None,
    *,
    lga: str | None = None,
) -> str:
    clauses: list[str] = []
    if lga:
        clauses.append(f"lga = '{_escape_sql(lga)}'")
    if localities:
        locality_clause = " OR ".join(
            f"locality = '{_escape_sql(value)}'" for value in localities
        )
        clauses.append(f"({locality_clause})" if lga and len(localities) > 1 else locality_clause)
    return " AND ".join(clauses) if clauses else "1=1"


def build_parcel_where(
    *,
    localities: Sequence[str] | None = None,
    lot_type_only: bool = True,
    extra_clauses: Sequence[str] | None = None,
) -> str:
    clauses: list[str] = []
    if lot_type_only:
        clauses.append("parcel_typ = 'Lot Type Parcel'")
    if localities:
        localities_sql = ", ".join(f"'{_escape_sql(value)}'" for value in localities)
        clauses.append(f"locality IN ({localities_sql})")
    if extra_clauses:
        clauses.extend(extra_clauses)
    return " AND ".join(clauses) if clauses else "1=1"


def fetch_localities_geojson(
    output_path: str | Path,
    *,
    localities: Sequence[str] | None = None,
    lga: str | None = None,
    bounds: Bounds | None = None,
    client: httpx.Client | None = None,
) -> Path:
    params = {
        "where": build_locality_where(localities, lga=lga),
        "outFields": LOCALITY_OUT_FIELDS,
        "returnGeometry": "true",
        "f": "geojson",
        "outSR": "4326",
    }
    if bounds is not None:
        params.update(bounds_to_query_params(bounds))
    return _download_geojson(
        LOCALITY_QUERY_URL,
        output_path,
        params,
        client=client,
        page_size=2000,
    )


def fetch_parcels_geojson(
    output_path: str | Path,
    *,
    localities: Sequence[str] | None = None,
    bounds: Bounds | None = None,
    client: httpx.Client | None = None,
    locality_batch_size: int = PARCEL_LOCALITY_BATCH_SIZE,
    object_id_batch_size: int = PARCEL_OBJECT_ID_BATCH_SIZE,
) -> Path:
    destination = Path(output_path)
    if localities:
        cache_dir = _parcel_locality_cache_dir(destination)
        cache_dir.mkdir(parents=True, exist_ok=True)
        all_features: list[dict] = []
        total_localities = len(localities)
        for index, locality in enumerate(localities, start=1):
            part_path = _parcel_locality_part_path(cache_dir, index, locality)
            if part_path.exists():
                print(f"[{index}/{total_localities}] Skipping cached locality: {locality}")
            else:
                print(f"[{index}/{total_localities}] Downloading locality: {locality}")
                params = {
                    "where": build_parcel_where(localities=[locality]),
                    "outFields": PARCEL_OUT_FIELDS,
                    "returnGeometry": "true",
                    "f": "geojson",
                    "outSR": "4326",
                }
                if bounds is not None:
                    params.update(bounds_to_query_params(bounds))
                object_ids = fetch_object_ids(PARCEL_QUERY_URL, params, client=client)
                print(f"  found {len(object_ids)} parcel ids")
                locality_features = list(
                    fetch_features_by_object_ids(
                        PARCEL_QUERY_URL,
                        params,
                        object_ids,
                        client=client,
                        batch_size=object_id_batch_size,
                        progress_label=locality,
                    )
                )
                _write_feature_collection(part_path, locality_features)
                print(f"  wrote {len(locality_features)} features to {part_path.name}")
            all_features.extend(_read_feature_collection(part_path))
        _write_feature_collection(destination, all_features)
        print(f"Wrote merged parcel extract: {destination}")
        return destination

    features: list[dict] = []
    locality_batches = [None]
    if localities:
        locality_batches = list(_chunked(localities, locality_batch_size))

    for locality_batch in locality_batches:
        params = {
            "where": build_parcel_where(localities=locality_batch),
            "outFields": PARCEL_OUT_FIELDS,
            "returnGeometry": "true",
            "f": "geojson",
            "outSR": "4326",
        }
        if bounds is not None:
            params.update(bounds_to_query_params(bounds))
        if locality_batch is not None:
            object_ids = fetch_object_ids(PARCEL_QUERY_URL, params, client=client)
            features.extend(
                fetch_features_by_object_ids(
                    PARCEL_QUERY_URL,
                    params,
                    object_ids,
                    client=client,
                    batch_size=object_id_batch_size,
                )
            )
            continue
        feature_count = fetch_feature_count(PARCEL_QUERY_URL, params, client=client)
        features.extend(
            fetch_all_features(
                PARCEL_QUERY_URL,
                params,
                client=client,
                page_size=DEFAULT_PAGE_SIZE,
                total_count=feature_count,
            )
        )
    return _write_feature_collection(output_path, features)


def bounds_to_query_params(bounds: Bounds) -> dict[str, str]:
    geometry = ",".join(
        [
            str(bounds.min_lon),
            str(bounds.min_lat),
            str(bounds.max_lon),
            str(bounds.max_lat),
        ]
    )
    return {
        "geometry": geometry,
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": "4326",
    }


def load_geodataframe(path: str | Path) -> gpd.GeoDataFrame:
    return gpd.read_file(path)


def _download_geojson(
    url: str,
    output_path: str | Path,
    params: dict[str, str],
    *,
    client: httpx.Client | None = None,
    page_size: int,
) -> Path:
    features = list(fetch_all_features(url, params, client=client, page_size=page_size))
    collection = {"type": "FeatureCollection", "features": features}
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(collection))
    return destination


def _write_feature_collection(output_path: str | Path, features: Sequence[dict]) -> Path:
    collection = {"type": "FeatureCollection", "features": list(features)}
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(collection))
    return destination


def _read_feature_collection(path: str | Path) -> list[dict]:
    payload = json.loads(Path(path).read_text())
    return list(payload.get("features") or [])


def fetch_all_features(
    url: str,
    params: dict[str, str],
    *,
    client: httpx.Client | None = None,
    page_size: int,
    total_count: int | None = None,
) -> Iterable[dict]:
    owns_client = client is None
    active_client = client or httpx.Client(timeout=60.0)
    try:
        offset = 0
        while True:
            page_params = dict(params)
            page_params["resultOffset"] = str(offset)
            current_page_size = page_size
            if total_count is not None:
                remaining = total_count - offset
                if remaining <= 0:
                    break
                current_page_size = min(page_size, remaining)
            page_params["resultRecordCount"] = str(current_page_size)
            response = active_client.get(url, params=page_params)
            response.raise_for_status()
            payload = response.json()

            features = payload.get("features", [])
            for feature in features:
                yield feature

            if total_count is not None:
                offset += len(features)
                if offset >= total_count:
                    break
                continue

            if not payload.get("exceededTransferLimit"):
                break
            offset += page_size
    finally:
        if owns_client:
            active_client.close()


def fetch_feature_count(
    url: str,
    params: dict[str, str],
    *,
    client: httpx.Client | None = None,
) -> int:
    owns_client = client is None
    active_client = client or httpx.Client(timeout=60.0)
    try:
        response = active_client.get(
            url,
            params={
                **params,
                "returnCountOnly": "true",
                "f": "json",
            },
        )
        response.raise_for_status()
        payload = response.json()
        return int(payload.get("count", 0))
    finally:
        if owns_client:
            active_client.close()


def fetch_object_ids(
    url: str,
    params: dict[str, str],
    *,
    client: httpx.Client | None = None,
) -> list[int]:
    owns_client = client is None
    active_client = client or httpx.Client(timeout=60.0)
    try:
        response = active_client.get(
            url,
            params={
                **params,
                "returnIdsOnly": "true",
                "returnGeometry": "false",
                "f": "json",
            },
        )
        response.raise_for_status()
        payload = response.json()
        return [int(value) for value in payload.get("objectIds") or []]
    finally:
        if owns_client:
            active_client.close()


def fetch_features_by_object_ids(
    url: str,
    params: dict[str, str],
    object_ids: Sequence[int],
    *,
    client: httpx.Client | None = None,
    batch_size: int,
    progress_label: str | None = None,
) -> Iterable[dict]:
    owns_client = client is None
    active_client = client or httpx.Client(timeout=60.0)
    try:
        object_id_batches = list(_chunked(list(object_ids), batch_size))
        for batch_index, object_id_batch in enumerate(object_id_batches, start=1):
            if progress_label is not None:
                print(
                    f"  {progress_label}: object id batch "
                    f"{batch_index}/{len(object_id_batches)} ({len(object_id_batch)} ids)"
                )
            yield from _fetch_feature_object_id_batch(
                url,
                params,
                list(object_id_batch),
                client=active_client,
            )
    finally:
        if owns_client:
            active_client.close()


def _escape_sql(value: str) -> str:
    return value.replace("'", "''")


def _chunked(values: Sequence[str] | Sequence[int], chunk_size: int) -> Iterable[list[str] | list[int]]:
    for offset in range(0, len(values), chunk_size):
        yield list(values[offset : offset + chunk_size])


def _fetch_feature_object_id_batch(
    url: str,
    params: dict[str, str],
    object_id_batch: list[int],
    *,
    client: httpx.Client,
) -> Iterable[dict]:
    response = client.post(
        url,
        data={
            **params,
            "objectIds": ",".join(str(value) for value in object_id_batch),
        },
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        if len(object_id_batch) == 1 or response.status_code < 500:
            raise
        midpoint = len(object_id_batch) // 2
        yield from _fetch_feature_object_id_batch(
            url,
            params,
            object_id_batch[:midpoint],
            client=client,
        )
        yield from _fetch_feature_object_id_batch(
            url,
            params,
            object_id_batch[midpoint:],
            client=client,
        )
        return

    payload = response.json()
    for feature in payload.get("features", []):
        yield feature


def _parcel_locality_cache_dir(output_path: Path) -> Path:
    return output_path.parent / f"{output_path.stem}_parts"


def _parcel_locality_part_path(cache_dir: Path, index: int, locality: str) -> Path:
    return cache_dir / f"{index:03d}_{_slugify_filename(locality)}.geojson"


def _slugify_filename(value: str) -> str:
    sanitized = "".join(char.lower() if char.isalnum() else "_" for char in value)
    compact = "_".join(part for part in sanitized.split("_") if part)
    return compact or "locality"
