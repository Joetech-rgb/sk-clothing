import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { VariantPicker, variantLabel } from "./VariantPicker";

const variants = [
  { id: 1, size: "M", colour: "Red", inStock: true },
  { id: 2, size: "L", colour: "Red", inStock: false },
  { id: 3, size: "", colour: "", inStock: true },
];

describe("variantLabel", () => {
  it("joins size and colour", () => {
    expect(variantLabel({ size: "M", colour: "Red" })).toBe("M · Red");
  });
  it("uses whichever one exists", () => {
    expect(variantLabel({ size: "", colour: "Red" })).toBe("Red");
  });
  it("falls back to Standard", () => {
    expect(variantLabel({ size: "", colour: "" })).toBe("Standard");
  });
});

describe("VariantPicker", () => {
  it("selects an option", () => {
    const onSelect = vi.fn();
    render(<VariantPicker variants={variants} selectedId={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByLabelText("M · Red"));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it("marks the selected option", () => {
    render(<VariantPicker variants={variants} selectedId={1} onSelect={() => {}} />);
    expect((screen.getByLabelText("M · Red") as HTMLInputElement).checked).toBe(true);
  });

  it("disables options that are sold out and says so", () => {
    render(<VariantPicker variants={variants} selectedId={null} onSelect={() => {}} />);
    expect((screen.getByLabelText(/L · Red/) as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("(sold out)")).toBeTruthy();
  });

  it("groups the options under a legend", () => {
    render(<VariantPicker variants={variants} selectedId={null} onSelect={() => {}} legend="Pick one" />);
    expect(screen.getByRole("group", { name: "Pick one" })).toBeTruthy();
  });
});
