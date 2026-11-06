"use client";

import { useState } from "react";
import { Card } from "@sk/ui";
import { DoorstepLocationPicker } from "../../../components/DoorstepLocationPicker";
import type { PinValue } from "../../../components/LocationPicker";

/** Development only. Lets you try the map pin with your token. Never shown in production. */
export function MapTestClient() {
  const [pin, setPin] = useState<PinValue | null>(null);
  return (
    <Card className="flex flex-col gap-3">
      <h1 className="text-xl font-semibold">Map pin test (development only)</h1>
      <DoorstepLocationPicker value={pin} onChange={setPin} />
      <p className="text-sm">
        {pin ? `latitude ${pin.latitude.toFixed(5)}, longitude ${pin.longitude.toFixed(5)}` : "No pin yet"}
      </p>
    </Card>
  );
}