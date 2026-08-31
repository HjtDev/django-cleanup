"use client";

import { useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { ApiClientProvider } from "@hjtdev/appkit";
import { makeQueryClient } from "@/lib/query-client";
import { apiClient } from "@/lib/api-client";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => makeQueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <ApiClientProvider
        client={apiClient}
        basePaths={{
          cleanup: "/api/v1/cleanup",
        }}
      >
        {children}
      </ApiClientProvider>
    </QueryClientProvider>
  );
}
