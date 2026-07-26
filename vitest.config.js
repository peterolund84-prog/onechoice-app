import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "happy-dom",
    include: ["web/**/*.test.js", "tests/frontend/**/*.test.js"],
    globals: false,
  },
});
