import type { Metadata } from "next";
import { Suspense } from "react";
import { PaymentReturnView } from "../../../components/PaymentReturnView";

export const metadata: Metadata = { title: "Your payment" };

export default function PaymentReturnPage() {
  return (
    <Suspense fallback={<p className="text-ink-muted">Loading.</p>}>
      <PaymentReturnView />
    </Suspense>
  );
}
