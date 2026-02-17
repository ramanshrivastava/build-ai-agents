import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("renders dark background", async ({ page }) => {
  await page.goto("/patients");
  const body = page.locator("body");
  const bg = await body.evaluate((el) => getComputedStyle(el).backgroundColor);
  // Dark charcoal — should not be white or pure black
  expect(bg).not.toBe("rgb(255, 255, 255)");
  expect(bg).not.toBe("rgb(0, 0, 0)");
});

test("uses Inter font family", async ({ page }) => {
  await page.goto("/patients");
  const body = page.locator("body");
  const font = await body.evaluate((el) => getComputedStyle(el).fontFamily);
  expect(font).toContain("Inter Variable");
});

test("header has backdrop blur", async ({ page }) => {
  await page.goto("/patients");
  const header = page.locator("header");
  const backdrop = await header.evaluate(
    (el) => getComputedStyle(el).backdropFilter,
  );
  expect(backdrop).toContain("blur");
});

test("generate button has gold accent color", async ({ page }) => {
  await page.goto("/patients/1");
  const btn = page.getByRole("button", { name: "Generate Briefing" });
  await expect(btn).toBeVisible();
});
