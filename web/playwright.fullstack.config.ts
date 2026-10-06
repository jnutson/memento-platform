import { defineConfig } from "@playwright/test";

const apiOrigin = "http://127.0.0.1:8100";
const webOrigin = "http://127.0.0.1:3100";

export default defineConfig({
  testDir: "./tests/fullstack",
  use: {
    baseURL: webOrigin,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "../.venv/bin/python ../tests/e2e/serve_attention_fixture.py --port 8100",
      url: `${apiOrigin}/healthz`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `env MEMENTO_API_ORIGIN=${apiOrigin} npm run dev -- --port 3100`,
      url: `${webOrigin}/signal`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
