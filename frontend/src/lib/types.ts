// Shapes returned by the FastAPI backend (only the fields the UI uses).

export type Category = { id: number; name: string; group: string; kind: string; icon: string; essential: boolean; discretionary: boolean };
export type Account = { id: number; name: string; institution: string; kind: string; mask: string | null };

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

export type SimOutcome = {
  status: string;
  detail: string;
  kind: string | null;
  confidence: number | null;
  fields: Record<string, { value: unknown; confidence: number }> | null;
  parser: string | null;
  transaction: Txn | null;
};

export type Job = { id: number; kind: string; status: string; progress: number; message: string | null; result: unknown; error: string | null };

export type Projection = { date: string; p10: number; p50: number; p90: number };

export type Insight = { id: number; kind: string; severity: number; title: string; body: string; link: string | null };

export type AnomalyGroup = { transaction: Txn; detectors: string[]; explanations: string[]; severity: "low" | "medium" | "high"; ids: number[] };

export type Dashboard = {
  preparing: boolean;
  kpis: {
    balance: number;
    income_month: number;
    spend_month: number;
    spend_last_month: number;
    savings_rate_last_month: number;
    safe_to_spend: number | null;
    safe_to_spend_total: number | null;
    wants_left: number | null;
    net_next_30: number | null;
    lowest_30: { amount: number; date: string } | null;
  };
  accounts: { name: string; kind: string; balance: number }[];
  cashflow: { month: string; income: number; spend: number; invested: number; savings_rate: number }[];
  balance: { history: { date: string; balance: number }[]; projection: Projection[] };
  categories: { category: string; amount: number }[];
  anomalies: AnomalyGroup[];
  insights: Insight[];
  upcoming: { date: string; name: string; amount: number; category: string; source: string }[];
  picks: { id: number; tier: string; title: string; price: number; reason: string }[];
  sources: { kind: string; title: string; status: string; last_ingest_at: string | null }[];
  budgets: { id: number; category: string; icon: string; budget: number; spent: number; pct: number; pace_pct: number; over_pace: boolean; over: boolean }[];
};

export type Product = {
  id: number;
  title: string;
  brand: string;
  category: string;
  price: number;
  mrp: number;
  discount_pct: number;
  rating: number;
  rating_count: number;
  store: string;
  url: string;
  image: string | null;
  tags: string[];
  history: { date: string; price: number }[];
  low_30: number;
  median_30: number;
};

export type Pick = {
  id: number;
  tier: "buy_now" | "goal" | "save_up";
  score: number;
  reasons: string[];
  impact: { lowest_before?: number; lowest_after?: number; buffer?: number; stays_above_buffer?: boolean; months?: number | null; monthly?: number | null };
  interest: string;
  status: string;
  product: Product;
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
  emergency_ok: boolean;
  origins: string[];
  explain: string[];
  complete: boolean;
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
