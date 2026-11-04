export const CURRENCY_CODE = "GHS" as const;

/**
 * Display formatting only. Takes integer pesewas from the server and shows GHS.
 * No price, fee or discount logic lives here. Integer maths only, no floats,
 * and no Intl so the output is identical on every device.
 */
export function formatGhs(pesewas: number): string {
  if (!Number.isSafeInteger(pesewas)) {
    throw new RangeError("Amount must be a whole number of pesewas");
  }
  const negative = pesewas < 0;
  const abs = Math.abs(pesewas);
  const cedis = Math.floor(abs / 100);
  const rest = abs % 100;
  const grouped = String(cedis).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `${negative ? "-" : ""}${CURRENCY_CODE} ${grouped}.${String(rest).padStart(2, "0")}`;
}
