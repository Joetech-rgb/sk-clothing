import { cn } from "../cn";
import { formatGhs } from "../money";

export interface PriceDisplayProps {
  /** Integer pesewas exactly as the server returned them. */
  pesewas: number;
  /** Optional short label, for example a tier name supplied by the server. */
  label?: string;
  className?: string;
}

export function PriceDisplay({ pesewas, label, className }: PriceDisplayProps) {
  return (
    <p className={cn("text-ink", className)}>
      {label && <span className="mr-1 text-sm text-ink-muted">{label}</span>}
      <span className="font-semibold tabular-nums">{formatGhs(pesewas)}</span>
    </p>
  );
}
