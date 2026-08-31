import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { setupServer } from "msw/node";

// Mock the HTTP layer, never a live backend, and fail loudly on any request nobody set up a
// handler for rather than silently letting it through — mirrors ../appkit's own
// tests/frontend/setup.ts (docs/APP-DESIGN.md §7.7).
export const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
