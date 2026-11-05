import type { ComponentType, ReactNode } from "react";
import { cn } from "../cn";

export interface NavItem {
  label: string;
  href: string;
}

/** A plain anchor, or a framework link such as next/link, passed in by the app. */
export type LinkLike =
  | "a"
  | ComponentType<{ href: string; className?: string; children?: ReactNode }>;

export interface SiteHeaderProps {
  shopName: string;
  nav: readonly NavItem[];
  linkAs?: LinkLike;
  /** Right-hand slot, for example a cart link supplied by the app. */
  actions?: ReactNode;
  className?: string;
}

const linkStyle =
  "inline-flex min-h-11 items-center rounded-control px-3 text-base text-ink " +
  "hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

export function SiteHeader({
  shopName,
  nav,
  linkAs,
  actions,
  className,
}: SiteHeaderProps) {
  const L: LinkLike = linkAs ?? "a";
  return (
    <header className={cn("border-b border-line bg-surface", className)}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded-control focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2">
        <L href="/" className={cn(linkStyle, "text-lg font-semibold")}>
          {shopName}
        </L>
        <nav aria-label="Main" className="flex flex-1 flex-wrap items-center gap-1">
          {nav.map((item) => (
            <L key={item.href} href={item.href} className={linkStyle}>
              {item.label}
            </L>
          ))}
        </nav>
        {actions}
      </div>
    </header>
  );
}
