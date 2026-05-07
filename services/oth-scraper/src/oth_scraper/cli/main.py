import asyncio
import sys

import typer

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
def list_create(name: str) -> None:
    """Create a new scrape list."""
    typer.echo(f"TODO: create scrape list '{name}'")


@list_app.command("show")
def list_show(list_id: str) -> None:
    """Show a scrape list."""
    typer.echo(f"TODO: show scrape list '{list_id}'")


@list_app.command("run")
def list_run(list_id: str) -> None:
    """Fan out scrape jobs for all suburbs in the list."""
    typer.echo(f"TODO: run scrape list '{list_id}'")


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
