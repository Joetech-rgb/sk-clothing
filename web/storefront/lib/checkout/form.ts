/**
 * Checkout form state. Only collects what the customer types and checks that
 * required fields are filled in. It does not compute a fee, decide whether pay
 * on delivery is allowed, or judge a phone number: the server does all of that
 * and the UI shows what the server says.
 */

export type DeliveryMethod = "pickup" | "station" | "doorstep";
export type PaymentChoice = "online" | "pay_on_delivery";

export interface CheckoutForm {
  name: string;
  phone: string;
  method: DeliveryMethod;
  stationId: string;
  customStation: string;
  address: string;
  payment: PaymentChoice;
}

export const EMPTY_FORM: CheckoutForm = {
  name: "",
  phone: "",
  method: "pickup",
  stationId: "",
  customStation: "",
  address: "",
  payment: "online",
};

export type FormAction =
  | { type: "set_field"; field: "name" | "phone" | "address" | "customStation"; value: string }
  | { type: "set_method"; method: DeliveryMethod }
  | { type: "set_station"; stationId: string }
  | { type: "set_payment"; payment: PaymentChoice };

export function formReducer(form: CheckoutForm, action: FormAction): CheckoutForm {
  switch (action.type) {
    case "set_field":
      if (action.field === "customStation") {
        // Typing an unlisted station replaces any chosen station.
        return {
          ...form,
          customStation: action.value,
          stationId: action.value.trim() === "" ? form.stationId : "",
        };
      }
      return { ...form, [action.field]: action.value };
    case "set_method":
      return action.method === form.method ? form : { ...form, method: action.method };
    case "set_station":
      return {
        ...form,
        stationId: action.stationId,
        customStation: action.stationId === "" ? form.customStation : "",
      };
    case "set_payment":
      return { ...form, payment: action.payment };
  }
}

/** Pay on delivery only counts when the server allows it for this order. */
export function effectivePayment(form: CheckoutForm, payOnDeliveryAllowed: boolean): PaymentChoice {
  return payOnDeliveryAllowed ? form.payment : "online";
}

export type FieldName = "name" | "phone" | "station" | "address";

/** Plain-words messages for fields that are still empty. Presence only. */
export function missingFields(form: CheckoutForm): Partial<Record<FieldName, string>> {
  const errors: Partial<Record<FieldName, string>> = {};
  if (form.name.trim() === "") errors.name = "Enter your name.";
  if (form.phone.trim() === "") errors.phone = "Enter your phone number.";
  if (form.method === "station" && form.stationId === "" && form.customStation.trim() === "") {
    errors.station = "Choose a station, or type the one you want.";
  }
  if (form.method === "doorstep" && form.address.trim() === "") {
    errors.address = "Enter your delivery address.";
  }
  return errors;
}

export type CheckoutValues =
  | { method: "pickup"; name: string; phone: string; payment: PaymentChoice }
  | {
      method: "station";
      name: string;
      phone: string;
      payment: PaymentChoice;
      stationId: string;
      customStation: string;
    }
  | { method: "doorstep"; name: string; phone: string; payment: PaymentChoice; address: string };

/** Trimmed values for the chosen method only. Fields for other methods are dropped. */
export function toValues(form: CheckoutForm, payOnDeliveryAllowed: boolean): CheckoutValues {
  const base = {
    name: form.name.trim(),
    phone: form.phone.trim(),
    payment: effectivePayment(form, payOnDeliveryAllowed),
  };
  switch (form.method) {
    case "pickup":
      return { method: "pickup", ...base };
    case "station":
      return {
        method: "station",
        ...base,
        stationId: form.stationId,
        customStation: form.stationId === "" ? form.customStation.trim() : "",
      };
    case "doorstep":
      return { method: "doorstep", ...base, address: form.address.trim() };
  }
}
