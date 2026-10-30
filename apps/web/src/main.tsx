import "@mantine/core/styles.css";
import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ApiError } from "./api/errors";
import { AuthProvider } from "./features/auth/AuthContext";
import "./features/practice/monacoSetup";
import "./app.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Retry only what may succeed later: network errors and 5xx
      retry: (count, err) => count < 2 && (!(err instanceof ApiError) || err.status === null || err.status >= 500),
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MantineProvider
      theme={{
        primaryColor: "indigo",
        defaultRadius: "md",
        fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        headings: { fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontWeight: "700" },
        components: {
          Button: { defaultProps: { radius: "md" } },
          Paper: { defaultProps: { radius: "lg" } },
          TextInput: { defaultProps: { radius: "md" } },
          Textarea: { defaultProps: { radius: "md" } },
          Select: { defaultProps: { radius: "md" } },
        },
      }}
    >
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </QueryClientProvider>
    </MantineProvider>
  </StrictMode>,
);
