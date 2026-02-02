"""Background tasks for automatic health checks."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
from app.models.health import FinanceHealthRun
from app.services.finance_health_service import finance_health_service

logger = logging.getLogger(__name__)

# Health check interval (24 hours in seconds)
HEALTH_CHECK_INTERVAL = 24 * 60 * 60

# Flag to stop the background task
_stop_health_check = False


async def run_finance_health_check(trigger: str = "scheduled") -> dict | None:
    """Run finance health check and persist results."""
    engine = create_async_engine(settings.database_url)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with async_session() as db:
            started_at = datetime.now(UTC)
            logger.info(f"Starting finance health check (trigger: {trigger})")

            try:
                result = await finance_health_service.run_all_checks(db)

                completed_at = datetime.now(UTC)
                duration_ms = int((completed_at - started_at).total_seconds() * 1000)

                # Persist the run
                health_run = FinanceHealthRun(
                    status=result["status"],
                    checks=result["checks"],
                    counts=result["counts"],
                    trigger=trigger,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                )
                db.add(health_run)
                await db.commit()

                logger.info(
                    f"Finance health check completed: status={result['status']}, "
                    f"duration={duration_ms}ms, checks={len(result['checks'])}"
                )

                # Log warnings/errors
                for check in result["checks"]:
                    if check["status"] != "OK":
                        logger.warning(
                            f"Health check '{check['name']}': {check['status']} - {check['message']}"
                        )

                return result

            except Exception as e:
                completed_at = datetime.now(UTC)
                duration_ms = int((completed_at - started_at).total_seconds() * 1000)

                # Persist failed run
                health_run = FinanceHealthRun(
                    status="ERROR",
                    checks=[],
                    counts={},
                    trigger=trigger,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    error_message=str(e),
                )
                db.add(health_run)
                await db.commit()

                logger.error(f"Finance health check failed: {e}")
                return None

    finally:
        await engine.dispose()


async def start_health_check_scheduler():
    """Background task that runs health check every 24 hours."""
    global _stop_health_check
    _stop_health_check = False

    logger.info("Finance health check scheduler started")

    while not _stop_health_check:
        try:
            await run_finance_health_check(trigger="scheduled")
        except Exception as e:
            logger.error(f"Scheduled health check error: {e}")

        # Wait for next interval (check stop flag every minute)
        for _ in range(HEALTH_CHECK_INTERVAL // 60):
            if _stop_health_check:
                break
            await asyncio.sleep(60)

    logger.info("Finance health check scheduler stopped")


def stop_health_check_scheduler():
    """Signal the health check scheduler to stop."""
    global _stop_health_check
    _stop_health_check = True


async def run_startup_health_check():
    """Run health check on application startup."""
    logger.info("Running startup finance health check")
    await run_finance_health_check(trigger="startup")
