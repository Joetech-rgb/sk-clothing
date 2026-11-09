import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { QuantityInput } from "./QuantityInput";

function field() {
  return screen.getByLabelText("Quantity") as HTMLInputElement;
}

describe("QuantityInput", () => {
  it("shows the value", () => {
    render(<QuantityInput value={3} onChange={() => {}} />);
    expect(field().value).toBe("3");
  });

  it("steps up and down", () => {
    const onChange = vi.fn();
    render(<QuantityInput value={3} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Increase quantity" }));
    fireEvent.click(screen.getByRole("button", { name: "Decrease quantity" }));
    expect(onChange).toHaveBeenNthCalledWith(1, 4);
    expect(onChange).toHaveBeenNthCalledWith(2, 2);
  });

  it("cannot go below the minimum", () => {
    render(<QuantityInput value={1} onChange={() => {}} />);
    const down = screen.getByRole("button", { name: "Decrease quantity" }) as HTMLButtonElement;
    expect(down.disabled).toBe(true);
  });

  it("cannot go above a maximum the server gave", () => {
    render(<QuantityInput value={5} max={5} onChange={() => {}} />);
    const up = screen.getByRole("button", { name: "Increase quantity" }) as HTMLButtonElement;
    expect(up.disabled).toBe(true);
  });

  it("assumes no maximum when none is given", () => {
    render(<QuantityInput value={5000} onChange={() => {}} />);
    const up = screen.getByRole("button", { name: "Increase quantity" }) as HTMLButtonElement;
    expect(up.disabled).toBe(false);
  });

  it("accepts a typed whole number when the field loses focus", () => {
    const onChange = vi.fn();
    render(<QuantityInput value={3} onChange={onChange} />);
    fireEvent.change(field(), { target: { value: "12" } });
    fireEvent.blur(field());
    expect(onChange).toHaveBeenCalledWith(12);
  });

  it.each(["abc", "0", "2.5", "", "-3"])("ignores %j and restores the value", (typed) => {
    const onChange = vi.fn();
    render(<QuantityInput value={3} onChange={onChange} />);
    fireEvent.change(field(), { target: { value: typed } });
    fireEvent.blur(field());
    expect(onChange).not.toHaveBeenCalled();
    expect(field().value).toBe("3");
  });

  it("does not call onChange when the typed number is the current one", () => {
    const onChange = vi.fn();
    render(<QuantityInput value={3} onChange={onChange} />);
    fireEvent.change(field(), { target: { value: "3" } });
    fireEvent.blur(field());
    expect(onChange).not.toHaveBeenCalled();
  });
});
