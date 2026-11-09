import { describe, expect, it } from "vitest";
import {
  getProduct,
  listProducts,
  listStations,
  priceCart,
  quoteDelivery,
} from "./endpoints";

interface Call {
  url: string;
  init: RequestInit & { headers: Record<string, string> };
}

function fakeFetch(body: unknown = {}) {
  const calls: Call[] = [];
  const impl = ((url: string, init: Call["init"]) => {
    calls.push({ url, init });
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
  }) as unknown as typeof fetch;
  return { impl, calls };
}

describe("endpoints", () => {
  it("lists products with the query the caller gave", async () => {
    const { impl, calls } = fakeFetch({ results: [], next_cursor: null });
    await listProducts({ q: "tee", sort: "newest", cursor: undefined }, { fetch: impl });
    expect(calls[0]?.url).toBe("/api/v1/catalog/products/?q=tee&sort=newest");
    expect(calls[0]?.init.method).toBe("GET");
  });

  it("encodes the slug of a product", async () => {
    const { impl, calls } = fakeFetch();
    await getProduct("cotton tee/red", { fetch: impl });
    expect(calls[0]?.url).toBe("/api/v1/catalog/products/cotton%20tee%2Fred/");
  });

  it("prices a basket by sending ids and quantities only", async () => {
    const { impl, calls } = fakeFetch();
    await priceCart([{ variant_id: 3, quantity: 2 }], { fetch: impl });
    expect(calls[0]?.url).toBe("/api/v1/catalog/price/");
    expect(JSON.parse(calls[0]?.init.body as string)).toEqual({
      items: [{ variant_id: 3, quantity: 2 }],
    });
  });

  it("asks for stations", async () => {
    const { impl, calls } = fakeFetch([]);
    await listStations({ fetch: impl });
    expect(calls[0]?.url).toBe("/api/v1/delivery/stations/");
  });

  it("asks for a delivery quote with where to, never a fee", async () => {
    const { impl, calls } = fakeFetch();
    await quoteDelivery({ method: "station", station_name: "Madina" }, { fetch: impl });
    expect(JSON.parse(calls[0]?.init.body as string)).toEqual({
      method: "station",
      station_name: "Madina",
    });
  });

  it("passes the server base URL through for server code", async () => {
    const { impl, calls } = fakeFetch([]);
    await listStations({ baseUrl: "http://backend:8000/api/v1", fetch: impl });
    expect(calls[0]?.url).toBe("http://backend:8000/api/v1/delivery/stations/");
  });
});
