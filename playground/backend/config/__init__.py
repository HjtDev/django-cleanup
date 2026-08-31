# Celery app registered here so `shared_task` picks it up (docs/CONTRACT.md §8's own convention
# for any host that installs the celery extra).
from config.celery import app as celery_app

__all__ = ["celery_app"]
