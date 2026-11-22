import Link from "next/link";
import type { BrowseParams } from "../lib/catalog/browse";
import {
  EMPTY_FILTERS,
  activeFilterCount,
  hasFilters,
  productsHrefWithFilters,
} from "../lib/catalog/filters";
import type { FilterParams } from "../lib/catalog/filters";

/** What the server says is available to choose from. */
export interface Facets {
  sizes: readonly string[];
  colours: readonly string[];
  /** The server's price text for the lowest and highest price, shown as a hint. */
  priceMinDisplay?: string | null;
  priceMaxDisplay?: string | null;
}

function Group({
  legend,
  name,
  options,
  selected,
}: {
  legend: string;
  name: string;
  options: readonly string[];
  selected: readonly string[];
}) {
  if (options.length === 0) return null;
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm font-medium">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => (
          <label
            key={option}
            className="flex min-h-11 items-center gap-2 rounded-control border border-line px-3 text-base"
          >
            <input
              type="checkbox"
              name={name}
              value={option}
              defaultChecked={selected.includes(option)}
            />
            {option}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/**
 * Filters as a plain form that adds size, colour and price to the page address. It works without
 * JavaScript. Starting a new filter returns to the first page.
 */
export function FilterPanel({
  facets,
  browse,
  filters,
}: {
  facets: Facets;
  browse: BrowseParams;
  filters: FilterParams;
}) {
  const count = activeFilterCount(filters);
  const noOptions =
    facets.sizes.length === 0 &&
    facets.colours.length === 0 &&
    !facets.priceMinDisplay &&
    !facets.priceMaxDisplay;
  if (noOptions && !hasFilters(filters)) return null;

  return (
    <details open={hasFilters(filters)} className="rounded-card border border-line p-3">
      <summary className="flex min-h-11 cursor-pointer items-center text-base font-medium text-ink">
        {count > 0 ? `Filters (${count})` : "Filters"}
      </summary>
      <form action="/products" method="get" className="mt-3 flex flex-col gap-4">
        {browse.q && <input type="hidden" name="q" value={browse.q} />}
        {browse.category && <input type="hidden" name="category" value={browse.category} />}
        {browse.sort && <input type="hidden" name="sort" value={browse.sort} />}

        <Group legend="Size" name="size" options={facets.sizes} selected={filters.sizes} />
        <Group legend="Colour" name="colour" options={facets.colours} selected={filters.colours} />

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium">Price (GHS)</legend>
          <div className="flex items-center gap-2">
            <label htmlFor="price_min" className="sr-only">
              Lowest price in cedis
            </label>
            <input
              id="price_min"
              name="price_min"
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder="From"
              defaultValue={filters.priceMin ?? ""}
              className="min-h-11 w-28 rounded-control border border-line bg-surface px-3 text-base text-ink"
            />
            <span className="text-ink-muted">to</span>
            <label htmlFor="price_max" className="sr-only">
              Highest price in cedis
            </label>
            <input
              id="price_max"
              name="price_max"
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder="To"
              defaultValue={filters.priceMax ?? ""}
              className="min-h-11 w-28 rounded-control border border-line bg-surface px-3 text-base text-ink"
            />
          </div>
          {(facets.priceMinDisplay || facets.priceMaxDisplay) && (
            <p className="text-sm text-ink-muted">
              Prices here run from {facets.priceMinDisplay ?? "..."} to {facets.priceMaxDisplay ?? "..."}.
            </p>
          )}
        </fieldset>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            className="inline-flex min-h-11 items-center rounded-control bg-accent px-4 text-base font-medium text-on-accent hover:bg-accent-hover"
          >
            Apply filters
          </button>
          {hasFilters(filters) && (
            <Link
              href={productsHrefWithFilters({ ...browse, cursor: undefined }, EMPTY_FILTERS)}
              className="text-ink underline"
            >
              Clear filters
            </Link>
          )}
        </div>
      </form>
    </details>
  );
}
