import CleanupClient from "./CleanupClient";

// Server-component wrapper, deliberately NOT "use client": `export const dynamic` only takes
// effect from a server file. Without it, `next build`'s static-generation pass prerenders the
// client component in a worker with no <Providers> in scope, and every hook below throws
// "No QueryClient set" at BUILD time rather than at request time — the directive is silently
// ignored when placed directly inside a "use client" file. Found and documented the hard way in
// ../../../appkit/playground/frontend/app/page.tsx (FINDINGS.md §12.1); pre-empted here rather
// than rediscovered.
export const dynamic = "force-dynamic";

export default function HomePage() {
  return <CleanupClient />;
}
