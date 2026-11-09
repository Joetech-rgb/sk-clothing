import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PriceTierList } from "./PriceTierList";

describe("PriceTierList", () => {
  it("shows only the tiers it is given", () => {
    render(
      <PriceTierList
        tiers={[
          { tier: "retail", minQuantity: 1, priceDisplay: "GHS 10.00" },
          { tier: "wholesale", minQuantity: 10, priceDisplay: "GHS 8.00" },
        ]}
      />,
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("GHS 8.00")).toBeTruthy();
  });

  it("names the quantity for tiers above one", () => {
    render(<PriceTierList tiers={[{ tier: "wholesale", minQuantity: 10, priceDisplay: "GHS 8.00" }]} />);
    expect(screen.getByText("wholesale, 10 or more")).toBeTruthy();
  });

  it("does not repeat the quantity for the first tier", () => {
    render(<PriceTierList tiers={[{ tier: "retail", minQuantity: 1, priceDisplay: "GHS 10.00" }]} />);
    expect(screen.getByText("retail")).toBeTruthy();
  });

  it("renders nothing without tiers", () => {
    const { container } = render(<PriceTierList tiers={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
