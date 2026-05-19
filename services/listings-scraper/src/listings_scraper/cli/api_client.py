"""Thin httpx wrapper over the REST API used by every CLI command.

The CLI never opens a DB session — it shells out to a running api. The base
URL comes from ``OTH_SCRAPER_BASE_URL`` (default ``http://127.0.0.1:8000``).
Errors are surfaced as ``ApiError`` carrying the HTTP status and decoded
detail so command impls can map them to typer exits.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import httpx
import typer

from listings_scraper.config import settings


class ApiError(Exception):
    """Non-2xx response from the api. ``detail`` is the parsed JSON body."""

    def __init__(self, status_code: int, detail: Any, *, method: str, url: str):
        self.status_code = status_code
        self.detail = detail
        self.method = method
        self.url = url
        super().__init__(f"{method} {url} -> {status_code}: {detail!r}")


class CliApiClient:
    """Per-command async HTTP client.

    Methods named after the resource they operate on. Network errors are
    re-raised as typer.Exit(2) with a friendly stderr message; HTTP error
    responses become ApiError so callers can branch on status code.
    """

    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            r = await self._client.request(method, path, json=json, params=params)
        except httpx.HTTPError as e:
            base = str(self._client.base_url).rstrip("/")
            typer.echo(
                f"Could not reach api at {base}{path}: {e}\n"
                "Is the service running? Set OTH_SCRAPER_BASE_URL if it's not on 127.0.0.1:8000.",
                err=True,
            )
            raise typer.Exit(code=2) from e
        if r.status_code >= 400:
            try:
                detail = r.json()
            except ValueError:
                detail = r.text
            raise ApiError(r.status_code, detail, method=method, url=path)
        return r

    # --------- suburbs ---------

    async def resolve_suburb(
        self, name: str, *, postcode: str | None, state: str | None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Returns a ResolvedSuburb dict on success, or the candidate list on
        409 (raised as ApiError so caller can switch on status)."""
        body: dict[str, Any] = {"name": name}
        if postcode is not None:
            body["postcode"] = postcode
        if state is not None:
            body["state"] = state
        r = await self._request("POST", "/suburbs/resolve", json=body)
        return r.json()

    # --------- scrape lists ---------

    async def list_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        r = await self._request("POST", "/scrape-lists", json=payload)
        return r.json()

    async def list_ls(self) -> list[dict[str, Any]]:
        r = await self._request("GET", "/scrape-lists")
        return r.json()

    async def list_get(self, list_id: int) -> dict[str, Any]:
        r = await self._request("GET", f"/scrape-lists/{list_id}")
        return r.json()

    async def list_update(
        self, list_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        r = await self._request("PUT", f"/scrape-lists/{list_id}", json=payload)
        return r.json()

    async def list_delete(self, list_id: int) -> None:
        await self._request("DELETE", f"/scrape-lists/{list_id}")

    async def list_add_suburb(
        self, list_id: int, body: dict[str, Any]
    ) -> dict[str, Any]:
        r = await self._request(
            "POST", f"/scrape-lists/{list_id}/suburbs", json=body
        )
        return r.json()

    async def list_remove_suburb(self, list_id: int, suburb_id: int) -> None:
        await self._request(
            "DELETE", f"/scrape-lists/{list_id}/suburbs/{suburb_id}"
        )

    async def list_run(
        self, list_id: int, *, source: str = "oth"
    ) -> dict[str, Any]:
        r = await self._request(
            "POST",
            f"/scrape-lists/{list_id}/run",
            json={"source": source},
        )
        return r.json()

    # --------- jobs ---------

    async def jobs_ls(
        self,
        *,
        status: str | None = None,
        list_id: int | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if status is not None:
            params["status"] = status
        if list_id is not None:
            params["list_id"] = list_id
        r = await self._request("GET", "/jobs", params=params)
        return r.json()

    async def jobs_get(self, job_id: int) -> dict[str, Any]:
        r = await self._request("GET", f"/jobs/{job_id}")
        return r.json()

    # --------- listings ---------

    async def listings_ls(
        self,
        *,
        suburb: int | None = None,
        category: str | None = None,
        active: bool | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit}
        if suburb is not None:
            params["suburb"] = suburb
        if category is not None:
            params["category"] = category
        if active:
            params["active"] = "true"
        r = await self._request("GET", "/listings", params=params)
        return r.json()

    async def listings_get(self, listing_id: int) -> dict[str, Any]:
        r = await self._request("GET", f"/listings/{listing_id}")
        return r.json()

    async def listings_history(self, listing_id: int) -> list[dict[str, Any]]:
        r = await self._request("GET", f"/listings/{listing_id}/snapshots")
        return r.json()


@asynccontextmanager
async def cli_api_client() -> AsyncIterator[CliApiClient]:
    """Open a CliApiClient bound to ``settings.scraper_base_url``."""
    base_url = settings.scraper_base_url.rstrip("/")
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        yield CliApiClient(client)
