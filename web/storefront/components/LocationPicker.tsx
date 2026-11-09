"use client";

import { useEffect, useRef, useState } from "react";
import type { Map as MapboxMap, Marker } from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { Button } from "@sk/ui";

export interface PinValue {
  latitude: number;
  longitude: number;
}

export interface LocationPickerProps {
  /** A PUBLIC Mapbox token (pk.), restricted to our URLs in the Mapbox account. */
  token: string;
  value: PinValue | null;
  onChange: (value: PinValue) => void;
}

// Only where the map starts looking. The pin stays empty until the customer places it.
const START_CENTER: [number, number] = [-0.187, 5.6037];
const START_ZOOM = 11;

/**
 * Loaded lazily (see DoorstepLocationPicker) so the map code is never part of the
 * initial JavaScript. The pin is set only by the customer: a tap, a drag, or "use my
 * location". The server requires the coordinates for doorstep delivery.
 */
export default function LocationPicker({ token, value, onChange }: LocationPickerProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapboxMap | null>(null);
  const placeRef = useRef<((lng: number, lat: number, notify: boolean) => void) | null>(null);
  const onChangeRef = useRef(onChange);
  const startValue = useRef(value);
  const [message, setMessage] = useState<string>();

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    if (!token || !container.current) return;
    let cancelled = false;
    let map: MapboxMap | undefined;

    void import("mapbox-gl").then((mod) => {
      const element = container.current;
      if (cancelled || !element) return;
      const mapboxgl = mod.default;
      mapboxgl.accessToken = token;

      const start = startValue.current;
      map = new mapboxgl.Map({
        container: element,
        style: "mapbox://styles/mapbox/streets-v12",
        center: start ? [start.longitude, start.latitude] : START_CENTER,
        zoom: start ? 15 : START_ZOOM,
      });
      map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");
      mapRef.current = map;

      let marker: Marker | null = null;
      const place = (lng: number, lat: number, notify: boolean) => {
        if (!map) return;
        if (!marker) {
          marker = new mapboxgl.Marker({ draggable: true }).setLngLat([lng, lat]).addTo(map);
          marker.on("dragend", () => {
            if (!marker) return;
            const at = marker.getLngLat();
            onChangeRef.current({ latitude: at.lat, longitude: at.lng });
          });
        } else {
          marker.setLngLat([lng, lat]);
        }
        if (notify) onChangeRef.current({ latitude: lat, longitude: lng });
      };
      placeRef.current = place;

      if (start) place(start.longitude, start.latitude, false);
      map.on("click", (event) => place(event.lngLat.lng, event.lngLat.lat, true));
    });

    return () => {
      cancelled = true;
      map?.remove();
      mapRef.current = null;
      placeRef.current = null;
    };
  }, [token]);

  function useMyLocation() {
    if (!("geolocation" in navigator)) {
      setMessage("This phone cannot share its location here. Tap the map to place your pin.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        placeRef.current?.(longitude, latitude, true);
        mapRef.current?.flyTo({ center: [longitude, latitude], zoom: 16 });
        setMessage(undefined);
      },
      () => setMessage("We could not get your location. Tap the map to place your pin."),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  if (!token) {
    return (
      <p role="alert" className="text-danger">
        The map is not available right now.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <Button type="button" variant="secondary" onClick={useMyLocation}>
        Use my current location
      </Button>
      <div
        ref={container}
        role="application"
        aria-label="Map. Tap to place your delivery pin."
        className="h-64 w-full overflow-hidden rounded-card border border-line"
      />
      <p className="text-sm text-ink-muted">
        {value ? "Pin placed. Drag it to adjust." : "Tap the map to place your pin."}
      </p>
      {message && (
        <p role="status" className="text-sm text-danger">
          {message}
        </p>
      )}
    </div>
  );
}
