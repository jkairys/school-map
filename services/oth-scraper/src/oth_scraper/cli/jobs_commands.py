"""CLI implementation for `oth jobs ...` commands.

Mirrors the REST surface in ``api/routers/jobs.py``. Both layers read from
the same `scrape_job` table; the CLI just renders rows for terminal use.
"""
import typer
from sqlalchemy import select

from oth_scraper.db.engine import AsyncSessionLocal
from oth_scraper.db.models.scrape_job import JOB_STATUS_VALUES, ScrapeJob


async def jobs_ls_impl(
    *,
    status: str | None,
    list_id: int | None,
    limit: int,
) -> None:
    if status is not None and status not in JOB_STATUS_VALUES:
        typer.echo(
            f"--status must be one of {list(JOB_STATUS_VALUES)}", err=True
        )
        raise typer.Exit(code=2)

    async with AsyncSessionLocal() as session:
        stmt = select(ScrapeJob).order_by(ScrapeJob.id.desc())
        if status is not None:
            stmt = stmt.where(ScrapeJob.status == status)
        if list_id is not None:
            stmt = stmt.where(ScrapeJob.scrape_list_id == list_id)
        stmt = stmt.limit(limit)
        rows = (await session.execute(stmt)).scalars().all()

    if not rows:
        typer.echo("(no jobs)")
        return
    for r in rows:
        list_part = (
            f" list={r.scrape_list_id}" if r.scrape_list_id is not None else ""
        )
        typer.echo(
            f"#{r.id:>6}  {r.status:<10}  suburb={r.suburb_id} "
            f"{r.category}{list_part}  attempts={r.attempts}"
        )


async def jobs_show_impl(*, job_id: int) -> None:
    async with AsyncSessionLocal() as session:
        row = await session.get(ScrapeJob, job_id)
    if row is None:
        typer.echo(f"Not found: job {job_id}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"#{row.id} {row.status}")
    typer.echo(f"  suburb_id: {row.suburb_id}")
    typer.echo(f"  category: {row.category}")
    typer.echo(f"  scrape_list_id: {row.scrape_list_id}")
    typer.echo(f"  filters: {row.filters}")
    typer.echo(f"  attempts: {row.attempts}")
    if row.last_error_class:
        typer.echo(f"  last_error_class: {row.last_error_class}")
        typer.echo(f"  last_error_message: {row.last_error_message}")
    typer.echo(f"  created_at: {row.created_at.isoformat()}")
    if row.claimed_at:
        typer.echo(f"  claimed_at: {row.claimed_at.isoformat()}")
    if row.completed_at:
        typer.echo(f"  completed_at: {row.completed_at.isoformat()}")
