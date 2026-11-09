import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CartLineRow } from "./CartLineRow";

function renderRow(props: Partial<React.ComponentProps<typeof CartLineRow>> = {}) {
  const onQuantityChange = vi.fn();
  const onRemove = vi.fn();
  render(
    <ul>
      <CartLineRow
        name="Cotton tee"
        variantLabel="M · Red"
        quantity={2}
        onQuantityChange={onQuantityChange}
        onRemove={onRemove}
        {...props}
      />
    </ul>,
  );
  return { onQuantityChange, onRemove };
}

describe("CartLineRow", () => {
  it("shows the name, option and the server's prices", () => {
    renderRow({ unitPriceDisplay: "GHS 10.00", lineTotalDisplay: "GHS 20.00" });
    expect(screen.getByText("Cotton tee")).toBeTruthy();
    expect(screen.getByText("M · Red")).toBeTruthy();
    expect(screen.getByText("GHS 10.00")).toBeTruthy();
    expect(screen.getByText("GHS 20.00")).toBeTruthy();
  });

  it("says the price is being checked until the server answers", () => {
    renderRow();
    expect(screen.getByText("Checking price")).toBeTruthy();
  });

  it("changes the quantity", () => {
    const { onQuantityChange } = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Increase quantity" }));
    expect(onQuantityChange).toHaveBeenCalledWith(3);
  });

  it("removes the line, naming the product for screen readers", () => {
    const { onRemove } = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Remove Cotton tee" }));
    expect(onRemove).toHaveBeenCalledOnce();
  });
});
