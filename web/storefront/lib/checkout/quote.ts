import type { components } from "@sk/api-client";

type Quote = components["schemas"]["QuoteResponse"];

// Status words the backend uses (delivery/fees.py).
const PRICED = "priced";

export interface QuoteText {
  kind: "free" | "priced" | "awaiting";
  text: string;
}

/**
 * The sentence for a delivery quote. The fee text is the server's own; nothing is worked out here.
 * Draft wording, to be approved by the human.
 */
export function describeQuote(quote: Quote): QuoteText {
  const label = quote.method === "pickup" ? "Pickup" : "Delivery";
  if (quote.status !== PRICED || quote.fee === null) {
    return { kind: "awaiting", text: "We will confirm the delivery fee before you pay." };
  }
  if (quote.fee.pesewas === 0) {
    return { kind: "free", text: `${label}: free` };
  }
  return { kind: "priced", text: `${label}: ${quote.fee.display}` };
}
