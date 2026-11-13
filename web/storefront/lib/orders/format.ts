/** "awaiting_payment" becomes "Awaiting payment". Display only. */
export function humanize(status: string): string {
  const spaced = status.replaceAll("_", " ").trim();
  return spaced === "" ? "" : spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
