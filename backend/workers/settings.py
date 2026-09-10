from __future__ import annotations

from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings

from backend.config import get_backend_settings
from backend.workers.jobs import run_analysis_job, run_cross_review
from backend.workers.runtime_identity import refresh_worker_identity


def redis_settings() -> RedisSettings:
    settings = get_backend_settings()
    return RedisSettings.from_dsn(settings.redis_url)


class WorkerSettings:
    functions: ClassVar = [run_analysis_job, run_cross_review]
    on_startup = refresh_worker_identity
    cron_jobs: ClassVar = [
        cron(
            refresh_worker_identity,
            second={0, 10, 20, 30, 40, 50},
            run_at_startup=False,
        )
    ]
    redis_settings = redis_settings()
    max_jobs: int = 1
    # 外层兜底上限 1200s；具体任务的实际执行上限由 jobs._resolve_job_deadline
    # 按 provider/model 施加（普通通道 600s、Maike 中转 gpt 通道 1000s），
    # 因此该值需大于内层上限以免 ARQ 提前掐断慢速但受控的任务。
    job_timeout: int = 1200


__all__ = ["WorkerSettings"]
