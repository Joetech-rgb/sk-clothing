import { describeError } from "../api/errors";
import type { ApiError } from "../api/errors";
import type { FieldName } from "./form";

/** Which checkout form field each API field path belongs to (POST /api/v1/orders/). */
const FIELD_FOR_PATH: Record<string, FieldName> = {
  contact_name: "name",
  contact_phone: "phone",
  "delivery.station_name": "station",
  "delivery.address": "address",
  "delivery.latitude": "location",
  "delivery.longitude": "location",
};

export interface CheckoutErrors {
  /** Messages to show beside a field. */
  fields: Partial<Record<FieldName, string>>;
  /** A message for the top of the form when it belongs to no single field. */
  general: string | null;
}

export function checkoutErrors(error: ApiError): CheckoutErrors {
  if (error.code !== "validation_error") {
    return { fields: {}, general: describeError(error) };
  }
  const fields: Partial<Record<FieldName, string>> = {};
  const left: string[] = [];
  for (const [path, messages] of Object.entries(error.fields)) {
    const field = FIELD_FOR_PATH[path];
    const first = messages[0];
    if (first === undefined) continue;
    if (field) {
      fields[field] ??= first;
    } else {
      left.push(first);
    }
  }
  const general = left[0] ?? (Object.keys(fields).length === 0 ? error.message : null);
  return { fields, general };
}
