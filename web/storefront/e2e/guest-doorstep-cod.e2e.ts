import { expect, test } from "@playwright/test";
import { addProductToCart, PHONE } from "./helpers";

// Needs the Mapbox token on the site and delivery settings in the admin. Set E2E_MAP=1 to run.
test.skip(!process.env.E2E_MAP, "Set E2E_MAP=1 to run the map and pay-on-delivery test");

test("guest pins a doorstep address, pays on delivery, then tracks the order", async ({ page }) => {
  await addProductToCart(page);
  await page.goto("/checkout");

  await page.getByLabel("Your name").fill("Test Guest");
  await page.getByLabel("Phone number").fill(PHONE);
  await page.getByLabel("Deliver to my door").check();
  await page.getByLabel("Delivery address").fill("12 Test Street, Accra");

  await page.getByRole("application", { name: /Map/ }).click({ position: { x: 150, y: 120 } });
  await expect(page.getByText("Pin placed. Drag it to adjust.")).toBeVisible();

  // Offered only when the server says pay on delivery is allowed for this address.
  await page.getByLabel("Pay when it arrives").check();
  await page.getByRole("button", { name: "Continue" }).click();

  await page.waitForURL(/\/orders\/confirmation/);
  await expect(page.getByRole("heading", { name: "Thank you for your order" })).toBeVisible();
  const reference = (
    await page.getByText("Order reference").locator("xpath=following-sibling::p").innerText()
  ).trim();
  expect(reference).not.toBe("");

  await page.goto("/orders");
  await page.getByLabel("Order reference").fill(reference);
  await page.getByLabel("Phone number").fill(PHONE);
  await page.getByRole("button", { name: "Find my order" }).click();
  await expect(page.getByText(reference)).toBeVisible();
});
