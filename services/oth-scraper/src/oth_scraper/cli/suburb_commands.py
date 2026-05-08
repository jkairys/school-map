"""CLI implementation for `oth suburb resolve`.

Calls ``POST /suburbs/resolve`` over HTTP. On 409 the api returns a
candidate list; in a TTY we prompt the user to pick one and re-resolve
with the chosen postcode/state. In non-TTY mode the candidates print to
stderr and the command exits non-zero.
"""
from __future__ import annotations

from typing import Any

import typer

from oth_scraper.cli._helpers import detail_message
from oth_scraper.cli.api_client import ApiError, cli_api_client


async def suburb_resolve_impl(
    *, name: str, postcode: str | None, state: str | None, interactive: bool
) -> None:
    async with cli_api_client() as client:
        try:
            resolved = await client.resolve_suburb(
                name, postcode=postcode, state=state
            )
        except ApiError as e:
            if e.status_code == 404:
                typer.echo(f"No match: {detail_message(e.detail)}", err=True)
                raise typer.Exit(code=1) from e
            if e.status_code == 503:
                typer.echo(
                    f"OTH autocomplete unavailable: {detail_message(e.detail)}",
                    err=True,
                )
                raise typer.Exit(code=2) from e
            if e.status_code == 409:
                candidates = _candidates_from_detail(e.detail)
                if not interactive:
                    typer.echo(
                        f"Ambiguous: {len(candidates)} candidates for {name!r}. "
                        "Re-run with --postcode and/or --state.",
                        err=True,
                    )
                    for m in candidates:
                        typer.echo(
                            f"  {m['name']}, {m['state']} {m['postcode']}  ({m['oth_slug']})",
                            err=True,
                        )
                    raise typer.Exit(code=3) from e
                chosen = _prompt_choice(candidates)
                try:
                    resolved = await client.resolve_suburb(
                        chosen["name"],
                        postcode=chosen["postcode"],
                        state=chosen["state"],
                    )
                except ApiError as e2:  # pragma: no cover - defensive
                    typer.echo(
                        f"Resolve failed after disambiguation: {detail_message(e2.detail)}",
                        err=True,
                    )
                    raise typer.Exit(code=1) from e2
            else:
                typer.echo(
                    f"Unexpected api error {e.status_code}: {detail_message(e.detail)}",
                    err=True,
                )
                raise typer.Exit(code=1) from e

    _print_resolved(resolved)


def _candidates_from_detail(detail: Any) -> list[dict[str, Any]]:
    if isinstance(detail, dict):
        d = detail.get("detail", detail)
        if isinstance(d, dict) and "candidates" in d:
            return list(d["candidates"])
    return []


def _print_resolved(r: dict[str, Any]) -> None:
    typer.echo(f"{r['name']}, {r['state']} {r['postcode']}")
    typer.echo(f"  slug: {r['oth_slug']}")
    typer.echo(f"  id: {r['id']}")


def _prompt_choice(matches: list[dict[str, Any]]) -> dict[str, Any]:
    typer.echo(f"{len(matches)} matches — pick one:", err=True)
    for i, m in enumerate(matches, 1):
        typer.echo(
            f"  [{i}] {m['name']}, {m['state']} {m['postcode']}", err=True
        )
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
