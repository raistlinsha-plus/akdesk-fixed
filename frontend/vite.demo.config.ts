import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";

const base = process.env.AKDESK_DEMO_BASE || "/akdesk-fixed/";
const media = [
  ["AKDesk-60秒导览.mp4", "akdesk-demo-60s.mp4", "video/mp4"],
  ["video-poster.png", "media/video-poster.png", "image/png"],
  ["demo-tour.zh-CN.vtt", "media/demo-tour.zh-CN.vtt", "text/vtt; charset=utf-8"],
] as const;

export default defineConfig({
  base,
  plugins: [
    react(),
    {
      name: "demo-pages-entry",
      enforce: "post",
      configureServer(server) {
        server.middlewares.use((request, response, next) => {
          const pathname = new URL(request.url || "/", "http://localhost").pathname;
          const match = media.find(([, fileName]) => pathname === `${base}${fileName}` || pathname === `/${fileName}`);
          if (!match) return next();
          response.setHeader("Content-Type", match[2]);
          response.end(readFileSync(new URL(`../docs/media/v1.1.0/${match[0]}`, import.meta.url)));
        });
      },
      generateBundle(_options, bundle) {
        const entry = bundle["demo.html"];
        if (entry?.type === "asset") {
          entry.fileName = "index.html";
          bundle["index.html"] = entry;
          delete bundle["demo.html"];
        }
        for (const [name, fileName] of media) {
          this.emitFile({ type: "asset", fileName, source: readFileSync(new URL(`../docs/media/v1.1.0/${name}`, import.meta.url)) });
        }
      },
    },
  ],
  server: { open: "/demo.html" },
  build: {
    outDir: "dist-demo",
    target: "es2022",
    chunkSizeWarningLimit: 550,
    rollupOptions: { input: "demo.html" },
  },
});
