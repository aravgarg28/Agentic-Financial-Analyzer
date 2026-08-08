/**
 * API client for the Financial Analyzer backend.
 *
 * Auth is cookie-based: the backend sets an HttpOnly session cookie on
 * login/register and resolves the tenant from it. The client therefore sends
 * NO user_id/household_id — identity is never client-supplied (SEC-01/02).
 * Every request uses `credentials: "include"` so the cookie rides along, and
 * mutating requests carry the `X-Requested-With` header the backend's CSRF
 * guard requires. Money is integer minor units end-to-end (FIN-01).
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const JSON_HEADERS = { "Content-Type": "application/json" };
// Present on mutating requests; the backend rejects cross-site POSTs lacking it.
const CSRF_HEADERS = { ...JSON_HEADERS, "X-Requested-With": "XMLHttpRequest" };

async function getJson(path: string) {
  const res = await fetch(`${API_URL}${path}`, { credentials: "include" });
  if (!res.ok) throw new Error(`Request failed: ${path} (${res.status})`);
  return res.json();
}

async function mutate(path: string, method: string, body?: unknown) {
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: CSRF_HEADERS,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Request failed: ${path} (${res.status})`);
  }
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface Me {
  user_public_id: string;
  email: string;
  household_public_id: string;
  role: string;
}

export async function loginUser(data: { email: string; password: string }) {
  return mutate("/auth/login", "POST", data);
}

export async function registerUser(data: { email: string; password: string }) {
  return mutate("/auth/register", "POST", data);
}

export async function logoutUser() {
  return mutate("/auth/logout", "POST");
}

/** Returns the current profile, or null if not authenticated. */
export async function fetchMe(): Promise<Me | null> {
  const res = await fetch(`${API_URL}/auth/me`, { credentials: "include" });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error("Failed to fetch profile");
  return res.json();
}

// ── Insights (dashboard) ────────────────────────────────────────────────────
// All amounts returned are integer minor units; format with formatMinor().

export async function fetchSpendingByCategory(monthOffset = 0) {
  return (await getJson(`/insights/spending-by-category?month_offset=${monthOffset}`)).data;
}

export async function fetchMonthlyTrends(months = 6) {
  return (await getJson(`/insights/monthly-trends?months=${months}`)).data;
}

/** Cash-flow summary for a month (income/expenses/net over the period —
 * this is a flow, not a net-worth balance; FIN-07). */
export async function fetchCashFlowSummary(monthOffset = 0) {
  return getJson(`/insights/cash-flow-summary?month_offset=${monthOffset}`);
}

export async function fetchTopMerchants(monthOffset = 0, limit = 10) {
  return (await getJson(`/insights/top-merchants?month_offset=${monthOffset}&limit=${limit}`)).data;
}

export async function fetchBudgetAlerts(monthOffset = 0) {
  return (await getJson(`/insights/budget-alerts?month_offset=${monthOffset}`)).data;
}

export async function fetchRecentTransactions(limit = 20) {
  return (await getJson(`/insights/recent-transactions?limit=${limit}`)).data;
}

export async function fetchBudgets(month?: string) {
  const q = month ? `?month=${month}` : "";
  return (await getJson(`/insights/budgets${q}`)).data;
}

export async function upsertBudget(data: {
  category_id: number;
  amount_minor: number;
  month?: string;
}) {
  return mutate("/insights/budgets", "PUT", data);
}

// ── Ledger: accounts & institutions (T-060) ──────────────────────────────────

export interface Account {
  id: string;
  name: string;
  type: string;
  tracking_mode: string;
  currency: string;
  current_balance_minor: number | null;
  archived: boolean;
  institution: { id: string; name: string } | null;
}

export interface Institution {
  id: string;
  name: string;
  kind: string | null;
}

export const ACCOUNT_TYPES = [
  "checking",
  "savings",
  "credit_card",
  "loan",
  "investment",
  "property",
  "cash",
  "other",
] as const;

export async function fetchAccounts(includeArchived = false): Promise<Account[]> {
  const q = includeArchived ? "?include_archived=true" : "";
  return (await getJson(`/ledger/accounts${q}`)).data;
}

export async function createAccount(data: {
  name: string;
  type: string;
  tracking_mode?: string;
  currency?: string;
  institution_id?: string | null;
  opening_balance_minor?: number | null;
}): Promise<Account> {
  return mutate("/ledger/accounts", "POST", data);
}

export async function updateAccount(
  publicId: string,
  data: {
    name?: string;
    institution_id?: string | null;
    clear_institution?: boolean;
    current_balance_minor?: number | null;
  }
): Promise<Account> {
  return mutate(`/ledger/accounts/${publicId}`, "PATCH", data);
}

export async function archiveAccount(publicId: string): Promise<Account> {
  return mutate(`/ledger/accounts/${publicId}/archive`, "POST");
}

export async function unarchiveAccount(publicId: string): Promise<Account> {
  return mutate(`/ledger/accounts/${publicId}/unarchive`, "POST");
}

export async function fetchInstitutions(): Promise<Institution[]> {
  return (await getJson("/ledger/institutions")).data;
}

export async function createInstitution(data: {
  name: string;
  kind?: string | null;
}): Promise<Institution> {
  return mutate("/ledger/institutions", "POST", data);
}

export async function addTransaction(data: {
  account_id: string;
  amount_minor: number;
  booked_date: string;
  description?: string;
  category_id?: number;
}) {
  return mutate("/ledger/transactions", "POST", data);
}

// ── Formatting ──────────────────────────────────────────────────────────────

/** Convert integer minor units to a display string, e.g. -1234 -> "-$12.34". */
export function formatMinor(minor: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(
    minor / 100
  );
}

// ── Agent SSE Streaming ───────────────────────────────────────────────────────

export interface AgentEvent {
  event: "conversation" | "tool_call" | "tool_result" | "answer" | "error";
  data: string | Record<string, unknown>;
}

export async function* streamAgentQuery(
  query: string,
  conversationId?: string
): AsyncGenerator<AgentEvent> {
  const res = await fetch(`${API_URL}/agent/query`, {
    method: "POST",
    headers: CSRF_HEADERS,
    credentials: "include",
    body: JSON.stringify({ query, conversation_id: conversationId || null }),
  });

  if (!res.ok) throw new Error("Agent query failed");

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue;
      const payload = trimmed.slice(6);
      if (payload === "[DONE]") return;

      try {
        yield JSON.parse(payload) as AgentEvent;
      } catch {
        // skip malformed lines
      }
    }
  }
}
