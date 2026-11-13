import { Card } from "@sk/ui";
import type { OrderView } from "../lib/api/orders-temp";
import { humanize } from "../lib/orders/format";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="text-right tabular-nums text-ink">{value}</dd>
    </div>
  );
}

/** Shows an order exactly as the server describes it: statuses, lines and the server's prices. */
export function OrderCard({ order }: { order: OrderView }) {
  const showRefund = order.refundStatus !== "" && order.refundStatus !== "none";
  return (
    <Card className="flex flex-col gap-4">
      <div>
        <p className="text-sm text-ink-muted">Order reference</p>
        <p className="text-xl font-semibold tabular-nums text-ink">{order.reference}</p>
      </div>

      <dl className="flex flex-col gap-1 text-sm">
        <Row label="Payment" value={humanize(order.paymentStatus)} />
        <Row label="Order" value={humanize(order.fulfilmentStatus)} />
        {showRefund && <Row label="Refund" value={humanize(order.refundStatus)} />}
      </dl>

      {order.deliveryCode && (
        <div className="rounded-control border border-line bg-surface-muted p-3">
          <p className="text-sm text-ink-muted">Your delivery code</p>
          <p className="text-2xl font-semibold tabular-nums tracking-widest text-ink">
            {order.deliveryCode}
          </p>
          <p className="text-sm text-ink-muted">Give this code to the rider when your order arrives.</p>
        </div>
      )}

      {order.lines.length > 0 && (
        <ul className="flex flex-col gap-1 border-t border-line pt-3 text-sm">
          {order.lines.map((line, index) => (
            <li key={`${line.name}-${index}`} className="flex justify-between gap-3">
              <span className="text-ink">
                {line.name} × {line.quantity}
              </span>
              <span className="tabular-nums text-ink">{line.lineTotalDisplay}</span>
            </li>
          ))}
        </ul>
      )}

      <dl className="flex flex-col gap-1 border-t border-line pt-3 text-sm">
        <Row label="Subtotal" value={order.subtotalDisplay} />
        <Row label="Delivery" value={order.deliveryFeeDisplay ?? "To be confirmed"} />
        <Row label="Total" value={order.totalDisplay ?? "To be confirmed"} />
      </dl>
    </Card>
  );
}
