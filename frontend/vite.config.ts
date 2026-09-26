import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local `npm run dev` talks to a backend on localhost; inside docker-compose,
// VITE_BACKEND_URL is set to http://backend:8000 (the service name on the
// compose network, since 127.0.0.1 inside the frontend container would mean
// the frontend container itself, not the backend one).
const backend = process.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // bind 0.0.0.0 so the dev server is reachable from outside a container
    proxy: { "/api": { target: backend, changeOrigin: true, ws: true } },
  },
  build: { chunkSizeWarningLimit: 900 },
});
