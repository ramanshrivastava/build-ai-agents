import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LazyMotion, domMax } from "motion/react";
import "@fontsource-variable/inter/index.css";
import "./index.css";
import App from "./App.tsx";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <LazyMotion features={domMax} strict>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </LazyMotion>
  </StrictMode>,
);
