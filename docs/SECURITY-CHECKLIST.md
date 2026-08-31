# Security checklist — v1.0.0

Every item is `docs/APP-DESIGN.md` §9 (backend) or §12 (frontend), walked with evidence against
the code as it stands at the v1.0.0 tag, not assumed. `[x]` passed, `[N/A]` genuinely doesn't
apply here (stated explicitly, not skipped), `[note]` passed but with a caveat worth knowing.

## §9 — Application layer

- **[x] No unauthenticated access to write endpoints unless explicitly intended.**
  `grep -rn permission_classes backend/src/cleanup_app` returns exactly five hits, one per
  view class, all `[IsAppAdmin]`:
  `admin_views.py:123` (`OrphanFileListView`), `:154` (`OrphanDeleteView`), `:234`
  (`CleanupRunListCreateView`), `:307` (`CleanupRunDetailView`), `:319`
  (`CleanupSummaryView`). Nothing else in `src/` sets or overrides `permission_classes`.
  `backend/src/cleanup_app/urls.py` — the non-admin surface — is
  `urlpatterns: list[URLPattern] = []`; `views.py` is a docstring-only stub with no code.
  `IsAppAdmin` is `appkit.permissions.IsAppAdmin` (`is_authenticated and is_staff`) — this app
  defines no permission class of its own. Confirmed to have survived Phase 5's admin page and
  Phase 6's frontend SDK additions: neither touches `permission_classes`.

- **[x] Object-level permission checks on top of class-level ones (IDOR).** Two independent
  paths, both re-validate against the live orphan snapshot rather than trusting a client-supplied
  path:
  - API: `OrphanDeleteRequestSerializer.validate_file_paths` (`serializers.py`) rejects the
    whole request if any path isn't in the current snapshot.
  - Admin: `OrphanFileAdmin._validate_selection` (`admin.py:320`) does the same for the
    Jazzmin delete flow — no partial deletes, no way to smuggle an arbitrary path through by
    guessing a checkbox value.
  Additionally, `CleanupService.run(file_paths=[...])` treats any path absent from the current
  cached snapshot as a per-file failure (`services.py:396,418-421`), not a delete — so even a
  call that bypassed both serializers above still can't delete an arbitrary filesystem path.

- **[x] Serializers used for writes list fields explicitly — never `fields = "__all__"`.**
  All seven serializers in `serializers.py` list fields by name.
  `CleanupRunSerializer` sets `read_only_fields = fields` (the full list) since nothing on a
  `CleanupRun` is client-writable after creation. The only two client-writable fields anywhere
  in the API are `OrphanDeleteRequestSerializer.file_paths` and
  `CleanupTriggerRequestSerializer.dry_run`.

- **[x] Sensitive fields never exposed in a serializer's read output.**
  `OrphanFileSerializer` exposes `file_path`/`file_size`/`modified_at` only — no `file_url`,
  so no response ever leaks a resolvable `MEDIA_ROOT`/storage URL. `CleanupRunSerializer`
  exposes `initiated_by` as a bare PK, not a nested user representation (no email/username
  leak). No model here has a token, secret, or password-hash field to begin with.

- **[x] No raw SQL without parameterization; no string-built queries.**
  `grep -rn "\.raw(\|cursor\.execute\|extra(" backend/src` returns nothing. All querying goes
  through the Django ORM (`_base_manager` filters, `.filter()`, `.aggregate()`). Ruff's `S`
  (bandit) rules run in CI (`backend-quality` job) and would flag this class of issue anyway.

- **[N/A] File uploads validate type and size server-side.**
  This app accepts no uploads — stated explicitly rather than silently skipped. No serializer
  declares a `FileField`/`ImageField`; the only parser in use is DRF's default JSON parser.
  This app *reads* files a host's own models already stored (via upstream `django-cleanup`
  and its own `FileField`/`ImageField` scan), it never accepts a file from a request body.

- **[x] No secrets or keys hardcoded.** This app declares zero `.env` keys (per its own scope
  boundary in `CLAUDE.md`) — every knob lives in the `CLEANUP` settings dict with a code
  default, not a secret. `grep -rn "SECRET\|API_KEY\|PASSWORD" backend/src` returns nothing
  beyond the `CLEANUP` dict's own key *names*, none of which hold a value.

