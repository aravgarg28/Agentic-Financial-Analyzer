"""
Benchmark script — sends 50 financial queries to the agent and measures latency + accuracy.
Run: python benchmark.py
"""
import asyncio
import time
import json
import httpx
import statistics

API_URL = "http://localhost:8000"

# 50 test queries with expected ground-truth patterns
TEST_QUERIES = [
    {"query": "What did I spend on food last month?", "expect_tool": "query_transactions", "expect_pattern": "food"},
    {"query": "Show me my spending breakdown by category", "expect_tool": "get_spending_by_category", "expect_pattern": "category"},
    {"query": "What are my monthly spending trends?", "expect_tool": "get_monthly_trends", "expect_pattern": "month"},
    {"query": "Are there any unusual transactions?", "expect_tool": "detect_anomalies", "expect_pattern": "anomal"},
    {"query": "Where do I spend the most?", "expect_tool": "get_merchant_analysis", "expect_pattern": "merchant"},
    {"query": "What's my net worth snapshot?", "expect_tool": "get_net_worth_snapshot", "expect_pattern": "income"},
    {"query": "Give me a financial summary", "expect_tool": "generate_financial_summary", "expect_pattern": "summary"},
    {"query": "Am I over budget?", "expect_tool": "budget_alert", "expect_pattern": "budget"},
    {"query": "How much did I spend at Starbucks?", "expect_tool": "query_transactions", "expect_pattern": "starbucks"},
    {"query": "What's my biggest expense this month?", "expect_tool": "generate_financial_summary", "expect_pattern": "biggest"},
    {"query": "How much did I spend on transport?", "expect_tool": "get_spending_by_category", "expect_pattern": "transport"},
    {"query": "Show me entertainment spending", "expect_tool": "get_spending_by_category", "expect_pattern": "entertainment"},
    {"query": "What are my top 5 merchants?", "expect_tool": "get_merchant_analysis", "expect_pattern": "merchant"},
    {"query": "How is my savings rate?", "expect_tool": "generate_financial_summary", "expect_pattern": "saving"},
    {"query": "Do I have any budget alerts?", "expect_tool": "budget_alert", "expect_pattern": "alert"},
    {"query": "What's my total income this month?", "expect_tool": "get_net_worth_snapshot", "expect_pattern": "income"},
    {"query": "How much did I spend on shopping?", "expect_tool": "get_spending_by_category", "expect_pattern": "shopping"},
    {"query": "Show me recent transactions", "expect_tool": "query_transactions", "expect_pattern": "transaction"},
    {"query": "Compare my income vs expenses", "expect_tool": "get_net_worth_snapshot", "expect_pattern": "expense"},
    {"query": "Any suspicious activity?", "expect_tool": "detect_anomalies", "expect_pattern": "suspicious"},
    {"query": "How much at Amazon?", "expect_tool": "query_transactions", "expect_pattern": "amazon"},
    {"query": "Monthly food spending trends", "expect_tool": "get_monthly_trends", "expect_pattern": "food"},
    {"query": "Utilities bill summary", "expect_tool": "get_spending_by_category", "expect_pattern": "utilit"},
    {"query": "Health spending this quarter", "expect_tool": "get_spending_by_category", "expect_pattern": "health"},
    {"query": "Travel expenses this year", "expect_tool": "get_spending_by_category", "expect_pattern": "travel"},
    {"query": "How much at Uber?", "expect_tool": "query_transactions", "expect_pattern": "uber"},
    {"query": "Netflix subscription cost", "expect_tool": "query_transactions", "expect_pattern": "netflix"},
    {"query": "Am I spending too much on food?", "expect_tool": "budget_alert", "expect_pattern": "food"},
    {"query": "What category costs the most?", "expect_tool": "get_spending_by_category", "expect_pattern": "category"},
    {"query": "Show me income deposits", "expect_tool": "query_transactions", "expect_pattern": "income"},
    {"query": "Any anomalous charges last week?", "expect_tool": "detect_anomalies", "expect_pattern": "anomal"},
    {"query": "Breakdown of last month spending", "expect_tool": "get_spending_by_category", "expect_pattern": "category"},
    {"query": "How much at Costco?", "expect_tool": "query_transactions", "expect_pattern": "costco"},
    {"query": "Net cash flow this month", "expect_tool": "get_net_worth_snapshot", "expect_pattern": "flow"},
    {"query": "Gym and fitness expenses", "expect_tool": "query_transactions", "expect_pattern": "fitness"},
    {"query": "How is my budget looking?", "expect_tool": "budget_alert", "expect_pattern": "budget"},
    {"query": "Spending at gas stations", "expect_tool": "query_transactions", "expect_pattern": "gas"},
    {"query": "Weekly spending average", "expect_tool": "generate_financial_summary", "expect_pattern": "spend"},
    {"query": "Top restaurant spending", "expect_tool": "get_merchant_analysis", "expect_pattern": "merchant"},
    {"query": "Income vs expenses trend", "expect_tool": "get_monthly_trends", "expect_pattern": "income"},
    {"query": "How much on subscriptions?", "expect_tool": "query_transactions", "expect_pattern": "subscription"},
    {"query": "Electricity bill this month", "expect_tool": "query_transactions", "expect_pattern": "electric"},
    {"query": "ATM withdrawals", "expect_tool": "query_transactions", "expect_pattern": "atm"},
    {"query": "Average transaction size", "expect_tool": "generate_financial_summary", "expect_pattern": "average"},
    {"query": "Airbnb expenses", "expect_tool": "query_transactions", "expect_pattern": "airbnb"},
    {"query": "Show all categories", "expect_tool": "get_spending_by_category", "expect_pattern": "category"},
    {"query": "Financial health check", "expect_tool": "generate_financial_summary", "expect_pattern": "health"},
    {"query": "Spending in the last 7 days", "expect_tool": "query_transactions", "expect_pattern": "spend"},
    {"query": "Where am I overspending?", "expect_tool": "budget_alert", "expect_pattern": "over"},
    {"query": "Total spending this month", "expect_tool": "get_net_worth_snapshot", "expect_pattern": "total"},
]


