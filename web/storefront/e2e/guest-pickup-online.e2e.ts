import { expect, test } from "@playwright/test";
import { addProductToCart, PHONE } from "./helpers";

test("guest checks out for pickup and is sent to the Paystack payment page", async ({ page }) => {
  await addProductToCart(page);
  await page.goto("/checkout");

  await page.getByLabel("Your name").fill("Test Guest");
  await page.getByLabel("Phone number").fill(PHONE);
  await expect(page.getByText("Pickup: free")).toBeVisible();
  await page.getByLabel("Email address").fill("guest@example.com");

  await Promise.all([
    page.waitForURL(/paystack\.com/, { timeout: 30_000 }),
    page.getByRole("button", { name: "Continue" }).click(),
  ]);
});
