import { cn } from "../cn";

export interface PriceTier {
  /** The tier name from the server, for example "retail" or "wholesale". */
  tier: string;
  minQuantity: number;
  /** The server's ready-made price text. */
  priceDisplay: string;
}

/** Shows only the tiers it is given. The server decides which tiers exist. */
export function PriceTierList({ tiers, className }: { tiers: readonly PriceTier[]; className?: string }) {
  if (tiers.length === 0) return null;
  return (
    <ul aria-label="Prices" className={cn("flex flex-col gap-1", className)}>
      {tiers.map((t) => (
        <li key={`${t.tier}-${t.minQuantity}`} className="flex justify-between gap-3">
          <span className="capitalize text-ink">
            {t.tier}
            {t.minQuantity > 1 ? `, ${t.minQuantity} or more` : ""}
          </span>
          <span className="font-semibold tabular-nums text-ink">{t.priceDisplay}</span>
        </li>
      ))}
    </ul>
  );
}
