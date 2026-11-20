import type { Metadata } from "next";
import Link from "next/link";
import { ProductCard, ProductGrid } from "@sk/ui";
import { listCategories, listProducts } from "../../lib/api/endpoints";
import { describeError } from "../../lib/api/errors";
import { serverOptions } from "../../lib/api/server";
import {
  SORTS,
  SORT_LABELS,
  parseBrowseParams,
  productsHref,
  withoutCursor,
} from "../../lib/catalog/browse";
import { toProductCard } from "../../lib/catalog/view-models";

export const metadata: Metadata = { title: "Products" };

const chip =
  "inline-flex min-h-11 items-center rounded-control border px-3 text-base hover:bg-surface-muted";

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = parseBrowseParams(await searchParams);
  const fresh = withoutCursor(params);
  const [result, categories] = await Promise.all([
    listProducts(params, serverOptions),
    listCategories(serverOptions),
  ]);
  const topCategories = categories.ok ? categories.data.filter((c) => c.parent_id === null) : [];
  const filtered = Boolean(params.q ?? params.category);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Products</h1>

      <form action="/products" method="get" role="search" className="flex gap-2">
        {params.category && <input type="hidden" name="category" value={params.category} />}
        {params.sort && <input type="hidden" name="sort" value={params.sort} />}
        <label htmlFor="q" className="sr-only">
          Search products
        </label>
        <input
          id="q"
          name="q"
          type="search"
          defaultValue={params.q ?? ""}
          placeholder="Search products"
          className="min-h-11 flex-1 rounded-control border border-line bg-surface px-3 text-base text-ink"
        />
        <button
          type="submit"
          className="inline-flex min-h-11 items-center rounded-control bg-accent px-4 text-base font-medium text-on-accent hover:bg-accent-hover"
        >
          Search
        </button>
      </form>

      {topCategories.length > 0 && (
        <nav aria-label="Categories" className="flex flex-wrap gap-2">
          <Link
            href={productsHref({ ...fresh, category: undefined })}
            aria-current={params.category ? undefined : "page"}
            className={`${chip} ${params.category ? "border-line text-ink" : "border-accent text-ink"}`}
          >
            All
          </Link>
          {topCategories.map((category) => (
            <Link
              key={category.id}
              href={productsHref({ ...fresh, category: category.slug })}
              aria-current={params.category === category.slug ? "page" : undefined}
              className={`${chip} ${
                params.category === category.slug ? "border-accent text-ink" : "border-line text-ink"
              }`}
            >
              {category.name}
            </Link>
          ))}
        </nav>
      )}

      <nav aria-label="Sort" className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-ink-muted">Sort by</span>
        {SORTS.map((sort) => (
          <Link
            key={sort}
            href={productsHref({ ...fresh, sort })}
            aria-current={(params.sort ?? "relevance") === sort ? "true" : undefined}
            className={`rounded-control px-2 py-1 ${
              (params.sort ?? "relevance") === sort
                ? "bg-surface-muted font-medium text-ink"
                : "text-ink-muted hover:text-ink"
            }`}
          >
            {SORT_LABELS[sort]}
          </Link>
        ))}
      </nav>

      {!result.ok ? (
        <p role="alert" className="text-danger">
          {describeError(result.error)}
        </p>
      ) : result.data.results.length === 0 ? (
        <div className="flex flex-col gap-2">
          <p className="text-ink-muted">
            {filtered ? "No products match your search." : "There are no products to show yet."}
          </p>
          {filtered && (
            <Link href="/products" className="self-start underline text-ink">
              Clear search
            </Link>
          )}
        </div>
      ) : (
        <>
          <ProductGrid>
            {result.data.results.map((item) => (
              <ProductCard key={item.id} {...toProductCard(item)} linkAs={Link} />
            ))}
          </ProductGrid>
          {result.data.next_cursor && (
            <Link
              href={productsHref({ ...params, cursor: result.data.next_cursor })}
              className={`${chip} self-start border-line text-ink`}
            >
              Next page
            </Link>
          )}
        </>
      )}
    </div>
  );
}
