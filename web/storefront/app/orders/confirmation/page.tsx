import type { Metadata } from "next";
import { ConfirmationView } from "../../../components/ConfirmationView";

export const metadata: Metadata = { title: "Your order" };

export default function ConfirmationPage() {
  return <ConfirmationView />;
}
