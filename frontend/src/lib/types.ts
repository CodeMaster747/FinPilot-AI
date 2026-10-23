// Shapes returned by the FastAPI backend (only the fields the UI uses).

export type Category = { id: number; name: string; group: string; kind: string; icon: string; essential: boolean; discretionary: boolean };
export type Account = { id: number; name: string; institution: string; kind: string; mask: string | null };
export type AccountRow = Account & { balance: number | null; movement: number; balance_known: boolean; as_of: string | null; balance_source: string };

export type Txn = {
  id: number;
  date: string;
  occurred_at: string | null;
  amount: number;
  signed_amount: number;
  direction: "debit" | "credit";
  merchant: string;
  description: string;
  counterparty: string | null;
  category: Category | null;
  category_source: string;
  category_confidence: number;
  account: Account | null;
  origin: string;
  is_transfer: boolean;
  status: string;
  ref: string | null;
  needs_review: boolean;
  notes: string | null;
  items_count: number;
};

export type Message = {
  id: number;
  channel: "sms" | "email";
  feed: string;
  sender: string;
  subject: string | null;
  received_at: string;
  kind: string;
  confidence: number;
  parser: string | null;
  status: string;
  role: string | null;
  match_score: number | null;
  transaction_id: number | null;
  note: string | null;
  body_purged: boolean;
  body?: string | null;
  fields?: Record<string, { value: unknown; confidence: number; span: [number, number] | null }>;
  institution?: string | null;
};

export type TxnDetail = Txn & {
  items: { description: string; quantity: number; amount: number; source: string }[];
  evidence: Message[];
  receipts: { id: number; filename: string; kind: string }[];
  transfer_partner?: Txn | null;
};

export type User = {
  id: number;
  email: string;
  name: string;
  is_demo: boolean;
  onboarded: boolean;
  preferences: Record<string, unknown>;
  data_end_date: string | null;
};

export type Mailbox = {
  provider: string;
  provider_label: string;
  username: string;
  host: string;
  folder: string | null;
  last_synced_at: string | null;
  last_error: string | null;
  last_counts: Record<string, number>;
};

export type SmsSync = {
  cursor_ms: number | null;
  backfill_start_ms: number;
  last_sync_at: string | null;
  last: Record<string, number>;
  totals: Record<string, number>;
  device: { manufacturer?: string; sdk?: number } | null;
};

export type Source = {
  kind: "sms" | "email";
  title: string;
  status: "not_connected" | "active" | "paused" | "revoked";
  purposes: string[];
  backfill_months: number | null;
  granted_at: string | null;
  last_ingest_at: string | null;
  counts: Record<string, number>;
  notice_current?: boolean;
  sync?: SmsSync;
  mailbox?: Mailbox | null;
};

export type Notice = {
  kind: string;
  version: string;
  title: string;
  reads: string[];
  never_reads: string[];
  stores: string[];
  never: string[];
  purposes: Record<string, string>;
  hash: string;
};

export type Job = { id: number; kind: string; status: string; progress: number; message: string | null; result: unknown; error: string | null };

export type Projection = { date: string; p10: number; p50: number; p90: number };

export type Insight = { id: number; kind: string; severity: number; title: string; body: string; link: string | null };

export type AnomalyGroup = { transaction: Txn; detectors: string[]; explanations: string[]; severity: "low" | "medium" | "high"; ids: number[] };

export type Dashboard = {
  preparing: boolean;
  has_data: boolean;
  months_of_data: number;
  kpis: {
    balance: number | null;
    balance_known: boolean;
    income_month: number;
    spend_month: number;
    spend_last_month: number;
    savings_rate_last_month: number;
    safe_basis: "balance" | "wants" | "none" | null;
    safe_to_spend: number | null;
    safe_to_spend_total: number | null;
    wants_left: number | null;
    buffer: number | null;
    net_next_30: number | null;
    lowest_30: { amount: number; date: string } | null;
  };
  accounts: { id: number; name: string; kind: string; balance: number | null; balance_source: string }[];
  cashflow: { month: string; income: number; spend: number; invested: number; savings_rate: number }[];
  balance: { history: { date: string; balance: number }[]; projection: Projection[] };
  categories: { category: string; amount: number }[];
  anomalies: AnomalyGroup[];
  insights: Insight[];
  upcoming: { date: string; name: string; amount: number; category: string; source: string }[];
  wishlist: { id: number; tier: string; title: string; price: number | null; reason: string }[];
  sources: { kind: string; title: string; status: string; last_ingest_at: string | null }[];
  budgets: { id: number; category: string; icon: string; budget: number; spent: number; pct: number; pace_pct: number; over_pace: boolean; over: boolean }[];
};

export type Tier = "buy_now" | "goal" | "save_up" | "not_now" | "needs_price";

export type WishItem = {
  id: number;
  text: string;
  price: number | null;
  price_source: "manual" | "link" | null;
  max_price: number | null;
  url: string | null;
  store: string | null;
  image_url: string | null;
  fetch_status: string | null;
  fetch_note: string | null;
  last_checked_at: string | null;
  created_at: string;
  active: boolean;
  history: { date: string; price: number }[];
  tier: Tier;
  goal_id: number | null;
  months: number | null;
  monthly: number | null;
  impact: { lowest_before: number; lowest_after: number; date: string; buffer: number; stays_above_buffer: boolean } | null;
  reasons: string[];
};

export type AffordSnapshot = {
  income: number;
  committed: number;
  essential: number;
  goals: number;
  surplus: number;
  buffer: number;
  emergency_target: number;
  liquid: number;
  dues_before_income: number;
  next_income: string | null;
  forecast_low: number | null;
  safe_to_spend: number;
  wants_budget: number;
  wants_spent: number;
  wants_left: number;
  wants_known: boolean;
  spendable: number;
  emergency_ok: boolean;
  income_source: "history" | "profile" | "none";
  balance_known: boolean;
  months_of_data: number;
  explain: string[];
};

export type Verdict = { tier: "buy_now" | "save_up" | "not_now"; months: number | null; monthly: number | null; text: string;
  impact: { lowest_before: number; lowest_after: number; date: string; buffer: number; stays_above_buffer: boolean } | null };

export type CoachAnswer = {
  id?: number;
  text: string;
  intent: string;
  confidence: number;
  chart: { type: "bar" | "line" | "progress"; title: string; data: { label: string; value: number; low?: number; high?: number }[] } | null;
  table: Record<string, string | number>[] | null;
  links: { label: string; href?: string; ask?: string }[];
};
