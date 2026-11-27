"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, Card, Input } from "@sk/ui";
import { requestLoginCode, verifyLoginCode } from "../lib/auth/api";
import { describeError } from "../lib/api/errors";

type Step = "phone" | "code";

/** Phone-code sign-in. The code is typed here and sent to the server; it is never stored. */
export function LoginView() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function sendCode(event?: React.SyntheticEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (phone.trim() === "") {
      setError("Enter your phone number.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    const result = await requestLoginCode(phone);
    setBusy(false);
    if (!result.ok) {
      setError(describeError(result.error));
      return;
    }
    setStep("code");
    setNotice("We have sent a code to your phone.");
  }

  async function signIn(event: React.SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    if (code.trim() === "") {
      setError("Enter the code we sent you.");
      return;
    }
    setBusy(true);
    setError(null);
    const result = await verifyLoginCode(phone, code);
    setBusy(false);
    if (!result.ok) {
      setError(describeError(result.error));
      return;
    }
    setCode("");
    router.push("/");
    router.refresh();
  }

  return (
    <div className="mx-auto flex max-w-md flex-col gap-4">
      <h1 className="text-2xl font-semibold">Sign in</h1>
      <Card>
        {step === "phone" ? (
          <form onSubmit={sendCode} noValidate className="flex flex-col gap-4">
            <p className="text-ink-muted">Enter your phone number and we will send you a code.</p>
            <Input
              label="Phone number"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
            {error && (
              <p role="alert" className="text-danger">
                {error}
              </p>
            )}
            <Button type="submit" fullWidth disabled={busy}>
              {busy ? "Please wait" : "Send code"}
            </Button>
          </form>
        ) : (
          <form onSubmit={signIn} noValidate className="flex flex-col gap-4">
            {notice && (
              <p role="status" className="text-ink-muted">
                {notice}
              </p>
            )}
            <Input
              label="Code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
            {error && (
              <p role="alert" className="text-danger">
                {error}
              </p>
            )}
            <Button type="submit" fullWidth disabled={busy}>
              {busy ? "Please wait" : "Sign in"}
            </Button>
            <div className="flex flex-wrap gap-3 text-sm">
              <button type="button" className="underline text-ink" onClick={() => void sendCode()}>
                Send a new code
              </button>
              <button
                type="button"
                className="underline text-ink"
                onClick={() => {
                  setStep("phone");
                  setCode("");
                  setError(null);
                  setNotice(null);
                }}
              >
                Use a different number
              </button>
            </div>
          </form>
        )}
      </Card>
      <p className="text-sm text-ink-muted">
        You do not need an account to order. You can{" "}
        <Link href="/products" className="underline text-ink">
          keep shopping as a guest
        </Link>
        .
      </p>
    </div>
  );
}
