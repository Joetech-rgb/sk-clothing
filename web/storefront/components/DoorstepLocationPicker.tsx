"use client";

import dynamic from "next/dynamic";
import type { PinValue } from "./LocationPicker";

/** The map code is a separate chunk, fetched only when this component first renders. */
const LocationPicker = dynamic(() => import("./LocationPicker"), {
  ssr: false,
  loading: () => <p className="text-ink-muted">Loading the map...</p>,
});

/** True when a Mapbox token was provided at build time. Doorstep stays off without it. */
export const MAP_CONFIGURED = Boolean(process.env.NEXT_PUBLIC_MAPBOX_TOKEN);

export function DoorstepLocationPicker(props: {
  value: PinValue | null;
  onChange: (value: PinValue) => void;
}) {
  const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN ?? "";
  return <LocationPicker token={token} {...props} />;
}
