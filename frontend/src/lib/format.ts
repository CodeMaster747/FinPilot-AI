// Indian number formatting (₹12,34,567), compact lakh/crore, and dates.
import { format, formatDistanceToNowStrict, parseISO } from "date-fns";

function group(whole: string) {
  if (whole.length <= 3) return whole;
  const tail = whole.slice(-3);
  let head = whole.slice(0, -3);
  const parts: string[] = [];
  while (head.length > 2) {
    parts.unshift(head.slice(-2));
    head = head.slice(0, -2);
  }
  if (head) parts.unshift(head);
  return parts.join(",") + "," + tail;
}

export function inr(value: number | null | undefined, opts: { decimals?: boolean; sign?: boolean } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const neg = value < 0;
  const abs = Math.abs(value);
  const fixed = opts.decimals ? abs.toFixed(2) : Math.round(abs).toString();
  const [w, f] = fixed.split(".");
  const body = "₹" + group(w) + (f ? "." + f : "");
  if (neg) return "−" + body;
  return opts.sign && value > 0 ? "+" + body : body;
}

export function inrCompact(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(abs >= 1e8 ? 0 : 1)}Cr`;
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(abs >= 1e6 ? 1 : 2).replace(/\.0+$/, "")}L`;
  if (abs >= 1e3) return `${sign}₹${(abs / 1e3).toFixed(abs >= 1e4 ? 0 : 1).replace(/\.0$/, "")}K`;
  return `${sign}₹${Math.round(abs)}`;
}

export function pct(value: number | null | undefined, digits = 0) {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(digits)}%`;
}

export function fmtDate(iso: string | null | undefined, pattern = "d MMM yyyy") {
  if (!iso) return "—";
  try {
    return format(parseISO(iso), pattern);
  } catch {
    return iso;
  }
}

export function ago(iso: string | null | undefined) {
  if (!iso) return "never";
  try {
    return formatDistanceToNowStrict(parseISO(iso), { addSuffix: true });
  } catch {
    return iso;
  }
}

export function titleCase(s: string) {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Backend links ("/transactions?anomalies=1") → the static export's trailing-slash routes ("/transactions/?anomalies=1"). */
export function appHref(link: string | null | undefined, fallback = "/dashboard/") {
  if (!link) return fallback;
  const [path, query] = link.split("?");
  const p = path.endsWith("/") ? path : `${path}/`;
  return query ? `${p}?${query}` : p;
}
