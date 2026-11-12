import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Button } from "./Button";

describe("Button", () => {
  it("renders its label as a button", () => {
    render(<Button>Pay now</Button>);
    expect(screen.getByRole("button", { name: "Pay now" })).toBeTruthy();
  });

  it("defaults to type=button so it never submits a form by accident", () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole("button").getAttribute("type")).toBe("button");
  });

  it("allows type=submit when asked", () => {
    render(<Button type="submit">Send</Button>);
    expect(screen.getByRole("button").getAttribute("type")).toBe("submit");
  });

  it("can be disabled", () => {
    render(<Button disabled>Wait</Button>);
    expect(screen.getByRole("button").hasAttribute("disabled")).toBe(true);
  });

  it("fills the width when asked", () => {
    render(<Button fullWidth>Wide</Button>);
    expect(screen.getByRole("button").className).toContain("w-full");
  });

  it("keeps a tap target of at least 44px (min-h-11)", () => {
    render(<Button>Tap</Button>);
    expect(screen.getByRole("button").className).toContain("min-h-11");
  });
});
