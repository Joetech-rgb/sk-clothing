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
  email: " ama@example.com ",
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

  it("choosing a listed station turns typing off", () => {
    const typing = { ...EMPTY_FORM, stationTyped: true, stationName: "Kasoa" };
    const next = formReducer(typing, { type: "set_station", stationName: "Madina" });
    expect(next).toMatchObject({ stationName: "Madina", stationTyped: false });
  });

  it("switching to a typed station clears the chosen name", () => {
    const chosen = { ...EMPTY_FORM, stationName: "Madina" };
    const next = formReducer(chosen, { type: "set_station_typed", typed: true });
    expect(next).toMatchObject({ stationName: "", stationTyped: true });
  });

  it("keeps the typed name when typing mode is already on", () => {
    const typing = { ...EMPTY_FORM, stationTyped: true, stationName: "Kasoa" };
    expect(formReducer(typing, { type: "set_station_typed", typed: true })).toBe(typing);
  });

  it("stores a pinned location", () => {
    const next = formReducer(EMPTY_FORM, { type: "set_location", latitude: 5.6, longitude: -0.18 });
    expect(next).toMatchObject({ latitude: 5.6, longitude: -0.18 });
  });
});

describe("effectivePayment", () => {
  const cod = { ...EMPTY_FORM, payment: "cod" as const };

  it("honours pay on delivery only when the server allows it", () => {
    expect(effectivePayment(cod, true)).toBe("cod");
    expect(effectivePayment(cod, false)).toBe("online");
  });
});

describe("missingFields", () => {
  it("asks for name, phone and email when paying online", () => {
    expect(Object.keys(missingFields(EMPTY_FORM, false)).sort()).toEqual([
      "email",
      "name",
      "phone",
    ]);
  });

  it("does not ask for an email when pay on delivery is chosen and allowed", () => {
    const cod = { ...EMPTY_FORM, payment: "cod" as const };
    expect(missingFields(cod, true).email).toBeUndefined();
  });

  it("still asks for an email when cod is chosen but the server does not allow it", () => {
    const cod = { ...EMPTY_FORM, payment: "cod" as const };
    expect(missingFields(cod, false).email).toBeDefined();
  });

  it("treats spaces-only as empty", () => {
    const errors = missingFields({ ...EMPTY_FORM, name: "   ", phone: " ", email: " " }, false);
    expect(errors.name).toBeDefined();
    expect(errors.phone).toBeDefined();
    expect(errors.email).toBeDefined();
  });

  it("needs a station name for station delivery, listed or typed", () => {
    const station = { ...filled, method: "station" as const };
    expect(missingFields(station, false).station).toBeDefined();
    expect(missingFields({ ...station, stationName: "Madina" }, false).station).toBeUndefined();
  });

  it("needs an address and a pinned location for doorstep delivery", () => {
    const door = { ...filled, method: "doorstep" as const };
    const none = missingFields(door, false);
    expect(none.address).toBeDefined();
    expect(none.location).toBeDefined();
    const done = missingFields(
      { ...door, address: "12 Palm St", latitude: 5.6, longitude: -0.18 },
      false,
    );
    expect(done).toEqual({});
  });

  it("asks for nothing extra when pickup is chosen", () => {
    expect(missingFields(filled, false)).toEqual({});
  });
});

describe("toValues", () => {
  it("trims and keeps only pickup fields for pickup", () => {
    const values = toValues({ ...filled, address: "ignored", stationName: "ignored" }, false);
    expect(values).toEqual({
      method: "pickup",
      name: "Ama",
      phone: "0240000000",
      email: "ama@example.com",
      payment: "online",
    });
  });

  it("keeps the trimmed station name for station delivery", () => {
    const values = toValues({ ...filled, method: "station", stationName: " Madina " }, false);
    expect(values).toMatchObject({ method: "station", stationName: "Madina" });
  });

  it("keeps address and coordinates for doorstep and applies the server's cod decision", () => {
    const form: CheckoutForm = {
      ...filled,
      method: "doorstep",
      address: " 12 Palm St ",
      latitude: 5.6,
      longitude: -0.18,
      payment: "cod",
    };
    expect(toValues(form, true)).toMatchObject({
      address: "12 Palm St",
      latitude: 5.6,
      longitude: -0.18,
      payment: "cod",
    });
    expect(toValues(form, false)).toMatchObject({ payment: "online" });
  });

  it("refuses a doorstep order without a pinned location", () => {
    const form: CheckoutForm = { ...filled, method: "doorstep", address: "12 Palm St" };
    expect(() => toValues(form, false)).toThrow();
  });
});
