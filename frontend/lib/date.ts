/**
 * Return calendar date YYYY-MM-DD in Asia/Dhaka regardless of browser or OS timezone.
 */
export function getDhakaTodayISO(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Dhaka",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

/**
 * Return current YYYY-MM string in Asia/Dhaka.
 */
export function getDhakaMonthISO(now: Date = new Date()): string {
  return getDhakaTodayISO(now).slice(0, 7);
}

