/**
 * API client for the Financial Analyzer backend.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Analytics REST Endpoints ──────────────────────────────────────────────────

export async function fetchSpendingByCategory(days = 30) {
  const res = await fetch(`${API_URL}/analytics/spending-by-category?days=${days}`);
  if (!res.ok) throw new Error("Failed to fetch spending data");
  const json = await res.json();
  return json.data;
}

export async function fetchMonthlyTrends(months = 6) {
  const res = await fetch(`${API_URL}/analytics/monthly-trends?months=${months}`);
  if (!res.ok) throw new Error("Failed to fetch monthly trends");
  const json = await res.json();
  return json.data;
}

export async function fetchNetWorth(days = 30) {
  const res = await fetch(`${API_URL}/analytics/net-worth?days=${days}`);
  if (!res.ok) throw new Error("Failed to fetch net worth");
  const json = await res.json();
  return json.data;
}

export async function fetchTopMerchants(days = 30, limit = 10) {
  const res = await fetch(`${API_URL}/analytics/top-merchants?days=${days}&limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch merchants");
  const json = await res.json();
  return json.data;
}

export async function fetchBudgetAlerts(days = 30) {
  const res = await fetch(`${API_URL}/analytics/budget-alerts?days=${days}`);
  if (!res.ok) throw new Error("Failed to fetch budget alerts");
  const json = await res.json();
  return json.data;
}

export async function fetchRecentTransactions(limit = 20) {
  const res = await fetch(`${API_URL}/analytics/recent-transactions?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to fetch transactions");
  const json = await res.json();
  return json.data;
}

// ── Agent SSE Streaming ───────────────────────────────────────────────────────

export interface AgentEvent {
  event: "session" | "tool_call" | "tool_result" | "answer" | "error";
  data: string | Record<string, unknown>;
}

export async function* streamAgentQuery(
  query: string,
  sessionId?: string
): AsyncGenerator<AgentEvent> {
  const res = await fetch(`${API_URL}/agent/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      user_id: "user_1",
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
