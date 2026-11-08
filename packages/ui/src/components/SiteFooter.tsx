import type { ReactNode } from "react";
import { cn } from "../cn";

export function SiteFooter({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <footer className={cn("border-t border-line bg-surface-muted", className)}>
      <div className="mx-auto max-w-5xl px-4 py-6 text-sm text-ink-muted">
        {children}
      </div>
    </footer>
  );
}
