"""Tests for ``cleanup_app.admin_views``/``urls_admin`` — ``docs/CONTRACT.md`` §4's six
admin-only endpoints. First ``APIClient`` tests in this repo.

Two things every endpoint must prove, per ``APP-DESIGN.md`` §7.4: nothing is reachable without
``IsAppAdmin`` (the IDOR-equivalent here — "an authenticated non-admin can reach nothing"), and
every delete-capable path goes through ``CleanupService`` honouring all four safety rails. The
rails themselves are proven in ``test_services.py``; here the point is that ``OrphanDeleteView``
never bypasses ``CleanupService`` to touch storage directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest
from appkit.testing import appkit_assert_error_envelope
from django.core.files.storage import Storage
from django.urls import reverse
from rest_framework.test import APIClient

from cleanup_app.admin_views import OrphanScanPagination
from cleanup_app.factories import CleanupRunFactory, CleanupRunFileFactory
from cleanup_app.models import CleanupRun
from cleanup_app.services import OrphanScanner

pytestmark = pytest.mark.django_db

# (method, url name, url kwargs) for all six routes — permission checks run in dispatch(),
# before any request body or object lookup, so a placeholder pk and an empty body are enough to
# prove neither the anonymous nor the authenticated-non-staff case ever reaches view logic.
_ENDPOINTS: list[tuple[str, str, dict[str, int]]] = [
    ("get", "cleanup-orphan-list", {}),
    ("post", "cleanup-orphan-delete", {}),
    ("get", "cleanup-run-list", {}),
    ("post", "cleanup-run-list", {}),
    ("get", "cleanup-run-detail", {"pk": 1}),
    ("get", "cleanup-summary", {}),
]


# --------------------------------------------------------------------------------- permissions


@pytest.mark.parametrize(("method", "url_name", "kwargs"), _ENDPOINTS)
def test_unauthenticated_request_is_rejected(
    appkit_api_client: APIClient, method: str, url_name: str, kwargs: dict[str, int]
) -> None:
    """DRF's default ``DEFAULT_AUTHENTICATION_CLASSES`` (``SessionAuthentication`` first,
    ``BasicAuthentication`` second — no override in test settings, matching a bare host) means
    an anonymous request against a permission-denied view surfaces as 403, not 401:
    ``APIView.handle_exception`` only keeps a ``NotAuthenticated`` at 401 when
    ``get_authenticate_header()`` returns a non-empty ``WWW-Authenticate`` value, and
    ``SessionAuthentication`` (checked first) deliberately returns none. The ``error.code``
    stays ``"not_authenticated"`` regardless — that's what actually distinguishes this case from
    authenticated-non-staff below, not the HTTP status."""
    response = getattr(appkit_api_client, method)(reverse(url_name, kwargs=kwargs), data={})
    appkit_assert_error_envelope(response, code="not_authenticated", status=403)


@pytest.mark.parametrize(("method", "url_name", "kwargs"), _ENDPOINTS)
def test_authenticated_non_staff_request_gets_403(
    appkit_auth_client: APIClient, method: str, url_name: str, kwargs: dict[str, int]
) -> None:
    response = getattr(appkit_auth_client, method)(reverse(url_name, kwargs=kwargs), data={})
    appkit_assert_error_envelope(response, code="permission_denied", status=403)


# --------------------------------------------------------------------------------- GET /orphans/


def test_orphan_list_returns_200_for_staff(
    appkit_admin_client: APIClient, media_storage: Storage, write_file: Callable[..., str]
) -> None:
    write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)

    response = appkit_admin_client.get(reverse("cleanup-orphan-list"))

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["file_path"] == "uploads/orphan.bin"
    assert "total_size" in response.data
    assert "files_scanned" in response.data
    assert "truncated" in response.data


def test_orphan_list_pagination_is_a_single_scan(
    appkit_admin_client: APIClient, media_storage: Storage, write_file: Callable[..., str]
) -> None:
    for i in range(30):
        write_file(media_storage, f"uploads/orphan-{i}.bin", age_seconds=10_000)

    with patch.object(OrphanScanner, "_run_scan", wraps=OrphanScanner._run_scan) as spy:
        first = appkit_admin_client.get(reverse("cleanup-orphan-list"), {"page": 1})
        second = appkit_admin_client.get(reverse("cleanup-orphan-list"), {"page": 2})

    assert first.status_code == 200
    assert second.status_code == 200
    assert spy.call_count == 1


def test_orphan_list_reports_truncation(
    appkit_admin_client: APIClient,
    media_storage: Storage,
    settings: Any,
    write_file: Callable[..., str],
) -> None:
    settings.CLEANUP = {**settings.CLEANUP, "MAX_FILES_PER_RUN": 2}
    for i in range(5):
        write_file(media_storage, f"uploads/orphan-{i}.bin", age_seconds=10_000)

    response = appkit_admin_client.get(reverse("cleanup-orphan-list"))

    assert response.status_code == 200
    assert response.data["truncated"] is True
    assert response.data["files_scanned"] == 5
    assert response.data["count"] == 2


def test_orphan_scan_pagination_schema_declares_extra_keys() -> None:
    pagination = OrphanScanPagination()

    schema = pagination.get_paginated_response_schema({"type": "object"})

    assert schema["properties"]["total_size"]["type"] == "integer"
    assert schema["properties"]["files_scanned"]["type"] == "integer"
    assert schema["properties"]["truncated"]["type"] == "boolean"


# ------------------------------------------------------------------------- POST /orphans/delete/


def test_orphan_delete_rejects_path_not_in_snapshot(
    appkit_admin_client: APIClient, media_storage: Storage
) -> None:
    response = appkit_admin_client.post(
        reverse("cleanup-orphan-delete"),
        {"file_paths": ["uploads/does-not-exist.bin"]},
        format="json",
    )

    appkit_assert_error_envelope(response, code="validation_error", status=400)


def test_orphan_delete_deletes_a_known_path_via_cleanup_service(
    appkit_admin_client: APIClient, media_storage: Storage, write_file: Callable[..., str]
) -> None:
    """Proves the delete rail end to end at the API boundary: a real orphan file, present in the
    current snapshot, is actually removed from storage — and the run this creates is exactly
    the ``CleanupService.run()`` code path (``services.CleanupService`` is the only place a file
    is ever removed or moved, per ``CLAUDE.md`` rule 3 — this view calls nothing else)."""
    write_file(media_storage, "uploads/orphan.bin", age_seconds=10_000)

    response = appkit_admin_client.post(
        reverse("cleanup-orphan-delete"), {"file_paths": ["uploads/orphan.bin"]}, format="json"
    )

    assert response.status_code == 202
    assert response.data["trigger"] == CleanupRun.Trigger.API
    assert response.data["status"] == CleanupRun.Status.SUCCESS
    assert not media_storage.exists("uploads/orphan.bin")


def test_orphan_delete_rejected_request_never_touches_storage(
    appkit_admin_client: APIClient, media_storage: Storage, write_file: Callable[..., str]
) -> None:
    """A path absent from the snapshot must 400 before ``CleanupService.run()`` is ever called —
    the file that IS a real, known orphan stays on disk, proving the rejection didn't fall
    through to a delete anyway."""
    write_file(media_storage, "uploads/real-orphan.bin", age_seconds=10_000)

    response = appkit_admin_client.post(
        reverse("cleanup-orphan-delete"),
        {"file_paths": ["uploads/real-orphan.bin", "uploads/not-a-real-path.bin"]},
        format="json",
    )

    appkit_assert_error_envelope(response, code="validation_error", status=400)
    assert media_storage.exists("uploads/real-orphan.bin")
    assert CleanupRun.objects.count() == 0


# ------------------------------------------------------------------------------------ GET /runs/


def test_run_list_returns_200_for_staff(appkit_admin_client: APIClient) -> None:
    CleanupRunFactory()

    response = appkit_admin_client.get(reverse("cleanup-run-list"))

    assert response.status_code == 200
    assert response.data["count"] == 1


def test_run_list_filters_by_status(appkit_admin_client: APIClient) -> None:
    CleanupRunFactory(status=CleanupRun.Status.SUCCESS)
    CleanupRunFactory(status=CleanupRun.Status.FAILED)

    response = appkit_admin_client.get(reverse("cleanup-run-list"), {"status": "failed"})

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["status"] == CleanupRun.Status.FAILED


def test_run_list_filters_by_trigger(appkit_admin_client: APIClient) -> None:
    CleanupRunFactory(trigger=CleanupRun.Trigger.MANUAL)
    CleanupRunFactory(trigger=CleanupRun.Trigger.API)

    response = appkit_admin_client.get(reverse("cleanup-run-list"), {"trigger": "api"})

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["trigger"] == CleanupRun.Trigger.API


@pytest.mark.parametrize("query", [{"status": "bogus"}, {"trigger": "bogus"}])
def test_run_list_rejects_unknown_filter_value(
    appkit_admin_client: APIClient, query: dict[str, str]
) -> None:
    response = appkit_admin_client.get(reverse("cleanup-run-list"), query)

    appkit_assert_error_envelope(response, code="validation_error", status=400)


# ----------------------------------------------------------------------------------- POST /runs/


def test_run_trigger_inline_returns_200_with_finished_run(
    appkit_admin_client: APIClient, media_storage: Storage
) -> None:
    response = appkit_admin_client.post(reverse("cleanup-run-list"), {"dry_run": False})

    assert response.status_code == 200
    assert response.data["trigger"] == CleanupRun.Trigger.API
    assert response.data["status"] in (
        CleanupRun.Status.SUCCESS,
        CleanupRun.Status.PARTIAL,
        CleanupRun.Status.FAILED,
    )


@pytest.mark.requires_extra
def test_run_trigger_enqueues_when_use_celery_and_celery_available(
    appkit_admin_client: APIClient, settings: Any
) -> None:
    settings.CLEANUP = {**getattr(settings, "CLEANUP", {}), "USE_CELERY": True}

    with patch("cleanup_app.admin_views.run_cleanup_run.delay") as mock_delay:
        response = appkit_admin_client.post(reverse("cleanup-run-list"), {})

    assert response.status_code == 202
    assert response.data["status"] == CleanupRun.Status.PENDING
    assert response.data["trigger"] == CleanupRun.Trigger.API
    mock_delay.assert_called_once_with(response.data["id"])


def test_run_trigger_falls_back_inline_when_celery_is_unavailable(
    appkit_admin_client: APIClient, settings: Any, media_storage: Storage
) -> None:
    """``USE_CELERY=True`` but ``importlib.util.find_spec("celery")`` returns ``None`` — must
    fall back to the synchronous path. Runs on the bare-install leg too (no ``requires_extra``
    marker) — that's exactly the case this proves."""
    settings.CLEANUP = {**getattr(settings, "CLEANUP", {}), "USE_CELERY": True}

    with patch("cleanup_app.admin_views.importlib.util.find_spec", return_value=None):
        response = appkit_admin_client.post(reverse("cleanup-run-list"), {})

    assert response.status_code == 200
    assert response.data["status"] != CleanupRun.Status.PENDING


