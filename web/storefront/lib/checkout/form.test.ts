import { describe, expect, it } from "vitest";
import {
  EMPTY_FORM,
  effectivePayment,
  formReducer,
  missingFields,
  toValues,
} from "./form";
import type { CheckoutForm } from "./form";

const filled: CheckoutForm = {
  ...EMPTY_FORM,
  name: "  Ama  ",
  phone: " 0240000000 ",
};

describe("formReducer", () => {
  it("sets text fields", () => {
    const next = formReducer(EMPTY_FORM, { type: "set_field", field: "name", value: "Ama" });
    expect(next.name).toBe("Ama");
  });

  it("changes only the method when the method changes", () => {
    const withAddress = { ...EMPTY_FORM, address: "12 Palm St" };
    const next = formReducer(withAddress, { type: "set_method", method: "doorstep" });
    expect(next).toEqual({ ...withAddress, method: "doorstep" });
  });

  it("returns the same object when the method does not change", () => {
    expect(formReducer(EMPTY_FORM, { type: "set_method", method: "pickup" })).toBe(EMPTY_FORM);
  });

  it("choosing a listed station clears a typed one", () => {
    const typed = { ...EMPTY_FORM, method: "station" as const, customStation: "Kasoa" };
    const next = formReducer(typed, { type: "set_station", stationId: "st-1" });
    expect(next.stationId).toBe("st-1");
    expect(next.customStation).toBe("");
  });

  it("typing an unlisted station clears the chosen one", () => {
    const chosen = { ...EMPTY_FORM, method: "station" as const, stationId: "st-1" };
    const next = formReducer(chosen, { type: "set_field", field: "customStation", value: "Kasoa" });
    expect(next.stationId).toBe("");
    expect(next.customStation).toBe("Kasoa");
  });

  it("emptying the typed station keeps the chosen one", () => {
    const chosen = { ...EMPTY_FORM, method: "station" as const, stationId: "st-1" };
    const next = formReducer(chosen, { type: "set_field", field: "customStation", value: " " });
    expect(next.stationId).toBe("st-1");
  });
});

describe("effectivePayment", () => {
  const cod = { ...EMPTY_FORM, payment: "pay_on_delivery" as const };

  it("honours pay on delivery only when the server allows it", () => {
    expect(effectivePayment(cod, true)).toBe("pay_on_delivery");
    expect(effectivePayment(cod, false)).toBe("online");
  });
});

describe("missingFields", () => {
  it("asks for name and phone", () => {
    expect(Object.keys(missingFields(EMPTY_FORM)).sort()).toEqual(["name", "phone"]);
  });

  it("treats spaces-only as empty", () => {
    const errors = missingFields({ ...EMPTY_FORM, name: "   ", phone: " " });
    expect(errors.name).toBeDefined();
    expect(errors.phone).toBeDefined();
  });

  it("needs a station for station delivery, listed or typed", () => {
    const station = { ...filled, method: "station" as const };
    expect(missingFields(station).station).toBeDefined();
    expect(missingFields({ ...station, stationId: "st-1" }).station).toBeUndefined();
    expect(missingFields({ ...station, customStation: "Kasoa" }).station).toBeUndefined();
  });

  it("needs an address for doorstep delivery", () => {
    const door = { ...filled, method: "doorstep" as const };
    expect(missingFields(door).address).toBeDefined();
    expect(missingFields({ ...door, address: "12 Palm St" }).address).toBeUndefined();
  });

  it("does not ask for a station or address when pickup is chosen", () => {
    expect(missingFields(filled)).toEqual({});
  });
});

describe("toValues", () => {
  it("trims and keeps only pickup fields for pickup", () => {
    const values = toValues({ ...filled, address: "ignored", stationId: "st-9" }, false);
    expect(values).toEqual({
      method: "pickup",
      name: "Ama",
      phone: "0240000000",
      payment: "online",
    });
  });

  it("keeps the chosen station and drops the typed one", () => {
    const values = toValues(
      { ...filled, method: "station", stationId: "st-1", customStation: "Kasoa" },
      false,
    );
    expect(values).toMatchObject({ method: "station", stationId: "st-1", customStation: "" });
  });

  it("keeps a typed station when none is chosen", () => {
    const values = toValues({ ...filled, method: "station", customStation: " Kasoa " }, false);
    expect(values).toMatchObject({ stationId: "", customStation: "Kasoa" });
  });

  it("keeps the address for doorstep and applies the server's pay-on-delivery decision", () => {
    const form: CheckoutForm = {
      ...filled,
      method: "doorstep",
      address: " 12 Palm St ",
      payment: "pay_on_delivery",
    };
    expect(toValues(form, true)).toMatchObject({ address: "12 Palm St", payment: "pay_on_delivery" });
    expect(toValues(form, false)).toMatchObject({ payment: "online" });
  });
});
