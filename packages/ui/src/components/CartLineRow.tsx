import { cn } from "../cn";
import { Button } from "./Button";
import { QuantityInput } from "./QuantityInput";

export interface CartLineRowProps {
  name: string;
  variantLabel?: string;
  imageUrl?: string | null;
  quantity: number;
  /** The server's price text. Leave undefined while the server is still pricing the cart. */
  unitPriceDisplay?: string;
  lineTotalDisplay?: string;
  onQuantityChange: (quantity: number) => void;
  onRemove: () => void;
  className?: string;
}

export function CartLineRow({
  name,
  variantLabel,
  imageUrl,
  quantity,
  unitPriceDisplay,
  lineTotalDisplay,
  onQuantityChange,
  onRemove,
  className,
}: CartLineRowProps) {
  return (
    <li className={cn("flex gap-3 border-b border-line py-3", className)}>
      <div className="h-20 w-20 shrink-0 overflow-hidden rounded-control bg-surface-muted">
        {imageUrl && (
          <img
            src={imageUrl}
            alt=""
            loading="lazy"
            decoding="async"
            className="h-full w-full object-cover"
          />
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2">
        <div>
          <p className="font-medium text-ink">{name}</p>
          {variantLabel && <p className="text-sm text-ink-muted">{variantLabel}</p>}
          <p className="text-sm tabular-nums text-ink-muted">{unitPriceDisplay ?? "Checking price"}</p>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <QuantityInput
            value={quantity}
            onChange={onQuantityChange}
            label={`Quantity for ${name}`}
          />
          <p className="font-semibold tabular-nums text-ink">{lineTotalDisplay ?? ""}</p>
        </div>
        <Button variant="ghost" className="self-start" aria-label={`Remove ${name}`} onClick={onRemove}>
          Remove
        </Button>
      </div>
    </li>
  );
}
