import type { Metadata } from "next";
import { PlaceholderPage } from "@/components/PlaceholderPage";

export const metadata: Metadata = { title: "Products" };

export default function Page() {
  return <PlaceholderPage title="Products" />;
}
