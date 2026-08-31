import path from "node:path";
import type { NextConfig } from "next";

// Backend base URL for server-side rewrites — talks to the Django container directly
// (CLEANUP_BACKEND_URL=http://backend:8000 in docker-compose.yml), defaulting to localhost for
// `npm run dev` against a backend reachable on the host.
const BACKEND_URL = process.env.CLEANUP_BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Next.js normalizes away trailing slashes with its OWN 308 redirect by default — proxied
  // through rewrites() below, that collides head-on with Django's CommonMiddleware
  // APPEND_SLASH, which redirects the other way (adds it back). skipTrailingSlashRedirect turns
  // off Next's own redirect for exactly this "the backend owns the URL shape" case.
  skipTrailingSlashRedirect: true,
  // Turbopack's `root` is a hard compilation boundary (its own error message: "files outside of
  // the workspace root are not compiled"). This repo's npm workspace root is the REPO ROOT
  // itself (package.json: "workspaces": ["frontend", "playground/frontend"]) — not
  // playground/frontend's own directory — since frontend/ (the SDK under test) is a sibling
  // workspace member, not a path dependency outside the workspace. See ../../CLAUDE.md /
  // docs/APP-DESIGN.md §11.2 and ../../../appkit/playground/frontend/next.config.ts's own
  // comment for the two wrong answers that were tried there before landing on "true common
  // ancestor of every workspace member".
  turbopack: {
    root: path.join(__dirname, "..", ".."),
  },
  // Every route this app's admin API and Django admin need is proxied same-origin
  // (localhost:3000) — decision 2 of the Phase 7 plan: every cleanup_app endpoint is
  // IsAppAdmin-gated, so the browser needs a real session cookie + CSRF cookie, which only
  // works cleanly same-origin with no CORS package and no credentials:"include" plumbing.
  async rewrites() {
    // `:path*` (a REPEATED param) tokenizes the URL into an array of non-empty segments before
    // reconstructing the destination — a trailing slash carries no segment of its own, so it is
    // silently dropped on every proxied request, independent of skipTrailingSlashRedirect and
    // trailingSlash (both tried first; neither affects this). Reproduced live: any Django URL
    // ending in "/" (every admin URL, every cleanup_app admin-API route) arrived at the backend
    // without it. Django's CommonMiddleware then either 301-redirects to re-add it (the plain
    // "/admin" case) or — worse, for a URL matched by admin's own catch_all_view, e.g.
    // "/admin/login" — the has_permission() wrapper for an unauthenticated request 302s to
    // "admin:login" with `next=<current path>`, which the browser follows back through this
    // SAME rewrite, which strips the slash again, forever: an infinite, ever-growing
    // ?next=...%3Fnext%3D... redirect loop, caught live (curl -v showed the query string
    // growing every hop) rather than by any unit test, since nothing in either half's own
    // suite runs a request through a Next.js rewrite. Fix: a single named param with an
    // explicit `(.*)`  regex, not a repeated `*` param — `(.*)` captures the remainder as ONE
    // raw string, trailing slash included, verbatim. See FINDINGS.md.
    return [
      { source: "/api/:path(.*)", destination: `${BACKEND_URL}/api/:path` },
      { source: "/admin/:path(.*)", destination: `${BACKEND_URL}/admin/:path` },
      { source: "/static/:path(.*)", destination: `${BACKEND_URL}/static/:path` },
      { source: "/media/:path(.*)", destination: `${BACKEND_URL}/media/:path` },
    ];
  },
};

export default nextConfig;
