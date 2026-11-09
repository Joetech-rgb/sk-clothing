import type { ReactNode } from "react";
import { Card } from "./Card";

export interface CartSummaryProps {
  /** The server's subtotal text. Leave undefined while the server is still pricing the cart. */
  subtotalDisplay?: string;
  note?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function CartSummary({ subtotalDisplay, note, action, className }: CartSummaryProps) {
  return (
    <Card className={className}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-base text-ink">Subtotal</span>
        <span className="text-lg font-semibold tabular-nums text-ink">
          {subtotalDisplay ?? "Checking prices"}
        </span>
      </div>
      {note && <p className="mt-2 text-sm text-ink-muted">{note}</p>}
      {action && <div className="mt-3">{action}</div>}
    </Card>
  );
}
