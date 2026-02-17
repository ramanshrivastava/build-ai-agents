import { test, expect } from "@playwright/test";
import { mockApi } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("renders patient list", async ({ page }) => {
  await page.goto("/patients");
  await expect(page.getByRole("button", { name: "Maria Garcia" })).toBeVisible();
  await expect(page.getByRole("button", { name: "James Wilson" })).toBeVisible();
});

test("clicking a patient selects them and updates URL", async ({ page }) => {
  await page.goto("/patients");
  await page.getByRole("button", { name: "Maria Garcia" }).click();
  await expect(page).toHaveURL(/\/patients\/1/);
  await expect(page.getByRole("heading", { name: "Maria Garcia" })).toBeVisible();
});

test("switching patients updates the view", async ({ page }) => {
  await page.goto("/patients/1");
  await expect(page.getByRole("heading", { name: "Maria Garcia" })).toBeVisible();

  await page.getByRole("button", { name: "James Wilson" }).click();
  await expect(page).toHaveURL(/\/patients\/2/);
  await expect(page.getByRole("heading", { name: "James Wilson" })).toBeVisible();
});
