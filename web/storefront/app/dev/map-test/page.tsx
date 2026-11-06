import { notFound } from "next/navigation";
import { MapTestClient } from "./MapTestClient";

export default function MapTestPage() {
  // A development tool: any production build answers "not found".
  if (process.env.NODE_ENV === "production") notFound();
  return <MapTestClient />;
}