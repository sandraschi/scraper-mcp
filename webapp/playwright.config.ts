import { defineConfig } from '@playwright/test';

export default defineConfig({
    testDir: './e2e',
    timeout: 60000,
    retries: 1,
    use: {
        baseURL: 'http://localhost:10999',
        headless: true,
        screenshot: 'only-on-failure',
    },
    webServer: {
        command: 'uv run python -m scraper_mcp.server --http --port 10998',
        port: 10998,
        cwd: '../',
        timeout: 30000,
        reuseExistingServer: false,
    },
});
