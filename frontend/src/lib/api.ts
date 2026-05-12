/**
 * API client for the Financial Analyzer backend.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Auth Endpoints ────────────────────────────────────────────────────────────

export async function loginUser(data: { username: string; password: string }) {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Login failed");
  }
  return res.json();
}

export async function registerUser(data: { username: string; password: string }) {
  const res = await fetch(`${API_URL}/auth/register`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Registration failed");
  }
  return res.json();
}

// ── Analytics REST Endpoints ──────────────────────────────────────────────────

export async function fetchSpendingByCategory(userId: string, monthOffset = 0) {
  const res = await fetch(`${API_URL}/analytics/spending-by-category?user_id=${userId}&month_offset=${monthOffset}`);
  if (!res.ok) throw new Error("Failed to fetch spending data");
  const json = await res.json();
  return json.data;
}

export async function fetchMonthlyTrends(userId: string, months = 6) {
  const res = await fetch(`${API_URL}/analytics/monthly-trends?user_id=${userId}&months=${months}`);
  if (!res.ok) throw new Error("Failed to fetch monthly trends");
  const json = await res.json();
  return json.data;
}

export async function fetchNetWorth(userId: string, monthOffset = 0) {
  const res = await fetch(`${API_URL}/analytics/net-worth?user_id=${userId}&month_offset=${monthOffset}`);
  if (!res.ok) throw new Error("Failed to fetch net worth");
  const json = await res.json();
  return json.data;
}

export async function fetchTopMerchants(userId: string, monthOffset = 0, limit = 10) {
  const res = await fetch(`${API_URL}/analytics/top-merchants?user_id=${userId}&month_offset=${monthOffset}&limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch merchants");
  const json = await res.json();
  return json.data;
}

export async function fetchBudgetAlerts(userId: string, days = 30) {
  const res = await fetch(`${API_URL}/analytics/budget-alerts?user_id=${userId}&days=${days}`);
  if (!res.ok) throw new Error("Failed to fetch budget alerts");
  const json = await res.json();
  return json.data;
}

export async function fetchRecentTransactions(userId: string, limit = 20) {
  const res = await fetch(`${API_URL}/analytics/recent-transactions?user_id=${userId}&limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch transactions");
  const json = await res.json();
  return json.data;
}

export async function addTransaction(userId: string, data: { merchant: string; amount: number; category: string; description?: string }) {
  const res = await fetch(`${API_URL}/analytics/transactions?user_id=${userId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to add transaction");
  return res.json();
}

export async function fetchBudgets(userId: string) {
  const res = await fetch(`${API_URL}/analytics/budgets?user_id=${userId}`);
  if (!res.ok) throw new Error("Failed to fetch budgets");
  const json = await res.json();
  return json.data;
}

// ── Agent SSE Streaming ───────────────────────────────────────────────────────

export interface AgentEvent {
  event: "session" | "tool_call" | "tool_result" | "answer" | "error";
  data: string | Record<string, unknown>;
}

export async function* streamAgentQuery(
  userId: string,
  query: string,
  sessionId?: string
): AsyncGenerator<AgentEvent> {
  const res = await fetch(`${API_URL}/agent/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      user_id: userId,
      session_id: sessionId || null,
    }),
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
        const parsed = JSON.parse(payload) as AgentEvent;
        yield parsed;
      } catch {
        // skip malformed lines
      }
    }
  }
}
