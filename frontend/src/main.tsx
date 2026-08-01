import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { WatchlistProvider } from "./components/WatchlistContext";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppErrorBoundary>
      <WatchlistProvider>
        <App />
      </WatchlistProvider>
    </AppErrorBoundary>
  </StrictMode>,
);
