"""CLI implementation for `oth list ...` commands.

Mirrors the REST surface in ``api/routers/scrape_lists.py``. Both layers call
the same service functions in ``services/scrape_list.py``.
"""
import json
import sys

import typer
from pydantic import ValidationError

from sqlalchemy import select

from oth_scraper.db.engine import AsyncSessionLocal
from oth_scraper.db.models.scrape_list import ScrapeList
from oth_scraper.queue import JobQueue
from oth_scraper.services.scrape_list import (
    AmbiguousSuburbError,
    ScrapeListCreate,
    ScrapeListFilters,
    ScrapeListNotFoundError,
    ScrapeListRead,
    ScrapeListSummary,
    ScrapeListUpdate,
    SuburbAddRequest,
    SuburbAlreadyInListError,
    SuburbNotInListError,
    add_suburb_to_list,
    create_list,
    delete_list,
    get_list,
    list_lists,
    remove_suburb_from_list,
    run_list,
    update_list,
)
from oth_scraper.suburb_resolver import (
    AutocompleteUnavailableError,
    NoMatchError,
)


def _parse_filters(raw: str | None) -> ScrapeListFilters:
    if not raw:
        return ScrapeListFilters()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        typer.echo(f"--filters must be valid JSON: {e}", err=True)
        raise typer.Exit(code=2)
    try:
        return ScrapeListFilters.model_validate(data)
    except ValidationError as e:
        typer.echo(f"Invalid filters: {e}", err=True)
        raise typer.Exit(code=2)


async def list_create_impl(
    *, name: str, description: str | None, filters_json: str | None
) -> None:
    filters = _parse_filters(filters_json)
    async with AsyncSessionLocal() as session:
        result = await create_list(
            session,
            ScrapeListCreate(
                name=name, description=description, filters=filters
            ),
        )
    _print_list(result)


async def list_ls_impl() -> None:
    async with AsyncSessionLocal() as session:
        rows = await list_lists(session)
    if not rows:
        typer.echo("(no scrape lists)")
        return
    for r in rows:
        _print_summary(r)


async def list_show_impl(*, list_id: int) -> None:
    async with AsyncSessionLocal() as session:
        try:
            result = await get_list(session, list_id)
        except ScrapeListNotFoundError as e:
            typer.echo(f"Not found: {e}", err=True)
            raise typer.Exit(code=1)
    _print_list(result)


async def list_update_impl(
    *,
    list_id: int,
    name: str | None,
    description: str | None,
    filters_json: str | None,
) -> None:
    update = ScrapeListUpdate(
        name=name,
        description=description,
        filters=_parse_filters(filters_json) if filters_json is not None else None,
    )
    async with AsyncSessionLocal() as session:
        try:
            result = await update_list(session, list_id, update)
        except ScrapeListNotFoundError as e:
            typer.echo(f"Not found: {e}", err=True)
            raise typer.Exit(code=1)
    _print_list(result)


async def list_rm_impl(*, list_id: int) -> None:
    async with AsyncSessionLocal() as session:
        try:
            await delete_list(session, list_id)
        except ScrapeListNotFoundError as e:
            typer.echo(f"Not found: {e}", err=True)
            raise typer.Exit(code=1)
    typer.echo(f"Deleted scrape list {list_id}")


async def list_add_suburb_impl(
    *,
    list_id: int,
    name: str,
    postcode: str | None,
    state: str | None,
) -> None:
    request = SuburbAddRequest(name=name, postcode=postcode, state=state)
    async with AsyncSessionLocal() as session:
        try:
            result = await add_suburb_to_list(session, list_id, request)
        except ScrapeListNotFoundError as e:
            typer.echo(f"Not found: {e}", err=True)
            raise typer.Exit(code=1)
        except AmbiguousSuburbError as e:
            typer.echo(
                f"Ambiguous: {len(e.candidates)} candidates for {name!r}. "
                "Re-run with --postcode and/or --state.",
                err=True,
            )
            for m in e.candidates:
                typer.echo(
                    f"  {m.name}, {m.state} {m.postcode}  ({m.oth_slug})",
                    err=True,
                )
            raise typer.Exit(code=3)
        except SuburbAlreadyInListError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=4)
        except NoMatchError as e:
            typer.echo(f"No match: {e}", err=True)
            raise typer.Exit(code=1)
        except AutocompleteUnavailableError as e:
            typer.echo(f"OTH autocomplete unavailable: {e}", err=True)
            raise typer.Exit(code=2)
    typer.echo(f"Added: {result.name}, {result.state} {result.postcode} → list {list_id}")


async def list_run_impl(*, target: str) -> None:
    """Resolve `target` (numeric id or name) and fan out one job per
    (suburb × category) for `[forsale, forrent, recentlysold]`."""
    async with AsyncSessionLocal() as session:
        list_id = await _resolve_list_id(session, target)
        if list_id is None:
            typer.echo(f"Not found: scrape list {target!r}", err=True)
            raise typer.Exit(code=1)
        queue = JobQueue(AsyncSessionLocal)
        try:
            result = await run_list(session, list_id, queue)
        except ScrapeListNotFoundError as e:
            typer.echo(f"Not found: {e}", err=True)
            raise typer.Exit(code=1)
    typer.echo(
        f"Enqueued {result.count} jobs for list {result.list_id}: "
        f"{result.job_ids}"
    )


async def _resolve_list_id(session, target: str) -> int | None:
    """Accept numeric id or unique name; return list_id or None."""
    if target.isdigit():
        list_id = int(target)
        row = await session.get(ScrapeList, list_id)
        return list_id if row is not None else None
    rows = (
        await session.execute(
            select(ScrapeList).where(ScrapeList.name == target)
        )
    ).scalars().all()
    if not rows:
        return None
    if len(rows) > 1:
        typer.echo(
            f"Ambiguous name {target!r} — {len(rows)} matches; use the id.",
            err=True,
        )
        raise typer.Exit(code=2)
    return rows[0].id


async def list_rm_suburb_impl(*, list_id: int, suburb_id: int) -> None:
    async with AsyncSessionLocal() as session:
        try:
            await remove_suburb_from_list(session, list_id, suburb_id)
        except (ScrapeListNotFoundError, SuburbNotInListError) as e:
            typer.echo(f"Not found: {e}", err=True)
            raise typer.Exit(code=1)
    typer.echo(f"Removed suburb {suburb_id} from list {list_id}")


def _print_list(r: ScrapeListRead) -> None:
    typer.echo(f"#{r.id} {r.name}")
    if r.description:
        typer.echo(f"  description: {r.description}")
    typer.echo(f"  filters: {r.filters.model_dump(exclude_none=True)}")
    if r.cron_schedule:
        typer.echo(f"  cron: {r.cron_schedule}")
    typer.echo(f"  created: {r.created_at.isoformat()}")
    if r.suburbs:
        typer.echo("  suburbs:")
        for s in r.suburbs:
            typer.echo(f"    [{s.id}] {s.name}, {s.state} {s.postcode}")
    else:
        typer.echo("  suburbs: (none)")


def _print_summary(r: ScrapeListSummary) -> None:
    typer.echo(
        f"#{r.id:>4}  {r.name}  ({r.suburb_count} suburbs)"
        + (f"  — {r.description}" if r.description else "")
    )
