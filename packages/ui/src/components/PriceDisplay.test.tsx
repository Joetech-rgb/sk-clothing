import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PriceDisplay } from "./PriceDisplay";

describe("PriceDisplay", () => {
  it("shows integer pesewas as GHS", () => {
    render(<PriceDisplay pesewas={1234} />);
    expect(screen.getByText("GHS 12.34")).toBeTruthy();
  });

  it("shows zero as GHS 0.00", () => {
    render(<PriceDisplay pesewas={0} />);
    expect(screen.getByText("GHS 0.00")).toBeTruthy();
  });

  it("shows an optional label from the server", () => {
    render(<PriceDisplay pesewas={5000} label="Wholesale" />);
    expect(screen.getByText("Wholesale")).toBeTruthy();
    expect(screen.getByText("GHS 50.00")).toBeTruthy();
  });
});
