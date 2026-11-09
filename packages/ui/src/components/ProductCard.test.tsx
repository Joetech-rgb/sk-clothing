import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProductCard } from "./ProductCard";

describe("ProductCard", () => {
  it("links the product name to its page", () => {
    render(<ProductCard name="Cotton tee" href="/products/cotton-tee" inStock />);
    expect(screen.getByRole("link", { name: "Cotton tee" }).getAttribute("href")).toBe(
      "/products/cotton-tee",
    );
  });

  it("shows the server's price text", () => {
    render(<ProductCard name="Tee" href="/p" priceFromDisplay="GHS 12.00" inStock />);
    expect(screen.getByText("GHS 12.00")).toBeTruthy();
    expect(screen.getByText(/From/)).toBeTruthy();
  });

  it("shows no price when the server sent none", () => {
    render(<ProductCard name="Tee" href="/p" priceFromDisplay={null} inStock />);
    expect(screen.queryByText(/From/)).toBeNull();
  });

  it("marks sold-out and wholesale products", () => {
    render(<ProductCard name="Tee" href="/p" inStock={false} hasWholesale />);
    expect(screen.getByText("Sold out")).toBeTruthy();
    expect(screen.getByText("Wholesale prices")).toBeTruthy();
  });

  it("shows no badges for a normal in-stock product", () => {
    render(<ProductCard name="Tee" href="/p" inStock />);
    expect(screen.queryByText("Sold out")).toBeNull();
    expect(screen.queryByText("Wholesale prices")).toBeNull();
  });

  it("lazy-loads its image and leaves the alt text empty when none is given", () => {
    const { container } = render(
      <ProductCard name="Tee" href="/p" imageUrl="/tee.webp" inStock />,
    );
    const image = container.querySelector("img");
    expect(image?.getAttribute("loading")).toBe("lazy");
    expect(image?.getAttribute("alt")).toBe("");
  });
});
