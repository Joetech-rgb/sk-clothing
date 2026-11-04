export const SHOP_TIME_ZONE = "Africa/Accra" as const;

/** Show a server timestamp in shop time (Africa/Accra), whatever the device zone. */
export function formatAccraDateTime(value: string | Date, locale = "en-GH"): string {
  const date = typeof value === "string" ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) {
    throw new RangeError("Invalid date");
  }
  return new Intl.DateTimeFormat(locale, {
    timeZone: SHOP_TIME_ZONE,
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