# ------------------------------------------------------------------------------ GET /runs/{id}/


def test_run_detail_returns_run_with_its_files(appkit_admin_client: APIClient) -> None:
    run = CleanupRunFactory()
    CleanupRunFileFactory.create_batch(3, run=run)

    response = appkit_admin_client.get(reverse("cleanup-run-detail", kwargs={"pk": run.pk}))

    assert response.status_code == 200
    assert response.data["id"] == run.pk
    assert len(response.data["files"]) == 3


def test_run_detail_has_no_n_plus_one(
    appkit_admin_client: APIClient, django_assert_num_queries: Any
) -> None:
    run = CleanupRunFactory()
    CleanupRunFileFactory.create_batch(8, run=run)

    with django_assert_num_queries(6, exact=False):
        response = appkit_admin_client.get(reverse("cleanup-run-detail", kwargs={"pk": run.pk}))

    assert response.status_code == 200
    assert len(response.data["files"]) == 8


def test_run_detail_returns_404_for_unknown_id(appkit_admin_client: APIClient) -> None:
    response = appkit_admin_client.get(reverse("cleanup-run-detail", kwargs={"pk": 999_999}))

    appkit_assert_error_envelope(response, code="not_found", status=404)


# --------------------------------------------------------------------------------- GET /summary/


