"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { isSignedIn, signOut } from "../lib/auth/api";

const style =
  "inline-flex min-h-11 items-center rounded-control px-3 text-base text-ink hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

/** "Sign in" or "Sign out" in the header, following what the server says about the session. */
export function AccountLink() {
  const pathname = usePathname();
  const router = useRouter();
  const [signedIn, setSignedIn] = useState(false);

  useEffect(() => {
    let alive = true;
    void isSignedIn().then((value) => {
      if (alive) setSignedIn(value);
    });
    return () => {
      alive = false;
    };
  }, [pathname]);

  if (!signedIn) {
    return (
      <Link href="/login" className={style}>
        Sign in
      </Link>
    );
  }
  return (
    <button
      type="button"
      className={style}
      onClick={async () => {
        await signOut();
        setSignedIn(false);
        router.refresh();
      }}
    >
      Sign out
    </button>
  );
}
