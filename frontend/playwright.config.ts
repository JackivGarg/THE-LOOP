import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  timeout: 45_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: "http://127.0.0.1:5180",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command:
        "python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000",
      cwd: "..",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !process.env.CI,
      env: {
        LOOP_DATABASE_PATH: "test-results/e2e.sqlite3",
        LOOP_ENABLE_DEMO: "true",
      },
    },
    {
      command: "npm run dev -- --port 5180 --strictPort",
      url: "http://127.0.0.1:5180",
      reuseExistingServer: !process.env.CI,
    },
  ],
});
