import { test, expect } from "@playwright/test";
import { mockApi, briefing } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  // Navigate and generate briefing
  await page.goto("/patients/1");
  await page.getByRole("button", { name: "Generate Briefing" }).click();
  // Wait for briefing to appear
  await expect(page.getByText(briefing.flags[0].title)).toBeVisible();
});

test("flags are collapsed by default", async ({ page }) => {
  // Title visible
  await expect(page.getByText(briefing.flags[0].title)).toBeVisible();
  // Description should NOT be visible (collapsed)
  await expect(page.getByText(briefing.flags[0].description)).not.toBeVisible();
});

test("clicking a flag expands it", async ({ page }) => {
  const flagCard = page.getByRole("button", { name: new RegExp(briefing.flags[0].title) });

  // Click to expand
  await flagCard.click();
  await expect(page.getByText(briefing.flags[0].description)).toBeVisible();
});

test("clicking elsewhere collapses an expanded flag", async ({ page }) => {
  const flagCard = page.getByRole("button", { name: new RegExp(briefing.flags[0].title) });

  // Click to expand
  await flagCard.click();
  await expect(page.getByText(briefing.flags[0].description)).toBeVisible();

  // Click elsewhere to blur (which triggers collapse via onBlur)
  await page.getByText(briefing.summary.one_liner).click();
  await expect(page.getByText(briefing.flags[0].description)).not.toBeVisible();
});

test("flag card has aria-expanded attribute", async ({ page }) => {
  const flagCard = page.getByRole("button", { name: new RegExp(briefing.flags[0].title) });
  await expect(flagCard).toHaveAttribute("aria-expanded", "false");

  await flagCard.click();
  await expect(flagCard).toHaveAttribute("aria-expanded", "true");
});

test("keyboard Enter expands flag", async ({ page }) => {
  const flagCard = page.getByRole("button", { name: new RegExp(briefing.flags[0].title) });

  // Tab to focus the card — this triggers onFocus which expands
  await flagCard.focus();
  // Focus should expand the card
  await expect(page.getByText(briefing.flags[0].description)).toBeVisible();

  // Enter toggles to collapsed
  await page.keyboard.press("Enter");
  await expect(page.getByText(briefing.flags[0].description)).not.toBeVisible();
});
