import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { PageContainer, SiteFooter, SiteHeader } from "@sk/ui";
import { CartLink } from "../components/CartLink";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "S.K Clothing", template: "%s | S.K Clothing" },
  description: "S.K Clothing online store",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

const NAV = [
  { label: "Products", href: "/products" },
  { label: "Track order", href: "/orders" },
] as const;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex min-h-dvh flex-col">
        <SiteHeader shopName="S.K Clothing" nav={NAV} linkAs={Link} actions={<CartLink />} />
        <main id="main" className="flex-1">
          <PageContainer>{children}</PageContainer>
        </main>
        <SiteFooter>S.K Clothing. Prices are in GHS.</SiteFooter>
      </body>
    </html>
  );
}
