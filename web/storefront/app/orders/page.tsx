import type { Metadata } from "next";
import { TrackView } from "../../components/TrackView";

export const metadata: Metadata = { title: "Track your order" };

export default function OrdersPage() {
  return <TrackView />;
}
