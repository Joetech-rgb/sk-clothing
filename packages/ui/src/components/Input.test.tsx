import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Input } from "./Input";

describe("Input", () => {
  it("links the label to the field", () => {
    render(<Input label="Phone number" />);
    expect(screen.getByLabelText("Phone number")).toBeTruthy();
  });

  it("uses a given id", () => {
    render(<Input label="Name" id="customer-name" />);
    expect(screen.getByLabelText("Name").id).toBe("customer-name");
  });

  it("shows the error in plain words and marks the field invalid", () => {
    render(<Input label="Phone number" error="Enter a Ghana number" />);
    const field = screen.getByLabelText("Phone number");
    expect(screen.getByText("Enter a Ghana number")).toBeTruthy();
    expect(field.getAttribute("aria-invalid")).toBe("true");
  });

  it("connects hint and error to the field for screen readers", () => {
    render(<Input label="Phone number" hint="Like 024 000 0000" error="Too short" />);
    const field = screen.getByLabelText("Phone number");
    const describedBy = (field.getAttribute("aria-describedby") ?? "").split(" ");
    expect(describedBy).toHaveLength(2);
    for (const id of describedBy) {
      expect(document.getElementById(id)).not.toBeNull();
    }
  });

  it("is not marked invalid when there is no error", () => {
    render(<Input label="Name" />);
    const field = screen.getByLabelText("Name");
    expect(field.getAttribute("aria-invalid")).toBeNull();
    expect(field.getAttribute("aria-describedby")).toBeNull();
  });
});
