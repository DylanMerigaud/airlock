// Diagnostic only, not part of the shipped pipeline. Measures where the ASA scroll beat in
// record.mjs (scrollIntoViewIfNeeded on "Assessment", then 8s of window.scrollBy(0,16) every 90ms)
// actually ends up, against the real page, to check the "ASA scroll position" item flagged open
// in docs/RUNS.md draft 2.
import { chromium } from "playwright";

const ASA_URL = "https://www.asa.org.uk/rulings/nutri-paw-ltd.html";
const ASA_SCROLL_MS = 8_000;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.goto(ASA_URL, { waitUntil: "domcontentloaded", timeout: 90_000 });
for (const label of [/accept all/i, /accept/i, /agree/i]) {
  const button = page.getByRole("button", { name: label }).first();
  if (await button.count().catch(() => 0)) {
    await button.click({ timeout: 3_000 }).catch(() => {});
    break;
  }
}
await page.waitForTimeout(500);

const assessmentBox = await page.getByText(/assessment/i).first().boundingBox().catch(() => null);
console.log("assessment heading bbox:", assessmentBox);

await page.getByText(/assessment/i).first().scrollIntoViewIfNeeded({ timeout: 10_000 }).catch(() => {});
const afterIntoView = await page.evaluate(() => window.scrollY);
console.log("scrollY right after scrollIntoViewIfNeeded:", afterIntoView);

const docHeight = await page.evaluate(() => document.documentElement.scrollHeight);
console.log("document scrollHeight:", docHeight);

const scrollUntil = Date.now() + ASA_SCROLL_MS;
let steps = 0;
while (Date.now() < scrollUntil) {
  await page.evaluate(() => window.scrollBy(0, 16));
  steps++;
  await new Promise((r) => setTimeout(r, 90));
}
const afterScroll = await page.evaluate(() => window.scrollY);
console.log("steps:", steps, "total scrollBy px:", steps * 16, "final scrollY:", afterScroll);

// What text is visible in the viewport at the end of the beat?
const visibleText = await page.evaluate(() => {
  const vh = window.innerHeight;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = [];
  let n;
  while ((n = walker.nextNode())) {
    const t = n.textContent.trim();
    if (!t) continue;
    const r = n.parentElement?.getBoundingClientRect();
    if (!r) continue;
    if (r.top >= 0 && r.top < vh) seen.push(t.slice(0, 80));
  }
  return seen.slice(0, 25);
});
console.log("visible text lines at end of beat:\n", visibleText.join("\n"));

await browser.close();
