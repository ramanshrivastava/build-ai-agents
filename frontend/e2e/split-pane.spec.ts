import { test, expect } from "@playwright/test";
import { mockApi, briefing } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/patients/1");
  await page.getByRole("button", { name: "Generate Briefing" }).click();
  await expect(page.getByText(briefing.summary.one_liner)).toBeVisible();
});

test("split pane renders two panels after briefing", async ({ page }) => {
  // Briefing panel (top) — has summary
  await expect(page.getByText(briefing.summary.one_liner)).toBeVisible();
  // Patient details panel (bottom) — has patient name
  await expect(page.getByRole("heading", { name: "Maria Garcia" })).toBeVisible();
});

test("resize handle is visible", async ({ page }) => {
  const grip = page.locator("svg.lucide-grip-horizontal");
  await expect(grip).toBeVisible();
});

test("both panels have independent scroll areas", async ({ page }) => {
  // Top panel and bottom panel should each have overflow-y-auto
  const scrollContainers = page.locator(".overflow-y-auto");
  const count = await scrollContainers.count();
  expect(count).toBeGreaterThanOrEqual(2);
});
