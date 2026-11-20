/** Search, category and sort choices for the product list, kept in the page address. */

export const SORTS = ["relevance", "newest", "price_low", "price_high"] as const;
export type Sort = (typeof SORTS)[number];

/** Draft wording, to be approved by the human. */
export const SORT_LABELS: Record<Sort, string> = {
  relevance: "Best match",
  newest: "Newest",
  price_low: "Price: low to high",
  price_high: "Price: high to low",
};

export interface BrowseParams {
  q?: string;
  category?: string;
  sort?: Sort;
  cursor?: string;
}

type Raw = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

const SLUG = /^[A-Za-z0-9_-]{1,100}$/;

/** Reads the page address's query. Anything unexpected is dropped rather than passed on. */
export function parseBrowseParams(raw: Raw): BrowseParams {
  const params: BrowseParams = {};
  const q = first(raw.q)?.trim();
  if (q) params.q = q.slice(0, 200);
  const category = first(raw.category)?.trim();
  if (category && SLUG.test(category)) params.category = category;
  const sort = first(raw.sort);
  if (sort && (SORTS as readonly string[]).includes(sort)) params.sort = sort as Sort;
  const cursor = first(raw.cursor)?.trim();
  if (cursor && cursor.length <= 64) params.cursor = cursor;
  return params;
}

/** A /products address that keeps the chosen search, category and sort. */
export function productsHref(params: BrowseParams): string {
  const query = new URLSearchParams();
  if (params.q) query.set("q", params.q);
  if (params.category) query.set("category", params.category);
  if (params.sort) query.set("sort", params.sort);
  if (params.cursor) query.set("cursor", params.cursor);
  const text = query.toString();
  return text ? `/products?${text}` : "/products";
}

/** The same choices from the first page again (a new search, category or sort starts over). */
export function withoutCursor(params: BrowseParams): BrowseParams {
  const { cursor: _cursor, ...rest } = params;
  return rest;
}