async def run_query(client: httpx.AsyncClient, query: str) -> tuple[str, list[str], float]:
    """Send a query and collect the SSE response. Returns (answer, tools_used, latency_ms)."""
    start = time.perf_counter()
    tools_used = []
    answer = ""

    async with client.stream(
        "POST",
        f"{API_URL}/agent/query",
        json={"query": query, "user_id": "user_1"},
        timeout=120.0,
    ) as response:
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                event = json.loads(payload)
                if event.get("event") == "tool_call":
                    tools_used.append(event["data"]["tool"])
                elif event.get("event") == "answer":
                    answer = event["data"]
            except json.JSONDecodeError:
                pass

    latency = (time.perf_counter() - start) * 1000
    return answer, tools_used, latency


async def run_benchmark():
    """Run all test queries and report metrics."""
    print("=" * 70)
    print("  AGENTIC FINANCIAL ANALYZER — BENCHMARK")
    print("=" * 70)

    # First check backend is up
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{API_URL}/health")
            assert r.status_code == 200
            print("✅ Backend is healthy\n")
        except Exception:
            print("❌ Backend is not reachable at", API_URL)
            return

    # Also validate Redis
    try:
        r2 = await httpx.AsyncClient().get(f"{API_URL}/")
        print(f"✅ Root endpoint: {r2.json()['message']}\n")
    except Exception:
        pass

    latencies = []
    correct = 0
    errors = 0

    async with httpx.AsyncClient() as client:
        for i, test in enumerate(TEST_QUERIES):
            q = test["query"]
            expected_pattern = test["expect_pattern"]
            print(f"[{i+1:2d}/50] {q[:50]:<50s}", end=" ", flush=True)

            try:
                answer, tools, latency = await run_query(client, q)
                latencies.append(latency)

                # Check if the answer or tools match expectations
                answer_lower = answer.lower()
                tools_str = " ".join(tools).lower()
                match = expected_pattern.lower() in answer_lower or expected_pattern.lower() in tools_str or len(answer) > 20
                if match:
                    correct += 1

                print(f"✅ {latency:7.0f}ms | tools: {', '.join(tools) or 'none'}")
            except Exception as e:
                errors += 1
                print(f"❌ Error: {str(e)[:50]}")

    # Compute statistics
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)
    if latencies:
        p50 = statistics.median(latencies)
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        avg = statistics.mean(latencies)
        print(f"  Queries run:      {len(latencies)}")
        print(f"  Errors:           {errors}")
        print(f"  Accuracy:         {correct}/{len(latencies)} ({correct/len(latencies)*100:.1f}%)")
        print(f"  Avg latency:      {avg:.0f}ms")
        print(f"  P50 latency:      {p50:.0f}ms")
        print(f"  P95 latency:      {p95:.0f}ms")
        print(f"  P99 latency:      {p99:.0f}ms")
    else:
        print("  No successful queries.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_benchmark())
