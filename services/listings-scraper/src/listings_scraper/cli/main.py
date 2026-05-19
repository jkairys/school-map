"""Typer entrypoint for the ``oth`` CLI.

Every command shells out to a running api over HTTP — the CLI never opens
its own DB session. The base URL comes from ``OTH_SCRAPER_BASE_URL``
(default ``http://127.0.0.1:8000``).
"""
import asyncio
import sys

import typer

from listings_scraper.cli.dev_commands import session_smoke
from listings_scraper.vendor import Vendor
from listings_scraper.cli.jobs_commands import jobs_ls_impl, jobs_show_impl
from listings_scraper.cli.list_commands import (
    list_add_suburb_impl,
    list_create_impl,
    list_ls_impl,
    list_rm_impl,
    list_rm_suburb_impl,
    list_run_impl,
    list_show_impl,
    list_update_impl,
)
from listings_scraper.cli.listings_commands import (
    listings_history_impl,
    listings_ls_impl,
    listings_show_impl,
)
from listings_scraper.cli.suburb_commands import suburb_resolve_impl

app = typer.Typer(name="oth", help="OTH Scraper CLI")

suburb_app = typer.Typer(help="Suburb commands")
list_app = typer.Typer(help="Scrape list commands")
jobs_app = typer.Typer(help="Job commands")
listings_app = typer.Typer(help="Listing commands")
dev_app = typer.Typer(help="Developer-only smoke / diagnostic commands")

app.add_typer(suburb_app, name="suburb")
app.add_typer(list_app, name="list")
app.add_typer(jobs_app, name="jobs")
app.add_typer(listings_app, name="listings")
app.add_typer(dev_app, name="dev")


@dev_app.command("session-smoke")
def dev_session_smoke() -> None:
    """Bootstrap a ScrapeSession and fire 5 live OTH search requests.

    HITL verification command for issue 10. Hits the real OTH service —
    do not run in CI. Exits non-zero if any request fails or trips an
    anti-bot detector.
    """
    session_smoke()


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
        help=(
            "Filters as inline JSON (e.g. '{\"beds_min\":3}') "
            "or @path/to/file.json."
        ),
    ),
) -> None:
    """Create a new scrape list."""
    asyncio.run(
        list_create_impl(name=name, description=description, filters_raw=filters)
    )


@list_app.command("ls")
def list_ls() -> None:
    """List all scrape lists."""
    asyncio.run(list_ls_impl())


@list_app.command("show")
def list_show(target: str) -> None:
    """Show a scrape list with its suburbs. Accepts an id or unique name."""
    asyncio.run(list_show_impl(target=target))


@list_app.command("update")
def list_update(
    target: str,
    name: str = typer.Option(None, "--name"),
    description: str = typer.Option(None, "--description"),
    filters: str = typer.Option(
        None,
        "--filters",
        help="Filters as inline JSON or @path/to/file.json.",
    ),
) -> None:
    """Update name, description, and/or filters on a scrape list.

    `target` accepts an id or unique name.
    """
    asyncio.run(
        list_update_impl(
            target=target,
            name=name,
            description=description,
            filters_raw=filters,
        )
    )


@list_app.command("rm")
def list_rm(target: str) -> None:
    """Delete a scrape list. Accepts an id or unique name."""
    asyncio.run(list_rm_impl(target=target))


@list_app.command("add-suburb")
def list_add_suburb(
    target: str,
    name: str,
    postcode: str = typer.Option(None, "--postcode"),
    state: str = typer.Option(None, "--state"),
) -> None:
    """Add a suburb (resolved via OTH autocomplete) to a list.

    `target` accepts an id or unique name. Use --postcode / --state for
    non-interactive disambiguation when the resolver returns multiple matches.
    """
    asyncio.run(
        list_add_suburb_impl(
            target=target, name=name, postcode=postcode, state=state
        )
    )


@list_app.command("rm-suburb")
def list_rm_suburb(target: str, suburb: str) -> None:
    """Remove a suburb from a list (does not delete the suburb row).

    Both `target` (list) and `suburb` accept either an id or a unique name.
    """
    asyncio.run(list_rm_suburb_impl(target=target, suburb=suburb))


@list_app.command("run")
def list_run(
    target: str,
    source: Vendor = typer.Option(
        Vendor.OTH,
        "--source",
        help="Vendor to run: oth or domain. Defaults to oth.",
    ),
) -> None:
    """Fan out scrape jobs for a list. `target` is an id or unique list name."""
    asyncio.run(list_run_impl(target=target, source=source.value))


@jobs_app.command("ls")
def jobs_ls(
    status: str = typer.Option(None, "--status"),
    list_target: str = typer.Option(
        None, "--list", help="Filter by list id or unique name."
    ),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """List scrape jobs (newest first)."""
    asyncio.run(
        jobs_ls_impl(status=status, list_target=list_target, limit=limit)
    )


@jobs_app.command("show")
def jobs_show(job_id: int) -> None:
    """Show a single job, including last error info."""
    asyncio.run(jobs_show_impl(job_id=job_id))


@listings_app.command("ls")
def listings_ls(
    suburb: int = typer.Option(None, "--suburb", help="Filter by suburb id."),
    category: str = typer.Option(
        None, "--category", help="forsale | forrent | recentlysold"
    ),
    active: bool = typer.Option(
        False, "--active", help="Only listings with closed_at IS NULL."
    ),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """List listings (newest first)."""
    asyncio.run(
        listings_ls_impl(
            suburb=suburb,
            category=category,
            active=active,
            limit=limit,
        )
    )


@listings_app.command("show")
def listings_show(listing_id: int) -> None:
    """Show a listing with its latest snapshot."""
    asyncio.run(listings_show_impl(listing_id=listing_id))


@listings_app.command("history")
def listings_history(listing_id: int) -> None:
    """Show snapshot history for a listing."""
    asyncio.run(listings_history_impl(listing_id=listing_id))


if __name__ == "__main__":
    app()
