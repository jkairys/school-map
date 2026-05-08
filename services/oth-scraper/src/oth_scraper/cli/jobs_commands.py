"""CLI implementation for `oth jobs ...` commands.

Calls ``GET /jobs`` and ``GET /jobs/{id}`` over HTTP.
"""
from __future__ import annotations

from typing import Any

import typer

from oth_scraper.cli._helpers import detail_message, resolve_list_id
from oth_scraper.cli.api_client import ApiError, cli_api_client


async def jobs_ls_impl(
    *,
    status: str | None,
    list_target: str | None,
    limit: int,
) -> None:
    async with cli_api_client() as client:
        list_id: int | None = None
        if list_target is not None:
            list_id = await resolve_list_id(client, list_target)
        try:
            rows = await client.jobs_ls(
                status=status, list_id=list_id, limit=limit
            )
        except ApiError as e:
            typer.echo(
                f"jobs ls failed ({e.status_code}): {detail_message(e.detail)}",
                err=True,
            )
            raise typer.Exit(code=2) from e

    if not rows:
        typer.echo("(no jobs)")
        return
    for r in rows:
        list_part = (
            f" list={r['scrape_list_id']}"
            if r.get("scrape_list_id") is not None
            else ""
        )
        typer.echo(
            f"#{int(r['id']):>6}  {r['status']:<10}  suburb={r['suburb_id']} "
            f"{r['category']}{list_part}  attempts={r['attempts']}"
        )


async def jobs_show_impl(*, job_id: int) -> None:
    async with cli_api_client() as client:
        try:
            row = await client.jobs_get(job_id)
        except ApiError as e:
            if e.status_code == 404:
                typer.echo(f"Not found: job {job_id}", err=True)
                raise typer.Exit(code=1) from e
            raise

    _print_job(row)


def _print_job(row: dict[str, Any]) -> None:
    typer.echo(f"#{row['id']} {row['status']}")
    typer.echo(f"  suburb_id: {row['suburb_id']}")
    typer.echo(f"  category: {row['category']}")
    typer.echo(f"  scrape_list_id: {row.get('scrape_list_id')}")
    typer.echo(f"  filters: {row.get('filters')}")
    typer.echo(f"  attempts: {row['attempts']}")
    if row.get("last_error_class"):
        typer.echo(f"  last_error_class: {row['last_error_class']}")
        typer.echo(f"  last_error_message: {row.get('last_error_message')}")
    typer.echo(f"  created_at: {row['created_at']}")
    if row.get("claimed_at"):
        typer.echo(f"  claimed_at: {row['claimed_at']}")
    if row.get("completed_at"):
        typer.echo(f"  completed_at: {row['completed_at']}")
