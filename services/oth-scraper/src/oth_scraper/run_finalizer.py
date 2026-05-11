"""ScrapeRunFinalizer — keeps scrape_run.(status, completed_at) consistent.

Called at the end of every terminal job transition (complete / fail→deadletter
/ reclaim_stuck).  The single public method ``recompute(run_id)`` issues ONE
idempotent UPDATE that derives the run's status from the current state of its
child ``scrape_job`` rows.

Concurrency-safety
------------------
Two workers racing on the last job of a run both call ``recompute()``
simultaneously.  Because the UPDATE is a single statement evaluated inside the
same transaction as the job write, Postgres serialises the two updates on the
``scrape_run`` row and both converge to the same final status.

Idempotency
-----------
Re-invoking ``recompute()`` on an already-terminal run re-evaluates the
expression — if no child changed, the SET values are identical to what's
already stored, so the row doesn't change (same-value UPDATE is a no-op at
the storage level in Postgres, and the application has no side-effects).

Status derivation (mirrors PRD spec)
--------------------------------------
  terminal = succeeded | failed | deadletter

  all_done       = every child is terminal
  all_succeeded  = every child is succeeded
  any_failed     = at least one child is failed OR deadletter
  any_succeeded  = at least one child is succeeded

  not all_done                          → running
  all_done and all_succeeded            → succeeded
  all_done and any_failed and any_succ  → partial
  all_done and any_failed               → failed

  completed_at = MAX(scrape_job.completed_at) when all_done ELSE NULL
"""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# One idempotent UPDATE that encodes the entire status-derivation table.
# Uses a CTE to compute the aggregate once, then drives the CASE in SET.
_RECOMPUTE_SQL = text(
    """
    WITH agg AS (
        SELECT
            COUNT(*) FILTER (
                WHERE status NOT IN ('succeeded', 'failed', 'deadletter')
            ) AS pending_count,
            COUNT(*) FILTER (
                WHERE status = 'succeeded'
            ) AS succeeded_count,
            COUNT(*) FILTER (
                WHERE status IN ('failed', 'deadletter')
            ) AS failed_count,
            MAX(completed_at) AS max_completed_at
        FROM scrape_job
        WHERE run_id = :run_id
    )
    UPDATE scrape_run r
    SET
        status = CASE
            WHEN agg.pending_count > 0
                THEN 'running'::scrape_run_status
            WHEN agg.failed_count = 0
                THEN 'succeeded'::scrape_run_status
            WHEN agg.succeeded_count > 0
                THEN 'partial'::scrape_run_status
            ELSE
                'failed'::scrape_run_status
        END,
        completed_at = CASE
            WHEN agg.pending_count = 0
                THEN agg.max_completed_at
            ELSE NULL
        END
    FROM agg
    WHERE r.id = :run_id
    """
)


class ScrapeRunFinalizer:
    """Recomputes ``scrape_run`` status from child job state.

    Accepts an ``async_sessionmaker`` so tests can inject a throwaway container.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def recompute(self, run_id: int) -> None:
        """Derive and persist ``(status, completed_at)`` for *run_id*.

        Safe to call multiple times — converges to the correct state each time.
        """
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(_RECOMPUTE_SQL, {"run_id": run_id})
        logger.debug("scrape_run %s recomputed", run_id)
