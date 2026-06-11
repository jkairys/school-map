"""CLI implementation for `oth listings ...` commands.

Calls ``GET /listings``, ``GET /listings/{id}``, ``GET /listings/{id}/snapshots``.
"""
from __future__ import annotations

import typer

from listings_scraper.cli._helpers import detail_message
from listings_scraper.cli.api_client import ApiError, cli_api_client


async def listings_ls_impl(
    *,
    suburb: int | None,
    category: str | None,
    active: bool,
    limit: int,
) -> None:
    async with cli_api_client() as client:
        try:
            rows = await client.listings_ls(
                suburb=suburb, category=category, active=active, limit=limit
            )
        except ApiError as e:
            typer.echo(
                f"listings ls failed ({e.status_code}): {detail_message(e.detail)}",
                err=True,
            )
            raise typer.Exit(code=2) from e

    if not rows:
        typer.echo("(no listings)")
        return
    for r in rows:
        closed = (
            f" closed={r['closed_at']} reason={r.get('closure_reason')}"
            if r.get("closed_at")
            else ""
        )
        typer.echo(
            f"#{int(r['id']):>6}  {r['category']:<13}  property={r['property_id']} "
            f"suburb={r['suburb_id']}  last_seen={r['last_seen_at']}{closed}"
        )


async def listings_show_impl(*, listing_id: int) -> None:
    async with cli_api_client() as client:
        try:
            row = await client.listings_get(listing_id)
        except ApiError as e:
            if e.status_code == 404:
                typer.echo(f"Not found: listing {listing_id}", err=True)
                raise typer.Exit(code=1) from e
            raise

    typer.echo(f"#{row['id']} {row['category']}")
    typer.echo(f"  property_id: {row['property_id']}")
    typer.echo(f"  suburb_id: {row['suburb_id']}")
    typer.echo(f"  external_listing_id: {row.get('external_listing_id')}")
    typer.echo(
        f"  agent: {row.get('agent_name')}  agency: {row.get('agency_name')}"
    )
    typer.echo(f"  first_seen_at: {row['first_seen_at']}")
    typer.echo(f"  last_seen_at: {row['last_seen_at']}")
    if row.get("closed_at"):
        typer.echo(
            f"  closed_at: {row['closed_at']} ({row.get('closure_reason')})"
        )
    latest = row.get("latest_snapshot")
    if latest is not None:
        typer.echo("  latest snapshot:")
        typer.echo(f"    observed_at: {latest['observed_at']}")
        typer.echo(f"    price: {latest.get('price')}")
        typer.echo(f"    bedrooms: {latest.get('bedrooms')}")
        typer.echo(f"    status: {latest.get('status')}")
        typer.echo(f"    changed_fields: {latest.get('changed_fields')}")


async def listings_history_impl(*, listing_id: int) -> None:
    async with cli_api_client() as client:
        try:
            rows = await client.listings_history(listing_id)
        except ApiError as e:
            if e.status_code == 404:
                typer.echo(f"Not found: listing {listing_id}", err=True)
                raise typer.Exit(code=1) from e
            raise

    if not rows:
        typer.echo("(no snapshots)")
        return
    for r in rows:
        typer.echo(
            f"#{int(r['id']):>6}  {r['observed_at']}  price={r.get('price')} "
            f"status={r.get('status')}  changed={r.get('changed_fields')}"
        )


