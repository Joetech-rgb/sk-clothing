import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { SiteHeader } from "./SiteHeader";

const nav = [
  { label: "Products", href: "/products" },
  { label: "Cart", href: "/cart" },
] as const;

describe("SiteHeader", () => {
  it("links the shop name to the home page", () => {
    render(<SiteHeader shopName="S.K Clothing" nav={nav} />);
    const home = screen.getByRole("link", { name: "S.K Clothing" });
    expect(home.getAttribute("href")).toBe("/");
  });

  it("renders the navigation links in a labelled landmark", () => {
    render(<SiteHeader shopName="S.K Clothing" nav={nav} />);
    const landmark = screen.getByRole("navigation", { name: "Main" });
    expect(landmark).toBeTruthy();
    expect(screen.getByRole("link", { name: "Products" }).getAttribute("href")).toBe(
      "/products",
    );
    expect(screen.getByRole("link", { name: "Cart" }).getAttribute("href")).toBe("/cart");
  });

  it("offers a skip link to the main content", () => {
    render(<SiteHeader shopName="S.K Clothing" nav={nav} />);
    expect(screen.getByText("Skip to content").getAttribute("href")).toBe("#main");
  });

  it("uses the link component the app passes in", () => {
    function AppLink(props: { href: string; className?: string; children?: ReactNode }) {
      return (
        <a href={props.href} className={props.className} data-app-link="yes">
          {props.children}
        </a>
      );
    }
    render(<SiteHeader shopName="S.K Clothing" nav={nav} linkAs={AppLink} />);
    expect(screen.getByRole("link", { name: "Products" }).getAttribute("data-app-link")).toBe(
      "yes",
    );
  });

  it("shows the actions slot", () => {
    render(<SiteHeader shopName="S.K Clothing" nav={nav} actions={<span>3 items</span>} />);
    expect(screen.getByText("3 items")).toBeTruthy();
  });
});
