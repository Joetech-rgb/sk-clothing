import { describe, expect, it } from "vitest";
import {
  addLine,
  clearCart,
  EMPTY_CART,
  removeLine,
  setQuantity,
  totalQuantity,
} from "./cart";
import type { Cart, CartLine } from "./cart";

const red: CartLine = { productSlug: "tee", variantId: "v-red", quantity: 2 };
const blue: CartLine = { productSlug: "tee", variantId: "v-blue", quantity: 3 };

describe("addLine", () => {
  it("adds a new line", () => {
    expect(addLine(EMPTY_CART, red)).toEqual([red]);
  });

  it("merges the same variant by adding quantities", () => {
    const cart = addLine(addLine(EMPTY_CART, red), { ...red, quantity: 5 });
    expect(cart).toEqual([{ ...red, quantity: 7 }]);
  });

  it("keeps different variants of one product as separate lines", () => {
    const cart = addLine(addLine(EMPTY_CART, red), blue);
    expect(cart).toHaveLength(2);
  });

  it.each([0, -1, 1.5, Number.NaN, Infinity])("rejects quantity %s", (quantity) => {
    expect(() => addLine(EMPTY_CART, { ...red, quantity })).toThrow(RangeError);
  });

  it("does not change the cart it was given", () => {
    const cart: Cart = Object.freeze([Object.freeze({ ...red })]);
    expect(() => addLine(cart, blue)).not.toThrow();
    expect(cart).toEqual([red]);
  });
});

describe("setQuantity", () => {
  it("sets a new quantity", () => {
    expect(setQuantity([red], "v-red", 9)).toEqual([{ ...red, quantity: 9 }]);
  });

  it("removes the line at zero", () => {
    expect(setQuantity([red, blue], "v-red", 0)).toEqual([blue]);
  });

  it("leaves the cart unchanged for an unknown variant", () => {
    const cart: Cart = [red];
    expect(setQuantity(cart, "nope", 4)).toBe(cart);
  });

  it.each([-1, 2.5, Number.NaN])("rejects quantity %s", (quantity) => {
    expect(() => setQuantity([red], "v-red", quantity)).toThrow(RangeError);
  });
});

describe("removeLine, clearCart and totalQuantity", () => {
  it("removes one line", () => {
    expect(removeLine([red, blue], "v-blue")).toEqual([red]);
  });

  it("clears the cart", () => {
    expect(clearCart()).toEqual([]);
  });

  it("counts items across lines", () => {
    expect(totalQuantity([red, blue])).toBe(5);
    expect(totalQuantity(EMPTY_CART)).toBe(0);
  });
});
