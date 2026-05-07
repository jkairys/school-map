import asyncio
import sys

import typer

from oth_scraper.cli.list_commands import (
    list_add_suburb_impl,
    list_create_impl,
    list_ls_impl,
    list_rm_impl,
    list_rm_suburb_impl,
    list_show_impl,
    list_update_impl,
)
from oth_scraper.cli.suburb_commands import suburb_resolve_impl

app = typer.Typer(name="oth", help="OTH Scraper CLI")

suburb_app = typer.Typer(help="Suburb commands")
list_app = typer.Typer(help="Scrape list commands")
jobs_app = typer.Typer(help="Job commands")
listings_app = typer.Typer(help="Listing commands")

app.add_typer(suburb_app, name="suburb")
app.add_typer(list_app, name="list")
app.add_typer(jobs_app, name="jobs")
app.add_typer(listings_app, name="listings")


@suburb_app.command("resolve")
def suburb_resolve(
    name: str,
    postcode: str = typer.Option(None, "--postcode", help="Disambiguate by postcode"),
    state: str = typer.Option(None, "--state", help="Disambiguate by state code, e.g. QLD"),
) -> None:
    """Resolve a suburb name to postcode/state via OTH autocomplete.

    On ambiguity in a TTY, prompts to pick a candidate. In non-TTY contexts,
    use --postcode and/or --state to disambiguate; otherwise exits non-zero
    with the candidate list on stderr.
    """
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    asyncio.run(
        suburb_resolve_impl(
            name=name, postcode=postcode, state=state, interactive=interactive
        )
    )


@list_app.command("create")
def list_create(
    name: str,
    description: str = typer.Option(None, "--description"),
    filters: str = typer.Option(
        None,
        "--filters",
        help='JSON string, e.g. \'{"beds_min":3,"price_max":1500000}\'',
    ),
) -> None:
    """Create a new scrape list."""
    asyncio.run(
        list_create_impl(name=name, description=description, filters_json=filters)
    )


@list_app.command("ls")
def list_ls() -> None:
    """List all scrape lists."""
    asyncio.run(list_ls_impl())


@list_app.command("show")
def list_show(list_id: int) -> None:
    """Show a scrape list with its suburbs."""
    asyncio.run(list_show_impl(list_id=list_id))


@list_app.command("update")
def list_update(
    list_id: int,
    name: str = typer.Option(None, "--name"),
    description: str = typer.Option(None, "--description"),
    filters: str = typer.Option(None, "--filters", help="JSON string"),
) -> None:
    """Update name, description, and/or filters on a scrape list."""
    asyncio.run(
        list_update_impl(
            list_id=list_id,
            name=name,
            description=description,
            filters_json=filters,
        )
    )


@list_app.command("rm")
def list_rm(list_id: int) -> None:
    """Delete a scrape list (cascades the list↔suburb m2m only)."""
    asyncio.run(list_rm_impl(list_id=list_id))


@list_app.command("add-suburb")
def list_add_suburb(
    list_id: int,
    name: str,
    postcode: str = typer.Option(None, "--postcode"),
    state: str = typer.Option(None, "--state"),
) -> None:
    """Add a suburb (resolved via OTH autocomplete) to a list."""
    asyncio.run(
        list_add_suburb_impl(
            list_id=list_id, name=name, postcode=postcode, state=state
        )
    )


@list_app.command("rm-suburb")
def list_rm_suburb(list_id: int, suburb_id: int) -> None:
    """Remove a suburb from a list (does not delete the suburb row)."""
    asyncio.run(list_rm_suburb_impl(list_id=list_id, suburb_id=suburb_id))


@jobs_app.command("ls")
def jobs_ls() -> None:
    """List scrape jobs."""
    typer.echo("TODO: list jobs")


@listings_app.command("ls")
def listings_ls() -> None:
    """List listings."""
    typer.echo("TODO: list listings")


@listings_app.command("history")
def listings_history(listing_id: str) -> None:
    """Show snapshot history for a listing."""
    typer.echo(f"TODO: listing history '{listing_id}'")


if __name__ == "__main__":
    app()
