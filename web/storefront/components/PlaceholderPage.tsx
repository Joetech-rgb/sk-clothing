import { Card } from "@sk/ui";

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <Card>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-ink-muted">This page is being built.</p>
    </Card>
  );
}
