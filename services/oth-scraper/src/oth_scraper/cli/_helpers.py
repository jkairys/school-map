"""Shared CLI helpers: filter parsing, id-or-name resolution, error mapping.

These helpers are HTTP-only — they use the ``CliApiClient`` to look things up
rather than touching the database. That keeps the CLI on a single code path
(REST) and means the test harness only has to stand up the api.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from oth_scraper.cli.api_client import ApiError, CliApiClient


def parse_filters(raw: str | None) -> dict[str, Any] | None:
    """Parse a ``--filters`` value.

    Accepts either inline JSON (``'{"beds_min":3}'``) or a path prefixed
    with ``@`` (``@filters.json``). Returns ``None`` when ``raw`` is None.
    Exits with code 2 on parse / file errors.
    """
    if raw is None:
        return None
    if raw.startswith("@"):
        path = Path(raw[1:])
        try:
            text = path.read_text()
        except OSError as e:
            typer.echo(f"--filters: cannot read {path}: {e}", err=True)
            raise typer.Exit(code=2) from e
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            typer.echo(f"--filters: {path} is not valid JSON: {e}", err=True)
            raise typer.Exit(code=2) from e
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        typer.echo(f"--filters must be valid JSON or @path.json: {e}", err=True)
        raise typer.Exit(code=2) from e


async def resolve_list_id(client: CliApiClient, target: str) -> int:
    """Resolve a numeric id or a unique list name to a list id.

    The CLI accepts both for nearly every list-targeted command. Names that
    don't match exactly one list cause a non-zero exit with a clear message.
    """
    if target.isdigit():
        list_id = int(target)
        try:
            await client.list_get(list_id)
        except ApiError as e:
            if e.status_code == 404:
                typer.echo(f"Not found: scrape list {target!r}", err=True)
                raise typer.Exit(code=1) from e
            raise
        return list_id

    rows = await client.list_ls()
    matches = [r for r in rows if r["name"] == target]
    if not matches:
        typer.echo(f"Not found: scrape list {target!r}", err=True)
        raise typer.Exit(code=1)
    if len(matches) > 1:
        typer.echo(
            f"Ambiguous name {target!r} — {len(matches)} matches; use the id.",
            err=True,
        )
        raise typer.Exit(code=2)
    return int(matches[0]["id"])


async def resolve_suburb_in_list(
    client: CliApiClient, list_id: int, target: str
) -> int:
    """Resolve a suburb id-or-name within a specific list.

    Used by ``oth list rm-suburb`` so the user can say
    ``oth list rm-suburb mylist "Little Mountain"`` instead of looking up
    the numeric id first.
    """
    if target.isdigit():
        return int(target)
    detail = await client.list_get(list_id)
    matches = [s for s in detail.get("suburbs", []) if s["name"] == target]
    if not matches:
        typer.echo(
            f"Not found: suburb {target!r} in list {list_id}", err=True
        )
        raise typer.Exit(code=1)
    if len(matches) > 1:
        typer.echo(
            f"Ambiguous suburb name {target!r} in list {list_id} — "
            f"{len(matches)} matches; use the id.",
            err=True,
        )
        raise typer.Exit(code=2)
    return int(matches[0]["id"])


def detail_message(detail: Any) -> str:
    """Best-effort one-liner for an ApiError detail body."""
    if isinstance(detail, dict) and "detail" in detail:
        d = detail["detail"]
        if isinstance(d, str):
            return d
        return json.dumps(d)
    if isinstance(detail, str):
        return detail
    return json.dumps(detail)
