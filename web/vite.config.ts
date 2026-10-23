import { defineConfig } from "vitest/config";

import { runtimeDependencies } from "./scripts/runtime-dependencies.mjs";

export default defineConfig({
  plugins: [runtimeDependencies()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    clearMocks: true,
  },
  build: { outDir: "../datakeel/web_dist", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
