/**
 * Checkout form state. Only collects what the customer types and checks that
 * required fields are filled in. It does not compute a fee, decide whether pay
 * on delivery is allowed, or judge a phone number: the server does all of that
 * and the UI shows what the server says.
 *
 * Shapes follow POST /api/v1/orders/ (station_name, latitude, longitude, address,
 * payment_method "online" | "cod") and payments/initialize (email).
 * The delivery method strings are PROVISIONAL until delivery/fees.py is checked.
 */

export type DeliveryMethod = "pickup" | "station" | "doorstep";
/** "cod" is pay on delivery, exactly as the server names it. */
export type PaymentChoice = "online" | "cod";

export interface CheckoutForm {
  name: string;
  phone: string;
  email: string;
  method: DeliveryMethod;
  /** A listed station's name, or one the customer typed. The server decides if it is listed. */
  stationName: string;
  /** True when the customer chose "my station is not listed" and types the name. */
  stationTyped: boolean;
  address: string;
  latitude: number | null;
  longitude: number | null;
  payment: PaymentChoice;
}

export const EMPTY_FORM: CheckoutForm = {
  name: "",
  phone: "",
  email: "",
  method: "pickup",
  stationName: "",
  stationTyped: false,
  address: "",
  latitude: null,
  longitude: null,
  payment: "online",
};

export type FormAction =
  | {
      type: "set_field";
      field: "name" | "phone" | "email" | "address" | "stationName";
      value: string;
    }
  | { type: "set_method"; method: DeliveryMethod }
  | { type: "set_station"; stationName: string }
  | { type: "set_station_typed"; typed: boolean }
  | { type: "set_location"; latitude: number; longitude: number }
  | { type: "set_payment"; payment: PaymentChoice };

export function formReducer(form: CheckoutForm, action: FormAction): CheckoutForm {
  switch (action.type) {
    case "set_field":
      return { ...form, [action.field]: action.value };
    case "set_method":
      return action.method === form.method ? form : { ...form, method: action.method };
    case "set_station":
      return { ...form, stationName: action.stationName, stationTyped: false };
    case "set_station_typed":
      return action.typed === form.stationTyped
        ? form
        : { ...form, stationTyped: action.typed, stationName: "" };
    case "set_location":
      return { ...form, latitude: action.latitude, longitude: action.longitude };
    case "set_payment":
      return { ...form, payment: action.payment };
  }
}

/** Pay on delivery only counts when the server allows it for this order. */
export function effectivePayment(form: CheckoutForm, codAllowed: boolean): PaymentChoice {
  return codAllowed ? form.payment : "online";
}

export type FieldName = "name" | "phone" | "email" | "station" | "address" | "location";

/** Plain-words messages for what is still empty. Presence only; the server judges the rest. */
export function missingFields(
  form: CheckoutForm,
  codAllowed: boolean,
): Partial<Record<FieldName, string>> {
  const errors: Partial<Record<FieldName, string>> = {};
  if (form.name.trim() === "") errors.name = "Enter your name.";
  if (form.phone.trim() === "") errors.phone = "Enter your phone number.";
  if (effectivePayment(form, codAllowed) === "online" && form.email.trim() === "") {
    errors.email = "Enter your email address.";
  }
  if (form.method === "station" && form.stationName.trim() === "") {
    errors.station = "Choose a station, or type the one you want.";
  }
  if (form.method === "doorstep") {
    if (form.address.trim() === "") errors.address = "Enter your delivery address.";
    if (form.latitude === null || form.longitude === null) {
      errors.location = "Pin your delivery location on the map.";
    }
  }
  return errors;
}

interface Common {
  name: string;
  phone: string;
  email: string;
  payment: PaymentChoice;
}

export type CheckoutValues =
  | ({ method: "pickup" } & Common)
  | ({ method: "station"; stationName: string } & Common)
  | ({ method: "doorstep"; address: string; latitude: number; longitude: number } & Common);

/** Trimmed values for the chosen method only. Call after missingFields found nothing. */
export function toValues(form: CheckoutForm, codAllowed: boolean): CheckoutValues {
  const base: Common = {
    name: form.name.trim(),
    phone: form.phone.trim(),
    email: form.email.trim(),
    payment: effectivePayment(form, codAllowed),
  };
  switch (form.method) {
    case "pickup":
      return { method: "pickup", ...base };
    case "station":
      return { method: "station", ...base, stationName: form.stationName.trim() };
    case "doorstep": {
      if (form.latitude === null || form.longitude === null) {
        throw new Error("A doorstep order needs a pinned location");
      }
      return {
        method: "doorstep",
        ...base,
        address: form.address.trim(),
        latitude: form.latitude,
        longitude: form.longitude,
      };
    }
  }
}
