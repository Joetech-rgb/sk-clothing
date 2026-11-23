import type { BrowseParams } from "./browse";

/**
 * Size, colour and price filters for the product list. They live in the page address, so a
 * filtered list can be shared and the back button works. Prices are whole cedis, so the screen
 * never converts money. Built against the shape proposed to Agent D (to be confirmed).
 */
export interface FilterParams {
  sizes: string[];
  colours: string[];
  priceMin?: number;
  priceMax?: number;
}

export const EMPTY_FILTERS: FilterParams = { sizes: [], colours: [] };

type Raw = Record<string, string | string[] | undefined>;

const MAX_CHOICES = 20;
const MAX_TEXT = 50;
const MAX_CEDIS = 10_000_000;

function many(value: string | string[] | undefined): string[] {
  const list = Array.isArray(value) ? value : value === undefined ? [] : [value];
  const seen = new Set<string>();
  for (const item of list) {
    const text = item.trim();
    if (text !== "" && text.length <= MAX_TEXT) seen.add(text);
    if (seen.size >= MAX_CHOICES) break;
  }
  return [...seen];
}

function cedis(value: string | string[] | undefined): number | undefined {
  const text = (Array.isArray(value) ? value[0] : value)?.trim();
  if (!text || !/^\d{1,8}$/.test(text)) return undefined;
  const number = Number(text);
  return number <= MAX_CEDIS ? number : undefined;
}

export function parseFilterParams(raw: Raw): FilterParams {
  const filters: FilterParams = { sizes: many(raw.size), colours: many(raw.colour) };
  const priceMin = cedis(raw.price_min);
  const priceMax = cedis(raw.price_max);
  if (priceMin !== undefined) filters.priceMin = priceMin;
  if (priceMax !== undefined) filters.priceMax = priceMax;
  return filters;
}

/** How many separate choices are active, for the "Filters (3)" label. */
export function activeFilterCount(filters: FilterParams): number {
  return (
    filters.sizes.length +
    filters.colours.length +
    (filters.priceMin !== undefined ? 1 : 0) +
    (filters.priceMax !== undefined ? 1 : 0)
  );
}

export function hasFilters(filters: FilterParams): boolean {
  return activeFilterCount(filters) > 0;
}

/** A /products address with the search, category, sort, filters and page. */
export function productsHrefWithFilters(browse: BrowseParams, filters: FilterParams): string {
  const query = new URLSearchParams();
  if (browse.q) query.set("q", browse.q);
  if (browse.category) query.set("category", browse.category);
  if (browse.sort) query.set("sort", browse.sort);
  for (const size of filters.sizes) query.append("size", size);
  for (const colour of filters.colours) query.append("colour", colour);
  if (filters.priceMin !== undefined) query.set("price_min", String(filters.priceMin));
  if (filters.priceMax !== undefined) query.set("price_max", String(filters.priceMax));
  if (browse.cursor) query.set("cursor", browse.cursor);
  const text = query.toString();
  return text ? `/products?${text}` : "/products";
}
