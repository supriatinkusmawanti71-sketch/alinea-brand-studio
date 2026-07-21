from celery import Celery

from apps.api.app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "brand_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["apps.api.app.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    timezone="Asia/Shanghai",
    enable_utc=True,
    # Hard-kill any task after 30 minutes so a stage run cannot legitimately
    # outlive the stuck-RUNNING recovery threshold (35 minutes).
    task_time_limit=30 * 60,
    beat_schedule={
        "recover-stuck-stage-runs": {
            "task": "agent.recover_stuck_stage_runs",
            "schedule": 60.0,
        },
    },
)
