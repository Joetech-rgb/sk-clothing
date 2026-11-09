import { cn } from "../cn";

export interface VariantOption {
  id: number;
  size: string;
  colour: string;
  inStock: boolean;
}

export function variantLabel(variant: Pick<VariantOption, "size" | "colour">): string {
  const text = [variant.size, variant.colour].filter((part) => part !== "").join(" · ");
  return text === "" ? "Standard" : text;
}

export interface VariantPickerProps {
  variants: readonly VariantOption[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  legend?: string;
  className?: string;
}

export function VariantPicker({
  variants,
  selectedId,
  onSelect,
  legend = "Choose an option",
  className,
}: VariantPickerProps) {
  return (
    <fieldset className={cn("flex flex-col gap-2", className)}>
      <legend className="mb-1 text-sm font-medium">{legend}</legend>
      {variants.map((v) => (
        <label
          key={v.id}
          className={cn(
            "flex min-h-11 items-center gap-3 rounded-control border px-3 text-base",
            v.id === selectedId ? "border-accent" : "border-line",
            !v.inStock && "opacity-50",
          )}
        >
          <input
            type="radio"
            name="variant"
            value={v.id}
            checked={v.id === selectedId}
            disabled={!v.inStock}
            onChange={() => onSelect(v.id)}
          />
          {variantLabel(v)}
          {!v.inStock && <span className="text-sm text-ink-muted">(sold out)</span>}
        </label>
      ))}
    </fieldset>
  );
}
