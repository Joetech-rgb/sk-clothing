import Link from "next/link";
import { ProductCard, ProductGrid } from "@sk/ui";
import { listCategories, listProducts } from "../lib/api/endpoints";
import { serverOptions } from "../lib/api/server";
import { productsHref } from "../lib/catalog/browse";
import { toProductCard } from "../lib/catalog/view-models";

export default async function HomePage() {
  const [categories, fresh] = await Promise.all([
    listCategories(serverOptions),
    listProducts({ sort: "newest", limit: 8 }, serverOptions),
  ]);
  const topCategories = categories.ok ? categories.data.filter((c) => c.parent_id === null) : [];
  const newest = fresh.ok ? fresh.data.results : [];

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3 rounded-card bg-surface-muted p-6">
        <h1 className="text-3xl font-semibold text-ink">S.K Clothing</h1>
        <p className="text-ink-muted">Shop clothing and general goods.</p>
        <form action="/products" method="get" role="search" className="flex gap-2">
          <label htmlFor="home-q" className="sr-only">
            Search products
          </label>
          <input
            id="home-q"
            name="q"
            type="search"
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
      </section>

      {topCategories.length > 0 && (
        <section aria-labelledby="shop-by-category" className="flex flex-col gap-3">
          <h2 id="shop-by-category" className="text-xl font-semibold">
            Shop by category
          </h2>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {topCategories.map((category) => (
              <li key={category.id}>
                <Link
                  href={productsHref({ category: category.slug })}
                  className="flex min-h-20 items-center justify-center rounded-card border border-line p-3 text-center text-ink hover:bg-surface-muted"
                >
                  {category.name}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {newest.length > 0 && (
        <section aria-labelledby="new-arrivals" className="flex flex-col gap-3">
          <h2 id="new-arrivals" className="text-xl font-semibold">
            New arrivals
          </h2>
          <ProductGrid>
            {newest.map((item) => (
              <ProductCard key={item.id} {...toProductCard(item)} linkAs={Link} />
            ))}
          </ProductGrid>
          <Link
            href={productsHref({ sort: "newest" })}
            className="inline-flex min-h-11 items-center self-start rounded-control border border-line px-4 text-ink hover:bg-surface-muted"
          >
            See all products
          </Link>
        </section>
      )}
    </div>
  );
}
