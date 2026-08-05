"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid
} from "recharts";
import {
  fetchSpendingByCategory,
  fetchMonthlyTrends,
  fetchCashFlowSummary,
  fetchRecentTransactions,
  fetchBudgets,
  formatMinor,
} from "@/lib/api";

const PALETTE = ["#00e5ff", "#00ff88", "#ce82ff", "#ffc800", "#ff4b72", "#1cb0f6"];

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1 } },
};

const item = {
  hidden: { opacity: 0, scale: 0.95, y: 10 },
  show:   { opacity: 1, scale: 1, y: 0,
            transition: { type: "spring" as const, duration: 0.6, bounce: 0.3 } },
};

// All *_minor fields are integer minor units (cents); charts plot major units.
type Spending = { category: string; total_minor: number; count: number };
type Trend    = { month: string; spending_minor: number; income_minor: number };
type CashFlow = { income_minor: number; expenses_minor: number; net_minor: number; transaction_count: number; currency: string };
type Budget   = { category_id: number; category: string; amount_minor: number };
type Tx       = { id: string; description: string | null; amount_minor: number; currency: string; booked_date: string; category: string };

const toMajor = (minor: number) => minor / 100;

function ChartTip({ active, payload, label }: { active?: boolean; payload?: { color?: string; name?: string; value?: number }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass-panel" style={{ padding: "12px 16px", background: "rgba(0,0,0,0.8)" }}>
      <p style={{ color: "var(--text-secondary)", fontSize: 12, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>{label}</p>
      {payload.map((e, i) => (
        <p key={i} style={{ color: e.color || "white", fontWeight: 500, fontSize: 14 }}>
          {e.name}: ${Number(e.value).toLocaleString()}
        </p>
      ))}
    </div>
  );
}

export default function DashboardCharts() {
  const [spending, setSpending] = useState<Spending[]>([]);
  const [trends,   setTrends]   = useState<Trend[]>([]);
  const [cash,     setCash]     = useState<CashFlow | null>(null);
  const [txns,     setTxns]     = useState<Tx[]>([]);
  const [budgets,  setBudgets]  = useState<Budget[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [monthOffset, setMonthOffset] = useState(0);
  const [trendMonths, setTrendMonths] = useState(6);

  useEffect(() => {
    setLoading(true);
    (async () => {
      try {
        const [s, t, c, tx, b] = await Promise.all([
          fetchSpendingByCategory(monthOffset),
          fetchMonthlyTrends(trendMonths),
          fetchCashFlowSummary(monthOffset),
          fetchRecentTransactions(10),
          fetchBudgets(),
        ]);
        setSpending(s); setTrends(t); setCash(c); setTxns(tx); setBudgets(b);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, [monthOffset, trendMonths]);

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}>
        <div style={{ width: 40, height: 40, border: "2px solid var(--text-secondary)", borderTopColor: "var(--brand-accent)", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  const currency = cash?.currency ?? "USD";
  const income   = toMajor(cash?.income_minor   ?? 0);
  const expenses = toMajor(cash?.expenses_minor ?? 0);
  const flow     = toMajor(cash?.net_minor      ?? 0);

  const spendMap: Record<string, number> = {};
  spending.forEach(s => { spendMap[s.category] = toMajor(s.total_minor); });

  const trendData = trends.map(t => ({
    month: t.month,
    income: toMajor(t.income_minor),
    spending: toMajor(t.spending_minor),
  }));
  const pieData = spending.map(s => ({ category: s.category, total: toMajor(s.total_minor) }));

  return (
    <motion.div variants={container} initial="hidden" animate="show" style={{ display: "flex", flexDirection: "column", gap: 24 }}>

      {/* Month Selector */}
      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 12 }}>
        <button
          className="sleek-button secondary"
          onClick={() => setMonthOffset(p => Math.min(p + 1, 11))}
        >
          &larr; Prev
        </button>
        <div className="sleek-text" style={{ fontSize: 14, minWidth: 120, textAlign: "center", textTransform: "uppercase", letterSpacing: "1px" }}>
          {monthOffset === 0 ? "This Month" : monthOffset === 1 ? "Last Month" : `${monthOffset} Months Ago`}
        </div>
        <button
          className="sleek-button secondary"
          onClick={() => setMonthOffset(p => Math.max(p - 1, 0))}
          disabled={monthOffset === 0}
          style={{ opacity: monthOffset === 0 ? 0.5 : 1 }}
        >
          Next &rarr;
        </button>
      </div>

      {/* Metrics Row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 24 }}>
        <motion.div variants={item} className="glass-panel" style={{ padding: 24 }}>
          <p style={{ color: "var(--text-secondary)", fontSize: 12, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>Total Income</p>
          <h3 className="sleek-text" style={{ fontSize: 32, color: "var(--text-primary)" }}>${income.toLocaleString()}</h3>
        </motion.div>

        <motion.div variants={item} className="glass-panel" style={{ padding: 24 }}>
          <p style={{ color: "var(--text-secondary)", fontSize: 12, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>Total Spent</p>
          <h3 className="sleek-text" style={{ fontSize: 32, color: "var(--text-primary)" }}>${expenses.toLocaleString()}</h3>
        </motion.div>

        <motion.div variants={item} className="glass-panel" style={{ padding: 24 }}>
          <p style={{ color: "var(--text-secondary)", fontSize: 12, textTransform: "uppercase", letterSpacing: "1px", marginBottom: 8 }}>Net Cash Flow</p>
          <h3 className="sleek-text" style={{ fontSize: 32, color: flow >= 0 ? "var(--brand-success)" : "var(--brand-error)" }}>
            {flow >= 0 ? "+" : "-"}${Math.abs(flow).toLocaleString()}
          </h3>
        </motion.div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>

        {/* Monthly Trends */}
        <motion.div variants={item} className="glass-panel" style={{ padding: "24px 24px 16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
            <h3 className="sleek-text" style={{ fontSize: 18 }}>Cash Flow Trends</h3>
            <div style={{ display: "flex", gap: 8 }}>
              {[1, 3, 6].map(m => (
                <button
                  key={m}
                  onClick={() => setTrendMonths(m)}
                  className={`sleek-button ${trendMonths === m ? "primary" : "secondary"}`}
                  style={{ padding: "4px 12px", fontSize: 12 }}
                >
                  {m}M
                </button>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={trendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="gInc" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--brand-success)" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="var(--brand-success)" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gExp" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--brand-error)" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="var(--brand-error)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="month" tick={{ fill: "var(--text-secondary)", fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 12 }} axisLine={false} tickLine={false} tickFormatter={v => `$${v}`} width={60} />
              <Tooltip content={<ChartTip />} cursor={{ stroke: 'rgba(255,255,255,0.1)', strokeWidth: 1 }} />
              <Area type="monotone" dataKey="income" stroke="var(--brand-success)" strokeWidth={2} fill="url(#gInc)" name="Income" />
              <Area type="monotone" dataKey="spending" stroke="var(--brand-error)" strokeWidth={2} fill="url(#gExp)" name="Spending" />
            </AreaChart>
          </ResponsiveContainer>
        </motion.div>

        {/* Spending Distribution */}
        <motion.div variants={item} className="glass-panel" style={{ padding: "24px 24px 16px" }}>
          <h3 className="sleek-text" style={{ fontSize: 18, marginBottom: 24 }}>Spending Distribution</h3>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={70}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="total"
                  stroke="none"
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={PALETTE[index % PALETTE.length]} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTip />} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
             <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 260, color: "var(--text-secondary)" }}>No data</div>
          )}
        </motion.div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>

        {/* Budget Goals */}
        <motion.div variants={item} className="glass-panel" style={{ padding: 24 }}>
          <h3 className="sleek-text" style={{ fontSize: 18, marginBottom: 24 }}>Budget Utilization</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {budgets.length === 0 && (
              <p style={{ color: "var(--text-secondary)", fontSize: 14 }}>No budgets set for this month.</p>
            )}
            {budgets.map((b, i) => {
              const budget = toMajor(b.amount_minor);
              const spent = spendMap[b.category] ?? 0;
              const pct = budget > 0 ? Math.round((spent / budget) * 100) : 0;
              const isOver = spent > budget;
              const color = isOver ? "var(--brand-error)" : "var(--brand-accent)";

              return (
                <div key={b.category_id} style={{ display: "grid", gridTemplateColumns: "1fr", gap: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ fontSize: 14, textTransform: "capitalize", color: "var(--text-primary)" }}>{b.category}</span>
                    <span style={{ fontSize: 14, color: isOver ? "var(--brand-error)" : "var(--text-secondary)" }}>
                      ${spent.toLocaleString()} / ${budget.toLocaleString()}
                    </span>
                  </div>
                  <div style={{ height: 6, background: "rgba(255,255,255,0.1)", borderRadius: 4, overflow: "hidden" }}>
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(pct, 100)}%` }}
                      transition={{ type: "spring", bounce: 0, delay: i * 0.1 }}
                      style={{ height: "100%", background: color, borderRadius: 4 }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </motion.div>

        {/* Activity Feed */}
        <motion.div variants={item} className="glass-panel" style={{ padding: 24 }}>
          <h3 className="sleek-text" style={{ fontSize: 18, marginBottom: 24 }}>Recent Transactions</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {txns.slice(0, 7).map((tx, i) => (
              <motion.div key={tx.id} initial={{ x: -10, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ delay: 0.1 + i * 0.05 }}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "12px 16px", borderRadius: 8, background: "rgba(255,255,255,0.02)",
                  border: "1px solid rgba(255,255,255,0.05)"
                }}>
                <div>
                  <p style={{ color: "var(--text-primary)", fontSize: 14, fontWeight: 500 }}>{tx.description ?? "(no description)"}</p>
                  <p style={{ color: "var(--text-secondary)", fontSize: 12, textTransform: "capitalize" }}>{tx.category} • {new Date(tx.booked_date).toLocaleDateString()}</p>
                </div>
                <div style={{
                  fontSize: 14, fontWeight: 500,
                  color: tx.amount_minor > 0 ? "var(--brand-success)" : "var(--text-primary)"
                }}>
                  {tx.amount_minor > 0 ? "+" : ""}{formatMinor(tx.amount_minor, tx.currency || currency)}
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>

    </motion.div>
  );
}
