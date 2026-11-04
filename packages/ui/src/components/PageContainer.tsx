import type { HTMLAttributes } from "react";
import { cn } from "../cn";

export function PageContainer({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mx-auto w-full max-w-5xl px-4 py-6", className)} {...props} />;
}