def test_summary_on_empty_db(appkit_admin_client: APIClient) -> None:
    response = appkit_admin_client.get(reverse("cleanup-summary"))

    assert response.status_code == 200
    assert response.data == {
        "total_runs": 0,
        "files_deleted_total": 0,
        "bytes_freed_total": 0,
        "last_run_at": None,
        "last_run_status": None,
    }


def test_summary_aggregates_match_fixture_rows(appkit_admin_client: APIClient) -> None:
    CleanupRunFactory(files_deleted=3, bytes_freed=100, status=CleanupRun.Status.SUCCESS)
    latest = CleanupRunFactory(files_deleted=2, bytes_freed=50, status=CleanupRun.Status.PARTIAL)

    response = appkit_admin_client.get(reverse("cleanup-summary"))

    assert response.status_code == 200
    assert response.data["total_runs"] == 2
    assert response.data["files_deleted_total"] == 5
    assert response.data["bytes_freed_total"] == 150
    assert response.data["last_run_status"] == latest.status


# ---------------------------------------------------------------------------------- throttling


def test_all_six_throttle_scopes_are_registered(settings: Any) -> None:
    """Covers what ``appkit.W004`` structurally can't: ``CleanupRunListCreateView`` swaps its
    ``throttle_scope`` at request time for POST (``cleanup_runs_trigger``), which W004's own
    docstring admits it can't see on a class-attribute walk of ``ROOT_URLCONF``."""
    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    for scope in (
        "cleanup_orphans_list",
        "cleanup_orphans_delete",
        "cleanup_runs_list",
        "cleanup_runs_trigger",
        "cleanup_runs_retrieve",
        "cleanup_summary",
    ):
        assert scope in rates


def test_summary_endpoint_throttles_past_its_rate(appkit_admin_client: APIClient) -> None:
    """``ScopedRateThrottle.THROTTLE_RATES`` is bound to ``api_settings.DEFAULT_THROTTLE_RATES``
    once, at ``rest_framework.throttling`` import time — overriding
    ``settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`` at test runtime never reaches it
    (DRF's own ``reload_api_settings`` only busts ``api_settings``'s cache, not this already-bound
    class attribute), so the rate has to be patched directly to actually engage a real 429 here."""
    from rest_framework.throttling import ScopedRateThrottle

    with patch.object(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "cleanup_summary": "1/min"},
    ):
        first = appkit_admin_client.get(reverse("cleanup-summary"))
        second = appkit_admin_client.get(reverse("cleanup-summary"))

    assert first.status_code == 200
    assert second.status_code == 429
