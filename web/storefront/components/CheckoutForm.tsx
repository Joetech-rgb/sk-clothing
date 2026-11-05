"use client";

import { useReducer, useState } from "react";
import { Button, Card, Input } from "@sk/ui";
import {
  EMPTY_FORM,
  formReducer,
  missingFields,
  toValues,
} from "../lib/checkout/form";
import type { CheckoutValues, DeliveryMethod, FieldName } from "../lib/checkout/form";

export interface StationOption {
  id: string;
  name: string;
}

export interface CheckoutFormProps {
  /** From the server's station list. */
  stations: readonly StationOption[];
  /** Whether the server allows pay on delivery for this order. */
  payOnDeliveryAllowed: boolean;
  submitting?: boolean;
  /** The server's error message in plain words, if any. */
  serverError?: string;
  onSubmit: (values: CheckoutValues) => void;
}

const METHODS: ReadonlyArray<{ value: DeliveryMethod; label: string }> = [
  { value: "pickup", label: "Pick up from the shop" },
  { value: "station", label: "Deliver to a station" },
  { value: "doorstep", label: "Deliver to my door" },
];

const radioRow =
  "flex min-h-11 items-center gap-3 rounded-control border border-line px-3 text-base";

export function CheckoutForm({
  stations,
  payOnDeliveryAllowed,
  submitting = false,
  serverError,
  onSubmit,
}: CheckoutFormProps) {
  const [form, dispatch] = useReducer(formReducer, EMPTY_FORM);
  const [errors, setErrors] = useState<Partial<Record<FieldName, string>>>({});

  function handleSubmit(event: React.SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = missingFields(form);
    setErrors(found);
    if (Object.keys(found).length === 0) {
      onSubmit(toValues(form, payOnDeliveryAllowed));
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
          {METHODS.map((m) => (
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
                value={form.stationId}
                aria-invalid={errors.station ? true : undefined}
                onChange={(e) => dispatch({ type: "set_station", stationId: e.target.value })}
                className="min-h-11 rounded-control border border-line bg-surface px-3 text-base"
              >
                <option value="">Choose a station</option>
                {stations.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <Input
              label="My station is not listed"
              value={form.customStation}
              error={errors.station}
              onChange={(e) =>
                dispatch({ type: "set_field", field: "customStation", value: e.target.value })
              }
            />
          </div>
        )}

        {form.method === "doorstep" && (
          <Input
            label="Delivery address"
            autoComplete="street-address"
            value={form.address}
            error={errors.address}
            onChange={(e) => dispatch({ type: "set_field", field: "address", value: e.target.value })}
          />
        )}

        {payOnDeliveryAllowed && (
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
                value="pay_on_delivery"
                checked={form.payment === "pay_on_delivery"}
                onChange={() => dispatch({ type: "set_payment", payment: "pay_on_delivery" })}
              />
              Pay when it arrives
            </label>
          </fieldset>
        )}

        <Button type="submit" fullWidth disabled={submitting}>
          {submitting ? "Please wait" : "Continue"}
        </Button>
      </form>
    </Card>
  );
}
