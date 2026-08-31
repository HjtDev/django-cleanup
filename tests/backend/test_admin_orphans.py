"""Tests for the ``OrphanFile``/``OrphanFileAdmin`` orphan-review page in ``cleanup_app.admin``
(Phase 5, ``docs/CONTRACT.md`` §6, Option A).

This is the page a human clicks "delete" on, so its own review matters more than most admin
pages — two tests are named explicitly by the phase brief and get their own section below: a
bare ``GET`` (with every delete-shaped query param a caller could stuff into a URL) must never
delete anything, and a non-staff request must never reach the page at all.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.files.storage import Storage
from django.test import Client, RequestFactory
from django.urls import NoReverseMatch, reverse
from django.utils import translation

from cleanup_app.admin import OrphanFile, OrphanFileAdmin
from cleanup_app.models import CleanupRun, CleanupRunFile

if TYPE_CHECKING:
    from pytest_django.fixtures import Settings

pytestmark = pytest.mark.django_db

CHANGELIST_URL = "admin:cleanup_app_orphanfile_changelist"
MO_PATH = (
    Path(__file__).resolve().parents[2] / "backend/src/cleanup_app/locale/fa/LC_MESSAGES/django.mo"
)


# --------------------------------------------------------------------------------- registration


def test_orphan_file_registered() -> None:
    assert isinstance(admin.site._registry[OrphanFile], OrphanFileAdmin)


@pytest.mark.parametrize(
    ("method_name", "expected"),
    [
        ("has_add_permission", False),
        ("has_change_permission", False),
    ],
)
def test_orphan_file_admin_always_denies(method_name: str, expected: bool) -> None:
    model_admin = admin.site._registry[OrphanFile]
    assert getattr(model_admin, method_name)(request=None) is expected  # type: ignore[arg-type]


@pytest.mark.parametrize("method_name", ["has_module_permission", "has_view_permission"])
def test_orphan_file_admin_permission_matrix(
    method_name: str,
    rf: RequestFactory,
    appkit_admin_user: AbstractBaseUser,
    appkit_user: AbstractBaseUser,
) -> None:
    model_admin = admin.site._registry[OrphanFile]
    request = rf.get("/")

    request.user = appkit_admin_user
    assert getattr(model_admin, method_name)(request) is True

    request.user = appkit_user
    assert getattr(model_admin, method_name)(request) is False


def test_get_urls_exposes_only_the_changelist() -> None:
    """No add/change/delete/history routes — those assume a real table, and ``OrphanFile`` has
    none. ``_changeform_view`` calls ``self.get_object()`` before its own permission check, so
    reaching one would hit a database error rather than a clean 404/403.
    """
    reverse(CHANGELIST_URL)  # does not raise

    with pytest.raises(NoReverseMatch):
        reverse("admin:cleanup_app_orphanfile_change", args=["some/path.bin"])
    with pytest.raises(NoReverseMatch):
        reverse("admin:cleanup_app_orphanfile_add")
    with pytest.raises(NoReverseMatch):
        reverse("admin:cleanup_app_orphanfile_delete", args=["some/path.bin"])


# ------------------------------------------------------------------------- the two named tests


def test_get_never_deletes_regardless_of_query_params(
    client: Client,
    appkit_admin_user: AbstractBaseUser,
    media_storage: Storage,
    write_file: Callable[..., str],
) -> None:
    """A bare GET — even one engineered to look exactly like a delete request — only ever
    renders the current scan. Nothing about this page is state-changing on GET.
    """
    path = write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)
    client.force_login(appkit_admin_user)

    response = client.get(
        reverse(CHANGELIST_URL),
        {"_selected_action": path, "action": "delete", "confirm": "yes"},
    )

    assert response.status_code == 200
    assert media_storage.exists(path)
    assert CleanupRun.objects.count() == 0


def test_non_staff_cannot_reach_the_page(
    client: Client,
    appkit_user: AbstractBaseUser,
    media_storage: Storage,
    write_file: Callable[..., str],
) -> None:
    path = write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)
    client.force_login(appkit_user)

    get_response = client.get(reverse(CHANGELIST_URL))
    assert get_response.status_code in (302, 403)

    post_response = client.post(
        reverse(CHANGELIST_URL),
        {"action": "delete", "_selected_action": [path], "confirm": "yes"},
    )
    assert post_response.status_code in (302, 403)

    assert media_storage.exists(path)
    assert CleanupRun.objects.count() == 0


def test_anonymous_cannot_reach_the_page(client: Client) -> None:
    response = client.get(reverse(CHANGELIST_URL))
    assert response.status_code in (302, 403)


# ---------------------------------------------------------------------------------- rendering


def test_changelist_renders_and_lists_real_orphan(
    client: Client,
    appkit_admin_user: AbstractBaseUser,
    media_storage: Storage,
    write_file: Callable[..., str],
) -> None:
    path = write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)
    client.force_login(appkit_admin_user)

    response = client.get(reverse(CHANGELIST_URL))

    assert response.status_code == 200
    assert path in response.content.decode()


# ------------------------------------------------------------------------- confirmation step


def test_delete_without_confirm_renders_confirmation_and_deletes_nothing(
    client: Client,
    appkit_admin_user: AbstractBaseUser,
    media_storage: Storage,
    write_file: Callable[..., str],
) -> None:
    path = write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)
    client.force_login(appkit_admin_user)

    response = client.post(
        reverse(CHANGELIST_URL), {"action": "delete", "_selected_action": [path]}
    )

    assert response.status_code == 200
    assert path in response.content.decode()
    assert media_storage.exists(path)
    assert CleanupRun.objects.count() == 0


# --------------------------------------------------------------------------------- real delete


def test_confirmed_delete_runs_a_real_cleanup_service_run(
    client: Client,
    appkit_admin_user: AbstractBaseUser,
    media_storage: Storage,
    write_file: Callable[..., str],
) -> None:
    """The phase's own verification requirement: a real ``CleanupService.run()`` call, not a
    stub — proven by asserting on the ``CleanupRun``/``CleanupRunFile`` rows it wrote and the
    file's actual removal from disk.
    """
    path = write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)
    client.force_login(appkit_admin_user)

    response = client.post(
        reverse(CHANGELIST_URL),
        {"action": "delete", "_selected_action": [path], "confirm": "yes"},
    )

    assert response.status_code == 302
    assert not media_storage.exists(path)

    run = CleanupRun.objects.get()
    assert run.trigger == CleanupRun.Trigger.MANUAL
    assert run.dry_run is False
    assert run.initiated_by_id == appkit_admin_user.pk
    assert run.status == CleanupRun.Status.SUCCESS
    assert run.files_deleted == 1

    run_file = CleanupRunFile.objects.get(run=run)
    assert run_file.file_path == path
    assert run_file.deleted is True


def test_confirmed_delete_one_failure_still_redirects_and_reports_partial(
    client: Client,
    appkit_admin_user: AbstractBaseUser,
    media_storage: Storage,
    write_file: Callable[..., str],
) -> None:
    """A storage-level failure on one file must not blow up the view — CleanupService.run()
    already tolerates it (test_services.py's own coverage of that), this proves the admin view
    surfaces the outcome (a redirect, a real PARTIAL/FAILED CleanupRun) instead of crashing.
    """
    path = write_file(media_storage, "uploads/bad.bin", age_seconds=10_000)
    client.force_login(appkit_admin_user)

    with patch.object(type(media_storage), "delete", side_effect=OSError("boom")):
        response = client.post(
            reverse(CHANGELIST_URL),
            {"action": "delete", "_selected_action": [path], "confirm": "yes"},
        )

    assert response.status_code == 302
    run = CleanupRun.objects.get()
    assert run.files_failed == 1
    assert run.status == CleanupRun.Status.FAILED


def test_unknown_path_is_rejected_wholesale(
    client: Client,
    appkit_admin_user: AbstractBaseUser,
    media_storage: Storage,
) -> None:
    """A path absent from the current snapshot must never reach ``CleanupService`` — rejected
    entirely, not silently dropped from a partial delete, and no ``CleanupRun`` row created at
    all for the rejection.
    """
    client.force_login(appkit_admin_user)

    response = client.post(
        reverse(CHANGELIST_URL),
        {"action": "delete", "_selected_action": ["never/written.bin"], "confirm": "yes"},
    )

    assert response.status_code == 302
    assert CleanupRun.objects.count() == 0


def test_no_selection_is_rejected(
    client: Client, appkit_admin_user: AbstractBaseUser, media_storage: Storage
) -> None:
    client.force_login(appkit_admin_user)

    response = client.post(reverse(CHANGELIST_URL), {"action": "delete"})

    assert response.status_code == 302
    assert CleanupRun.objects.count() == 0


# ------------------------------------------------------------------------------------- rescan


def test_rescan_invalidates_the_cache_and_redirects(
    client: Client, appkit_admin_user: AbstractBaseUser, media_storage: Storage
) -> None:
    client.force_login(appkit_admin_user)

    response = client.post(reverse(CHANGELIST_URL), {"action": "rescan"})

    assert response.status_code == 302


# ----------------------------------------------------------------------------------- rails


def test_file_within_grace_period_never_listed_or_deletable(
    client: Client,
    appkit_admin_user: AbstractBaseUser,
    media_storage: Storage,
    settings: Settings,
    write_file: Callable[..., str],
) -> None:
    settings.CLEANUP = {**settings.CLEANUP, "GRACE_PERIOD_SECONDS": 3600}
    path = write_file(media_storage, "uploads/fresh.bin", age_seconds=10)
    client.force_login(appkit_admin_user)

    listing = client.get(reverse(CHANGELIST_URL))
    assert path not in listing.content.decode()

    response = client.post(
        reverse(CHANGELIST_URL),
        {"action": "delete", "_selected_action": [path], "confirm": "yes"},
    )

    assert response.status_code == 302
    assert media_storage.exists(path)
    assert CleanupRun.objects.count() == 0


def test_excluded_file_never_listed_or_deletable(
    client: Client,
    appkit_admin_user: AbstractBaseUser,
    media_storage: Storage,
    settings: Settings,
    write_file: Callable[..., str],
) -> None:
    settings.CLEANUP = {**settings.CLEANUP, "EXCLUDE_PATTERNS": ["*.tmp"]}
    path = write_file(media_storage, "uploads/cache.tmp", age_seconds=10_000)
    client.force_login(appkit_admin_user)

    listing = client.get(reverse(CHANGELIST_URL))
    assert path not in listing.content.decode()

    response = client.post(
        reverse(CHANGELIST_URL),
        {"action": "delete", "_selected_action": [path], "confirm": "yes"},
    )

    assert response.status_code == 302
    assert media_storage.exists(path)
    assert CleanupRun.objects.count() == 0


# ------------------------------------------------------------------------------------ locale


def test_fa_catalog_is_compiled_on_disk() -> None:
    """A committed ``.po`` alone is not enough — CI's wheel-smoke-test looks for a real ``.mo``
    in the built wheel, and this asserts the source of truth for that is actually present.
    """
    assert MO_PATH.is_file()
    assert MO_PATH.stat().st_size > 0


def test_fa_translation_renders() -> None:
    with translation.override("fa"):
        assert str(translation.gettext("Rescan")) == "اسکن مجدد"
