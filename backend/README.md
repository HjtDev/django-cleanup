# django-cleanup

## Installation — frontend

```bash
npm install @hjtdev/appkit               # if not already installed
npm install @hjtdev/django-cleanup
```

## Usage — add this app's basePath to the shared provider, then import hooks from the package root

**basePath key: `cleanup`** — add it to the `basePaths` map on the `ApiClientProvider` every
installed app shares (one provider for the whole host, mounted once):

```tsx
// frontend/app/providers.tsx — one-time wiring per host, one basePaths entry per app
import { ApiClientProvider } from "@hjtdev/appkit";
import { apiClient } from "@/lib/api-client";

<ApiClientProvider
  client={apiClient}
  basePaths={{
    // ...entries for already-installed apps stay here
    cleanup: "/api/v1/cleanup",
  }}
>
  {children}
</ApiClientProvider>;
```

```tsx
import { useOrphanFiles, useDeleteOrphanFiles, useCleanupRuns, useTriggerCleanup } from "@hjtdev/django-cleanup";

function OrphanReviewPanel() {
  const { data: orphans } = useOrphanFiles();
  const { mutate: deleteOrphans } = useDeleteOrphanFiles();
  const { data: runs } = useCleanupRuns();
  const { mutate: triggerCleanup } = useTriggerCleanup();
  // ...
}
```

Requires the host's `@tanstack/react-query` `QueryClientProvider` to already be mounted and
`appkit`'s `ApiClientProvider` mounted above wherever these hooks are used, with the `cleanup`
key above present in its `basePaths` map. No further frontend configuration needed.

Every endpoint behind these hooks is admin-only (`appkit.permissions.IsAppAdmin`) — a
non-staff user's request 403s at the API regardless of what the frontend renders.
