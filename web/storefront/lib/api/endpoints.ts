import type { components, paths } from "@sk/api-client";
import { apiRequest } from "./request";
import type { RequestOptions } from "./request";

type Schemas = components["schemas"];
export type ProductQuery = NonNullable<
  paths["/api/v1/catalog/products/"]["get"]["parameters"]["query"]
>;

/**
 * One typed function per endpoint whose response is described in the schema.
 * Request and response types come from the generated client, never written by hand.
 * The client sends ids and quantities only, never a price.
 */
type Options = Omit<RequestOptions, "body" | "query">;

export function listCategories(options?: Options) {
  return apiRequest<Schemas["Category"][]>("GET", "/catalog/categories/", options);
}

export function listProducts(query: ProductQuery = {}, options?: Options) {
  return apiRequest<Schemas["ProductPage"]>("GET", "/catalog/products/", { ...options, query });
}

export function getProduct(slug: string, options?: Options) {
  return apiRequest<Schemas["ProductDetail"]>(
    "GET",
    `/catalog/products/${encodeURIComponent(slug)}/`,
    options,
  );
}

export function priceCart(items: Schemas["PriceItem"][], options?: Options) {
  const body: Schemas["PriceRequest"] = { items };
  return apiRequest<Schemas["PriceResponse"]>("POST", "/catalog/price/", { ...options, body });
}

export function listStations(options?: Options) {
  return apiRequest<Schemas["Station"][]>("GET", "/delivery/stations/", options);
}

export function quoteDelivery(body: Schemas["QuoteRequest"], options?: Options) {
  return apiRequest<Schemas["QuoteResponse"]>("POST", "/delivery/quote/", { ...options, body });
}
