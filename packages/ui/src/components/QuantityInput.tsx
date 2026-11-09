"use client";

import { useEffect, useState } from "react";
import { cn } from "../cn";
import { Button } from "./Button";

export interface QuantityInputProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  /** Only set when the server tells you a limit. No limit is assumed here. */
  max?: number;
  label?: string;
  className?: string;
}

/** onChange is only ever called with a whole number between min and max. */
export function QuantityInput({
  value,
  onChange,
  min = 1,
  max,
  label = "Quantity",
  className,
}: QuantityInputProps) {
  const [text, setText] = useState(String(value));

  useEffect(() => {
    setText(String(value));
  }, [value]);

  const canDecrease = value > min;
  const canIncrease = max === undefined || value < max;

  function commit() {
    const trimmed = text.trim();
    const number = Number(trimmed);
    const valid =
      trimmed !== "" &&
      Number.isInteger(number) &&
      number >= min &&
      (max === undefined || number <= max);
    if (valid) {
      if (number !== value) onChange(number);
      setText(String(number));
    } else {
      setText(String(value));
    }
  }

  return (
    <div className={cn("inline-flex items-center gap-1", className)}>
      <Button
        variant="secondary"
        className="w-11 px-0"
        aria-label="Decrease quantity"
        disabled={!canDecrease}
        onClick={() => onChange(value - 1)}
      >
        −
      </Button>
      <input
        type="text"
        inputMode="numeric"
        aria-label={label}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          }
        }}
        className="min-h-11 w-16 rounded-control border border-line bg-surface text-center text-base tabular-nums text-ink"
      />
      <Button
        variant="secondary"
        className="w-11 px-0"
        aria-label="Increase quantity"
        disabled={!canIncrease}
        onClick={() => onChange(value + 1)}
      >
        +
      </Button>
    </div>
  );
}
