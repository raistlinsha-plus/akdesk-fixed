import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
  build: {
    target: "es2022",
    // ECharts is loaded on demand as its own chunk; 550 kB is the expected
    // uncompressed ceiling for that optional analytics dependency.
    chunkSizeWarningLimit: 550,
  },
});