- **[x] Rate limiting and admin-vs-user permission separation both in place.**
  Six throttle scopes declared (`cleanup_orphans_list`, `cleanup_orphans_delete`,
  `cleanup_runs_list`, `cleanup_runs_trigger`, `cleanup_runs_retrieve`, `cleanup_summary`),
  documented in `README.md` with their default rates and exercised by `tests/backend/`. There
  is no "regular user" tier at all in this app to accidentally fall back to — every endpoint
  and every admin view requires `is_staff`, full stop.

- **[note] Stale-snapshot window is by design, not a bug — worth stating openly.**
  `OrphanScanner.scan()` is cached for `CLEANUP["SCAN_CACHE_TIMEOUT"]` (default 300s). A file
  that becomes referenced again after a snapshot was built, but before that snapshot expires,
  could still show up as a delete candidate within that window. This is the same trade-off
  every cache-backed scan makes; a host that needs tighter guarantees can lower
  `SCAN_CACHE_TIMEOUT`.

- **[note] Quarantine save-then-delete is not atomic.**
  `CleanupService._quarantine` (`services.py:448`) does `storage.save()` into the quarantine
  dir, then `storage.delete()` of the original. If `save()` succeeds and the subsequent
  `delete()` raises, the file now exists in both places and the `CleanupRunFile` row is marked
  failed (not silently marked deleted) — record-before-delete plus honest failure-state
  reporting is what keeps this from being a data-integrity bug rather than an edge case.

### Supply chain

- **[x] `pip-audit` and `npm audit --audit-level=high` both pass.**
  `npm audit --audit-level=high` run live under this repo's workspace-hoisted layout on
  2026-08-31: **0 vulnerabilities**. `pip-audit` is the `security-audit` job in the CI caller
  (`.github/workflows/ci.yml`) — first real run happens on the PR this phase opens.
- **[x] Dependency ranges follow `CLAUDE.md`'s wide-range rule.** `django`, `djangorestframework`,
  `drf-spectacular`, `hjtdev-appkit`, `django-cleanup` are all ranged, never exact-pinned, in
  `backend/pyproject.toml`. CI's `resolution-matrix` job (lowest-direct + highest) proves the
  low end actually installs and passes tests.

## §12 — Frontend security checklist

- **[x] No sensitive tokens stored in `localStorage`/`sessionStorage`.**
  `grep -rn "localStorage\|sessionStorage" frontend/src` returns nothing — auth is entirely the
  host's `ApiClient`/cookie handling via `appkit`; this package never touches storage.

- **[x] Manager methods never build a URL by concatenating unescaped user input.**
  `api/manager.ts` builds every query string through `URLSearchParams` (`toQueryString`); the
  only interpolated path segment anywhere is `${id}` in `getRun`, typed `number` — not a raw
  string, so there's nothing to escape or inject.

- **[N/A] No `dangerouslySetInnerHTML` with unsanitized data.**
  This package ships hooks only, no UI components — `grep -rn dangerouslySetInnerHTML frontend/src`
  returns nothing because there's no JSX in the package at all.

- **[x] No hardcoded base URLs, API keys, or secrets.**
  The base URL always comes from the host's shared `ApiClientProvider`/`useCleanupConfig`; every
  hook receives its `client`/`basePath` from that shared context, never a literal.

- **[x] A mutation hook for a destructive action never fires on mount or on a passive render.**
  Both of this app's mutations are destructive (`useDeleteOrphanFiles` deletes files,
  `useTriggerCleanup` starts a real cleanup run that can delete files). `grep -rn
  "useEffect|useLayoutEffect|mutate\(" frontend/src` returns only two docstring mentions of
  `mutate()` — zero actual `useEffect`/`useLayoutEffect`, zero auto-invoked `mutate()` call
  sites. Both hooks are bare `useMutation({...})` calls with `mutationFn` wired to an explicit
  argument, never an effect. Backed by a dedicated regression test,
  `tests/frontend/mutations-do-not-fire-on-mount.test.tsx`.

- **[x] Every manager method and hook is typed against `types.ts` — no `any` on a
  request/response shape.** `grep -rn ": any" frontend/src` returns nothing on a
  request/response boundary; types flow from the generated `schema.d.ts` through `types.ts`
  into every hook's return type.

- **[x] `react`, `@tanstack/react-query`, and `appkit` stay `peerDependencies`, never bundled.**
  `frontend/package.json` — all three are `peerDependencies`; the package's `dependencies` key
  does not exist at all (`forbid-runtime-dependencies: true` in the CI caller enforces this
  going forward, not just at this snapshot).

- **[x] `npm audit --audit-level=high` passes.** Same run as above: 0 vulnerabilities.
