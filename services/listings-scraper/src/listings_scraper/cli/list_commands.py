"""CLI implementation for `oth list ...` commands.

Mirrors ``api/routers/scrape_lists.py`` over HTTP. Every command resolves
its target argument as either a numeric id or a unique list name before
hitting the api, so a user can do either::

    oth list show 17
    oth list show "Sunshine Coast family homes"
"""
from __future__ import annotations

from typing import Any

import typer

from listings_scraper.cli._helpers import (
    detail_message,
    parse_filters,
    resolve_list_id,
    resolve_suburb_in_list,
)
from listings_scraper.cli.api_client import ApiError, CliApiClient, cli_api_client


async def list_create_impl(
    *, name: str, description: str | None, filters_raw: str | None
) -> None:
    payload: dict[str, Any] = {"name": name}
    if description is not None:
        payload["description"] = description
    filters = parse_filters(filters_raw)
    if filters is not None:
        payload["filters"] = filters
    async with cli_api_client() as client:
        try:
            result = await client.list_create(payload)
        except ApiError as e:
            typer.echo(
                f"Create failed ({e.status_code}): {detail_message(e.detail)}",
                err=True,
            )
            raise typer.Exit(code=1) from e
    _print_list(result)


async def list_ls_impl() -> None:
    async with cli_api_client() as client:
        rows = await client.list_ls()
    if not rows:
        typer.echo("(no scrape lists)")
        return
    for r in rows:
        _print_summary(r)


async def list_show_impl(*, target: str) -> None:
    async with cli_api_client() as client:
        list_id = await resolve_list_id(client, target)
        result = await client.list_get(list_id)
    _print_list(result)


async def list_update_impl(
    *,
    target: str,
    name: str | None,
    description: str | None,
    filters_raw: str | None,
) -> None:
    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    filters = parse_filters(filters_raw)
    if filters is not None:
        body["filters"] = filters
    async with cli_api_client() as client:
        list_id = await resolve_list_id(client, target)
        try:
            result = await client.list_update(list_id, body)
        except ApiError as e:
            typer.echo(
                f"Update failed ({e.status_code}): {detail_message(e.detail)}",
                err=True,
            )
            raise typer.Exit(code=1) from e
    _print_list(result)


async def list_rm_impl(*, target: str) -> None:
    async with cli_api_client() as client:
        list_id = await resolve_list_id(client, target)
        await client.list_delete(list_id)
    typer.echo(f"Deleted scrape list {list_id}")


async def list_add_suburb_impl(
    *,
    target: str,
    name: str,
    postcode: str | None,
    state: str | None,
) -> None:
    body: dict[str, Any] = {"name": name}
    if postcode is not None:
        body["postcode"] = postcode
    if state is not None:
        body["state"] = state
    async with cli_api_client() as client:
        list_id = await resolve_list_id(client, target)
        try:
            result = await client.list_add_suburb(list_id, body)
        except ApiError as e:
            _handle_add_suburb_error(e, name, list_id)
            return
    typer.echo(
        f"Added: {result['name']}, {result['state']} {result['postcode']} → list {list_id}"
    )


def _handle_add_suburb_error(e: ApiError, name: str, list_id: int) -> None:
    if e.status_code == 409:
        # Could be ambiguous (with candidates) or already-in-list (string).
        d = e.detail.get("detail") if isinstance(e.detail, dict) else None
        if isinstance(d, dict) and "candidates" in d:
            cands = d["candidates"]
            typer.echo(
                f"Ambiguous: {len(cands)} candidates for {name!r}. "
                "Re-run with --postcode and/or --state.",
                err=True,
            )
            for m in cands:
                typer.echo(
                    f"  {m['name']}, {m['state']} {m['postcode']}  ({m['oth_slug']})",
                    err=True,
                )
            raise typer.Exit(code=3) from e
        typer.echo(detail_message(e.detail), err=True)
        raise typer.Exit(code=4) from e
    if e.status_code == 404:
        typer.echo(f"Not found: {detail_message(e.detail)}", err=True)
        raise typer.Exit(code=1) from e
    if e.status_code == 503:
        typer.echo(
            f"OTH autocomplete unavailable: {detail_message(e.detail)}",
            err=True,
        )
        raise typer.Exit(code=2) from e
    typer.echo(
        f"Unexpected api error {e.status_code}: {detail_message(e.detail)}",
        err=True,
    )
    raise typer.Exit(code=1) from e


async def list_run_impl(*, target: str) -> None:
    """Resolve `target` (numeric id or name) and POST .../run."""
    async with cli_api_client() as client:
        list_id = await resolve_list_id(client, target)
        result = await client.list_run(list_id)
    typer.echo(
        f"Enqueued {result['count']} jobs for list {result['list_id']}: "
        f"{result['job_ids']}"
    )


async def list_rm_suburb_impl(*, target: str, suburb: str) -> None:
    async with cli_api_client() as client:
        list_id = await resolve_list_id(client, target)
        suburb_id = await resolve_suburb_in_list(client, list_id, suburb)
        try:
            await client.list_remove_suburb(list_id, suburb_id)
        except ApiError as e:
            if e.status_code == 404:
                typer.echo(f"Not found: {detail_message(e.detail)}", err=True)
                raise typer.Exit(code=1) from e
            raise
    typer.echo(f"Removed suburb {suburb_id} from list {list_id}")


def _print_list(r: dict[str, Any]) -> None:
    typer.echo(f"#{r['id']} {r['name']}")
    if r.get("description"):
        typer.echo(f"  description: {r['description']}")
    filters = r.get("filters") or {}
    filters_compact = {k: v for k, v in filters.items() if v is not None}
    typer.echo(f"  filters: {filters_compact}")
    if r.get("cron_schedule"):
        typer.echo(f"  cron: {r['cron_schedule']}")
    typer.echo(f"  created: {r['created_at']}")
    suburbs = r.get("suburbs") or []
    if suburbs:
        typer.echo("  suburbs:")
        for s in suburbs:
            typer.echo(
                f"    [{s['id']}] {s['name']}, {s['state']} {s['postcode']}"
            )
    else:
        typer.echo("  suburbs: (none)")


def _print_summary(r: dict[str, Any]) -> None:
    desc = f"  — {r['description']}" if r.get("description") else ""
    typer.echo(
        f"#{int(r['id']):>4}  {r['name']}  ({r['suburb_count']} suburbs){desc}"
    )


# Re-exported so tests / external callers can monkeypatch the API client.
__all__ = [
    "CliApiClient",
    "list_add_suburb_impl",
    "list_create_impl",
    "list_ls_impl",
    "list_rm_impl",
    "list_rm_suburb_impl",
    "list_run_impl",
    "list_show_impl",
    "list_update_impl",
]
