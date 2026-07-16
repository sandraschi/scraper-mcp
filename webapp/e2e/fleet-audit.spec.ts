import { test, expect } from '@playwright/test';

const BE = 'http://127.0.0.1:10998';

test.describe('Fleet Audit', () => {
    test('Backend health', async ({ request }) => {
        const resp = await request.get(BE + '/health');
        expect(resp.status()).toBe(200);
        const body = await resp.json();
        expect(body.ok).toBe(true);
    });

    test('Frontend loads', async ({ page }) => {
        await page.goto('/', { timeout: 15000 });
        await page.waitForTimeout(3000);
        await expect(page.locator('[data-testid="dashboard"]')).toBeAttached();
    });

    test('No console errors', async ({ page }) => {
        const errors: string[] = [];
        page.on('console', (msg) => {
            if (msg.type() === 'error') errors.push(msg.text());
        });
        await page.goto('/', { timeout: 15000 });
        await page.waitForTimeout(3000);
        expect(errors).toEqual([]);
    });

    test('Navigation links work', async ({ page }) => {
        await page.goto('/', { timeout: 15000 });
        await page.waitForTimeout(2000);
        // Navigate to platforms
        await page.goto('/platforms', { timeout: 10000 });
        await page.waitForTimeout(2000);
        await expect(page).toHaveURL(/\/platforms/);
    });
});
