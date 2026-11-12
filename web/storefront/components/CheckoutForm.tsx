"use client";

import { useReducer, useState } from "react";
import type { ReactNode } from "react";
import { Button, Card, Input } from "@sk/ui";
import {
  EMPTY_FORM,
  effectivePayment,
  formReducer,
  missingFields,
  toValues,
} from "../lib/checkout/form";
import type { CheckoutValues, DeliveryMethod, FieldName } from "../lib/checkout/form";
import type { PinValue } from "./LocationPicker";

export interface StationOption {
  name: string;
}

export interface CheckoutFormProps {
  /** From GET /api/v1/delivery/stations/. */
  stations: readonly StationOption[];
  /** `cod_allowed` from the server's delivery quote. */
  codAllowed: boolean;
  /**
   * Doorstep needs a pinned map location (the server requires coordinates), so it stays
   * off unless the map is configured.
   */
  doorstepAvailable?: boolean;
  /** Renders the map pin. Receives the current pin and a way to set it. */
  renderLocationPicker?: (props: {
    value: PinValue | null;
    onChange: (value: PinValue) => void;
  }) => ReactNode;
  submitting?: boolean;
  /** The server's error message in plain words, if any. */
  serverError?: string;
  onSubmit: (values: CheckoutValues) => void;
}

const OTHER_STATION = "__other__";

const METHODS: ReadonlyArray<{ value: DeliveryMethod; label: string }> = [
  { value: "pickup", label: "Pick up from the shop" },
  { value: "station", label: "Deliver to a station" },
  { value: "doorstep", label: "Deliver to my door" },
];

const radioRow =
  "flex min-h-11 items-center gap-3 rounded-control border border-line px-3 text-base";

export function CheckoutForm({
  stations,
  codAllowed,
  doorstepAvailable = false,
  renderLocationPicker,
  submitting = false,
  serverError,
  onSubmit,
}: CheckoutFormProps) {
  const [form, dispatch] = useReducer(formReducer, EMPTY_FORM);
  const [errors, setErrors] = useState<Partial<Record<FieldName, string>>>({});
  const payment = effectivePayment(form, codAllowed);
  const methods = METHODS.filter((m) => doorstepAvailable || m.value !== "doorstep");
  const pin: PinValue | null =
    form.latitude === null || form.longitude === null
      ? null
      : { latitude: form.latitude, longitude: form.longitude };

  function handleSubmit(event: React.SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = missingFields(form, codAllowed);
    setErrors(found);
    if (Object.keys(found).length === 0) {
      onSubmit(toValues(form, codAllowed));
    }
  }

  return (
    <Card>
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        {serverError && (
          <p role="alert" className="text-danger">
            {serverError}
          </p>
        )}

        <Input
          label="Your name"
          autoComplete="name"
          value={form.name}
          error={errors.name}
          onChange={(e) => dispatch({ type: "set_field", field: "name", value: e.target.value })}
        />
        <Input
          label="Phone number"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          value={form.phone}
          error={errors.phone}
          onChange={(e) => dispatch({ type: "set_field", field: "phone", value: e.target.value })}
        />

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium">How do you want to get your order?</legend>
          {methods.map((m) => (
            <label key={m.value} className={radioRow}>
              <input
                type="radio"
                name="method"
                value={m.value}
                checked={form.method === m.value}
                onChange={() => dispatch({ type: "set_method", method: m.value })}
              />
              {m.label}
            </label>
          ))}
        </fieldset>

        {form.method === "station" && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <label htmlFor="station" className="text-sm font-medium">
                Station
              </label>
              <select
                id="station"
                value={form.stationTyped ? OTHER_STATION : form.stationName}
                aria-invalid={errors.station ? true : undefined}
                onChange={(e) => {
                  if (e.target.value === OTHER_STATION) {
                    dispatch({ type: "set_station_typed", typed: true });
                  } else {
                    dispatch({ type: "set_station", stationName: e.target.value });
                  }
                }}
                className="min-h-11 rounded-control border border-line bg-surface px-3 text-base"
              >
                <option value="">Choose a station</option>
                {stations.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name}
                  </option>
                ))}
                <option value={OTHER_STATION}>My station is not listed</option>
              </select>
            </div>
            {form.stationTyped && (
              <Input
                label="Station name"
                value={form.stationName}
                onChange={(e) =>
                  dispatch({ type: "set_field", field: "stationName", value: e.target.value })
                }
              />
            )}
            {errors.station && (
              <p className="text-sm text-danger" role="alert">
                {errors.station}
              </p>
            )}
          </div>
        )}

        {form.method === "doorstep" && (
          <div className="flex flex-col gap-3">
            <Input
              label="Delivery address"
              autoComplete="street-address"
              value={form.address}
              error={errors.address}
              onChange={(e) =>
                dispatch({ type: "set_field", field: "address", value: e.target.value })
              }
            />
            {renderLocationPicker?.({
              value: pin,
              onChange: (v) =>
                dispatch({ type: "set_location", latitude: v.latitude, longitude: v.longitude }),
            })}
            {errors.location && (
              <p className="text-sm text-danger" role="alert">
                {errors.location}
              </p>
            )}
          </div>
        )}

        {codAllowed && (
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-sm font-medium">How do you want to pay?</legend>
            <label className={radioRow}>
              <input
                type="radio"
                name="payment"
                value="online"
                checked={form.payment === "online"}
                onChange={() => dispatch({ type: "set_payment", payment: "online" })}
              />
              Pay online
            </label>
            <label className={radioRow}>
              <input
                type="radio"
                name="payment"
                value="cod"
                checked={form.payment === "cod"}
                onChange={() => dispatch({ type: "set_payment", payment: "cod" })}
              />
              Pay when it arrives
            </label>
          </fieldset>
        )}

        {payment === "online" && (
          <Input
            label="Email address"
            type="email"
            inputMode="email"
            autoComplete="email"
            value={form.email}
            error={errors.email}
            onChange={(e) => dispatch({ type: "set_field", field: "email", value: e.target.value })}
          />
        )}

        <Button type="submit" fullWidth disabled={submitting}>
          {submitting ? "Please wait" : "Continue"}
        </Button>
      </form>
    </Card>
  );
}
