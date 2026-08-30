"""Tests for ``cleanup_app.models`` — ``docs/CONTRACT.md`` §1 verified field-for-field.

Scope is deliberately narrow (models + admin only) per this phase's plan; ``apps.py``'s
``ready()`` branches are covered here only if the coverage gate comes up short without them.
"""

from __future__ import annotations

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

from cleanup_app.factories import CleanupRunFactory, CleanupRunFileFactory
from cleanup_app.models import CleanupRun, CleanupRunFile

pytestmark = pytest.mark.django_db


def test_status_choices() -> None:
    assert set(CleanupRun.Status.values) == {
        "pending",
        "running",
        "success",
        "failed",
        "partial",
    }


def test_trigger_has_four_values_including_auto() -> None:
    """docs/CONTRACT.md §9.4: AUTO is a real fourth trigger, not the guide's three."""
    assert set(CleanupRun.Trigger.values) == {"manual", "scheduled", "api", "auto"}


def test_cleanup_run_defaults() -> None:
    run = CleanupRunFactory(trigger=CleanupRun.Trigger.MANUAL)

    assert run.status == CleanupRun.Status.SUCCESS
    assert run.dry_run is False
    assert run.files_scanned == 0
    assert run.files_deleted == 0
    assert run.files_failed == 0
    assert run.bytes_freed == 0
    assert run.error == ""
    assert run.started_at is not None
    assert run.finished_at is None


def test_initiated_by_references_swappable_user_model() -> None:
    field = CleanupRun._meta.get_field("initiated_by")
    assert field.related_model is get_user_model()
    # settings.AUTH_USER_MODEL, never a concrete User import (docs/CONTRACT.md §1).
    assert settings.AUTH_USER_MODEL


def test_initiated_by_set_null_on_user_delete() -> None:
    user = get_user_model().objects.create_user(**_user_kwargs("alice"))
    run = CleanupRunFactory(initiated_by=user, trigger=CleanupRun.Trigger.API)

    user.delete()
    run.refresh_from_db()

    assert run.initiated_by is None


def test_initiated_by_related_name() -> None:
    user = get_user_model().objects.create_user(**_user_kwargs("bob"))
    run = CleanupRunFactory(initiated_by=user, trigger=CleanupRun.Trigger.API)

    assert list(user.cleanup_runs.all()) == [run]


def test_cleanup_run_str() -> None:
    run = CleanupRunFactory(trigger=CleanupRun.Trigger.SCHEDULED, status=CleanupRun.Status.FAILED)

    assert str(run) == f"CleanupRun #{run.pk} (scheduled/failed)"


def test_cleanup_run_indexes() -> None:
    index_fields = {tuple(index.fields) for index in CleanupRun._meta.indexes}
    assert index_fields == {("status", "-started_at"), ("trigger",)}


def test_cleanup_run_file_defaults_and_fk() -> None:
    run = CleanupRunFactory()
    run_file = CleanupRunFileFactory(run=run)

    assert run_file.run == run
    assert run_file.deleted is False
    assert run_file.quarantined is False
    assert run_file.error == ""
    assert run_file.file_size == 1024


def test_cleanup_run_file_related_name() -> None:
    run = CleanupRunFactory()
    run_file = CleanupRunFileFactory(run=run)

    assert list(run.files.all()) == [run_file]


def test_cleanup_run_file_cascades_on_run_delete() -> None:
    run = CleanupRunFactory()
    run_file = CleanupRunFileFactory(run=run)

    run.delete()

    assert not CleanupRunFile.objects.filter(pk=run_file.pk).exists()


def test_cleanup_run_file_str() -> None:
    run = CleanupRunFactory()
    run_file = CleanupRunFileFactory(run=run, file_path="uploads/orphan-1.bin")

    assert str(run_file) == f"uploads/orphan-1.bin (run #{run.pk})"


def test_cleanup_run_file_indexes() -> None:
    index_fields = {tuple(index.fields) for index in CleanupRunFile._meta.indexes}
    assert index_fields == {("run", "deleted")}


def _user_kwargs(username: str) -> dict[str, str]:
    """Build create_user() kwargs reflectively against USERNAME_FIELD, matching appkit.testing's
    own approach (docs/CONTRACT.md's own test settings ship no custom user model, but this keeps
    the test honest about not hardcoding ``username=``)."""
    field = get_user_model().USERNAME_FIELD
    if field == "email":
        return {"email": f"{username}@example.com", "password": "pw"}
    return {field: username, "password": "pw"}
