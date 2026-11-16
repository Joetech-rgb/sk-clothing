import { expect, test } from "@playwright/test";
import { addProductToCart } from "./helpers";

test("add to cart, see the server's price, change the quantity, remove", async ({ page }) => {
  await addProductToCart(page);
  await expect(page.getByRole("link", { name: /^Cart \(1\)/ })).toBeVisible();

  await page.goto("/cart");
  await expect(page.getByRole("heading", { name: "Your cart" })).toBeVisible();
  await expect(page.getByText(/GHS [\d,]+\.\d{2}/).first()).toBeVisible();

  await page.getByRole("button", { name: "Increase quantity" }).click();
  await expect(page.getByLabel(/^Quantity for/)).toHaveValue("2");

  await page.getByRole("button", { name: /^Remove / }).click();
  await expect(page.getByText("Your cart is empty.")).toBeVisible();
});
