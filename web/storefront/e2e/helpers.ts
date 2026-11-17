import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";

/** A phone number the backend accepts. Override with TEST_PHONE if staging rejects this one. */
export const PHONE = process.env.TEST_PHONE ?? "0240000000";

/** Opens a product, picks the first option that is in stock, and adds one to the cart. */
export async function addProductToCart(page: Page): Promise<void> {
  const slug = process.env.TEST_PRODUCT_SLUG;
  if (slug) {
    await page.goto(`/products/${slug}`);
  } else {
    await page.goto("/products");
    await page.getByRole("article").first().getByRole("link").first().click();
  }
  const option = page.locator('input[name="variant"]:not([disabled])').first();
  if ((await option.count()) > 0) {
    await option.check();
  }
  await page.getByRole("button", { name: "Add to cart" }).click();
  await expect(page.getByText("Added to your cart.")).toBeVisible();
}
