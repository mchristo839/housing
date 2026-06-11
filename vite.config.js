import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Serve the /api serverless handlers during `npm run dev` so the paywall flow
// (preview + dev-unlock) is testable locally without `vercel dev`.
function apiDev() {
  return {
    name: "api-dev",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (!req.url || !req.url.startsWith("/api/")) return next();
        const name = req.url.split("?")[0].replace(/^\/api\//, "").replace(/\/$/, "");
        try {
          const mod = await server.ssrLoadModule(`/api/${name}.js`);
          await mod.default(req, res);
        } catch (e) {
          res.statusCode = 500;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ error: "dev_handler_error", detail: String(e && e.stack || e) }));
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), apiDev()],
});
