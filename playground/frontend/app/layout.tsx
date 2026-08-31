import type { Metadata } from "next";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "django-cleanup playground",
  description: "Phase 7 playground — docs/APP-DESIGN.md §11.2",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: "2rem" }}>
        <Providers>
          <nav style={{ marginBottom: "1.5rem", display: "flex", gap: "1rem" }}>
            <a href="/">Cleanup review</a>
            <a href="/admin/cleanup_app/orphanfile/">Jazzmin admin</a>
          </nav>
          {children}
        </Providers>
      </body>
    </html>
  );
}
