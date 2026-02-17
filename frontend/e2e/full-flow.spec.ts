import { test, expect } from "@playwright/test";
import { mockApi, briefing } from "./fixtures";

test("complete user journey: select, details, generate, briefing, expand flag, regenerate, switch", async ({
  page,
}) => {
  await mockApi(page);

  // 1. Start at patient list
  await page.goto("/patients");
  await expect(page.getByText("Select a patient to view their details")).toBeVisible();

  // 2. Select a patient
  await page.getByRole("button", { name: "Maria Garcia" }).click();
  await expect(page).toHaveURL(/\/patients\/1/);

  // 3. See patient details
  await expect(page.getByRole("heading", { name: "Maria Garcia" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Conditions" })).toBeVisible();
  await expect(page.getByText("Type 2 Diabetes")).toBeVisible();

  // 4. Click Generate Briefing
  await page.getByRole("button", { name: "Generate Briefing" }).click();

  // 5. Briefing loads — wait for summary to appear
  await expect(page.getByText(briefing.summary.one_liner)).toBeVisible();

  // 6. Flags visible (collapsed)
  await expect(page.getByText(briefing.flags[0].title)).toBeVisible();
  await expect(page.getByText(briefing.flags[0].description)).not.toBeVisible();

  // 7. Expand a flag
  const flagCard = page.getByRole("button", { name: new RegExp(briefing.flags[0].title) });
  await flagCard.click();
  await expect(page.getByText(briefing.flags[0].description)).toBeVisible();

  // 8. Regenerate
  await page.getByRole("button", { name: "Regenerate" }).click();
  // After regeneration, briefing should still be visible
  await expect(page.getByText(briefing.summary.one_liner)).toBeVisible();

  // 9. Switch patient
  await page.getByRole("button", { name: "James Wilson" }).click();
  await expect(page).toHaveURL(/\/patients\/2/);
  await expect(page.getByRole("heading", { name: "James Wilson" })).toBeVisible();
  // Briefing should be cleared
  await expect(page.getByRole("button", { name: "Generate Briefing" })).toBeVisible();
});
