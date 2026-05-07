"""CLI implementation for `oth suburb resolve`.

Kept in its own module so it can be unit-tested without spinning up Typer.
"""

import sys

import typer

from oth_scraper.db.engine import AsyncSessionLocal
from oth_scraper.services.suburb import resolve_suburb
from oth_scraper.suburb_resolver import (
    AutocompleteUnavailableError,
    Match,
    NoMatchError,
    ResolvedSuburb,
)


async def suburb_resolve_impl(
    *, name: str, postcode: str | None, state: str | None, interactive: bool
) -> None:
    async with AsyncSessionLocal() as session:
        try:
            result = await resolve_suburb(
                name, session=session, postcode=postcode, state=state
            )
        except NoMatchError as e:
            typer.echo(f"No match: {e}", err=True)
            raise typer.Exit(code=1)
        except AutocompleteUnavailableError as e:
            typer.echo(f"OTH autocomplete unavailable: {e}", err=True)
            raise typer.Exit(code=2)

    if isinstance(result, ResolvedSuburb):
        _print_resolved(result)
        return

    if not interactive:
        typer.echo(
            f"Ambiguous: {len(result)} candidates for {name!r}. "
            "Re-run with --postcode and/or --state.",
            err=True,
        )
        for m in result:
            typer.echo(f"  {m.name}, {m.state} {m.postcode}  ({m.oth_slug})", err=True)
        raise typer.Exit(code=3)

    chosen = _prompt_choice(result)
    async with AsyncSessionLocal() as session:
        result = await resolve_suburb(
            chosen.name,
            session=session,
            postcode=chosen.postcode,
            state=chosen.state,
        )
    assert isinstance(result, ResolvedSuburb)
    _print_resolved(result)


def _print_resolved(r: ResolvedSuburb) -> None:
    typer.echo(f"{r.name}, {r.state} {r.postcode}")
    typer.echo(f"  slug: {r.oth_slug}")
    typer.echo(f"  id: {r.id}")


def _prompt_choice(matches: list[Match]) -> Match:
    typer.echo(f"{len(matches)} matches — pick one:", err=True)
    for i, m in enumerate(matches, 1):
        typer.echo(f"  [{i}] {m.name}, {m.state} {m.postcode}", err=True)
    while True:
        raw = typer.prompt("Choice", default="1")
        try:
            idx = int(raw)
        except ValueError:
            typer.echo("Enter a number.", err=True)
            continue
        if 1 <= idx <= len(matches):
            return matches[idx - 1]
        typer.echo(f"Out of range (1..{len(matches)}).", err=True)
