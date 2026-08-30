"""Tests for ``cleanup_app.admin`` — both registrations are read-mostly (``docs/CONTRACT.md``
§1's models never get an add/change/delete surface from the admin, only from
``services.CleanupService``, per this phase's plan).
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.base_user import AbstractBaseUser
from django.test import Client
from django.urls import reverse

from cleanup_app.admin import CleanupRunAdmin, CleanupRunFileAdmin
from cleanup_app.factories import CleanupRunFactory, CleanupRunFileFactory
from cleanup_app.models import CleanupRun, CleanupRunFile

pytestmark = pytest.mark.django_db


def test_both_models_registered() -> None:
    assert isinstance(admin.site._registry[CleanupRun], CleanupRunAdmin)
    assert isinstance(admin.site._registry[CleanupRunFile], CleanupRunFileAdmin)


def test_cleanup_run_admin_list_display_and_filters() -> None:
    site_admin = admin.site._registry[CleanupRun]
    assert "status" in site_admin.list_display
    assert "trigger" in site_admin.list_display
    assert "files_deleted" in site_admin.list_display
    assert "bytes_freed" in site_admin.list_display
    assert "started_at" in site_admin.list_display
    assert set(site_admin.list_filter) == {"status", "trigger", "dry_run"}


def test_cleanup_run_file_admin_list_filter() -> None:
    site_admin = admin.site._registry[CleanupRunFile]
    assert set(site_admin.list_filter) == {"deleted", "quarantined"}


@pytest.mark.parametrize("model", [CleanupRun, CleanupRunFile])
def test_read_only_permissions(model: type[CleanupRun] | type[CleanupRunFile]) -> None:
    model_admin = admin.site._registry[model]

    assert model_admin.has_add_permission(request=None) is False  # type: ignore[arg-type]
    assert model_admin.has_change_permission(request=None) is False  # type: ignore[arg-type]
    assert model_admin.has_delete_permission(request=None) is False  # type: ignore[arg-type]


def test_run_changelist_renders_for_staff(
    client: Client, appkit_admin_user: AbstractBaseUser
) -> None:
    CleanupRunFactory()
    client.force_login(appkit_admin_user)

    response = client.get(reverse("admin:cleanup_app_cleanuprun_changelist"))

    assert response.status_code == 200


def test_run_changelist_denies_non_staff(client: Client, appkit_user: AbstractBaseUser) -> None:
    client.force_login(appkit_user)

    response = client.get(reverse("admin:cleanup_app_cleanuprun_changelist"))

    assert response.status_code in (302, 403)


def test_run_changelist_query_count_bounded(
    client: Client, appkit_admin_user: AbstractBaseUser, django_assert_num_queries
) -> None:
    """Proves get_queryset()'s select_related/annotate rather than asserting on internals: N
    runs, each with a couple of files, must not scale the query count with N (APP-DESIGN.md §2's
    N+1-avoidance baseline)."""
    for _ in range(5):
        run = CleanupRunFactory()
        CleanupRunFileFactory.create_batch(2, run=run)
    client.force_login(appkit_admin_user)
    url = reverse("admin:cleanup_app_cleanuprun_changelist")

    with django_assert_num_queries(15, exact=False):
        client.get(url)
