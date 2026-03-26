// GraphSpy Playwright Test Suite
// Usage: npx playwright test test-pages.mjs
// Or: node test-pages.mjs

import { chromium } from 'playwright';

const GRAPHSPY = 'http://45.55.210.142:5000';
const CAMPAIGN = 'http://45.55.210.142:8080';
const SCREENSHOT_DIR = './test-screenshots';

async function test() {
    const browser = await chromium.launch({ headless: true });
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    let passed = 0, failed = 0;

    async function check(name, url, expects, screenshotName) {
        const page = await ctx.newPage();
        try {
            const resp = await page.goto(url, { waitUntil: 'load', timeout: 30000 });
            const status = resp?.status();
            await page.waitForTimeout(2000);
            const body = await page.content();

            let ok = status === 200 || status === 302;
            let issues = [];

            if (status !== 200 && status !== 302) issues.push(`HTTP ${status}`);

            for (const expect of expects) {
                if (!body.includes(expect)) {
                    issues.push(`Missing: "${expect}"`);
                    ok = false;
                }
            }

            if (screenshotName) {
                await page.screenshot({ path: `${SCREENSHOT_DIR}/${screenshotName}.png`, fullPage: false });
            }

            if (ok) {
                console.log(`  ✓ ${name}`);
                passed++;
            } else {
                console.log(`  ✗ ${name} — ${issues.join(', ')}`);
                if (screenshotName) {
                    await page.screenshot({ path: `${SCREENSHOT_DIR}/${screenshotName}-FAIL.png`, fullPage: true });
                }
                failed++;
            }
        } catch (e) {
            console.log(`  ✗ ${name} — ${e.message.split('\n')[0]}`);
            failed++;
        }
        await page.close();
    }

    console.log('\n=== GraphSpy Pages ===');
    await check('Home (Users Table)', `${GRAPHSPY}/`, ['Users', 'action-btn', 'list_users'], 'home');
    await check('Settings', `${GRAPHSPY}/settings`, ['Settings', 'Databases', 'User Agent'], 'settings');
    await check('Device Codes', `${GRAPHSPY}/device_codes`, ['Device Code', 'Generate'], 'device-codes');
    await check('Access Tokens', `${GRAPHSPY}/access_tokens`, ['Access Token'], 'access-tokens');
    await check('Refresh Tokens', `${GRAPHSPY}/refresh_tokens`, ['Refresh Token'], 'refresh-tokens');
    await check('Outlook Graph', `${GRAPHSPY}/outlook_graph`, ['Outlook', 'Reload'], 'outlook-graph');
    await check('Outlook Web', `${GRAPHSPY}/outlook`, ['Outlook Web', 'Refresh Token'], 'outlook-web');

    console.log('\n=== GraphSpy Sidebar ===');
    const homePage = await ctx.newPage();
    await homePage.goto(`${GRAPHSPY}/`, { waitUntil: 'load', timeout: 30000 });
    await homePage.waitForTimeout(2000);
    const sidebar = await homePage.content();
    const sidebarItems = ['Users', 'Device Codes', 'Phish Generator', 'Access Tokens', 'Refresh Tokens', 'Primary Refresh', 'WinHello', 'MFA', 'Teams', 'Entra', 'Settings', 'Logout'];
    for (const item of sidebarItems) {
        if (sidebar.includes(item)) { console.log(`  ✓ Sidebar: ${item}`); passed++; }
        else { console.log(`  ✗ Sidebar missing: ${item}`); failed++; }
    }
    await homePage.close();

    console.log('\n=== Campaign App Pages ===');
    await check('OWA Portal', `${CAMPAIGN}/owa?token=13`, ['Outlook', 'Loading'], 'owa');
    await check('OneDrive', `${CAMPAIGN}/drive?token=13`, ['OneDrive', 'Loading'], 'drive');
    await check('OneNote', `${CAMPAIGN}/onenote?token=13`, ['OneNote', 'Loading'], 'onenote');
    await check('Phish Page', `${CAMPAIGN}/phish`, ['Microsoft', 'verification'], 'phish');

    console.log('\n=== API Tests ===');
    await check('API: list_users', `${GRAPHSPY}/api/list_users`, ['email', 'access_token_id']);
    await check('API: list_access_tokens', `${GRAPHSPY}/api/list_access_tokens`, ['accesstoken']);
    await check('API: list_device_codes', `${GRAPHSPY}/api/list_device_codes`, []);

    console.log(`\n=== Results: ${passed} passed, ${failed} failed ===\n`);

    await browser.close();
    process.exit(failed > 0 ? 1 : 0);
}

// Create screenshot dir
import { mkdirSync } from 'fs';
try { mkdirSync(SCREENSHOT_DIR, { recursive: true }); } catch(e) {}

test().catch(e => { console.error(e); process.exit(1); });
