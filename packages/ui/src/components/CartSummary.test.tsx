import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CartSummary } from "./CartSummary";

describe("CartSummary", () => {
  it("shows the server's subtotal", () => {
    render(<CartSummary subtotalDisplay="GHS 45.00" />);
    expect(screen.getByText("GHS 45.00")).toBeTruthy();
  });

  it("says prices are being checked until the server answers", () => {
    render(<CartSummary />);
    expect(screen.getByText("Checking prices")).toBeTruthy();
  });

  it("shows a note and an action when given", () => {
    render(<CartSummary subtotalDisplay="GHS 1.00" note="A note" action={<button>Checkout</button>} />);
    expect(screen.getByText("A note")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Checkout" })).toBeTruthy();
  });
});
