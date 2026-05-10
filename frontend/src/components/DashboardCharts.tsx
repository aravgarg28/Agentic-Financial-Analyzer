"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from "recharts";
import {
  fetchSpendingByCategory,
  fetchMonthlyTrends,
  fetchNetWorth,
  fetchBudgetAlerts,
  fetchTopMerchants,
  fetchRecentTransactions,
} from "@/lib/api";

const CHART_COLORS = [
  "#3b82f6", "#8b5cf6", "#06b6d4", "#10b981",
  "#f59e0b", "#ef4444", "#ec4899", "#14b8a6",
];

const categoryEmojis: Record<string, string> = {
  food: "🍔", transport: "🚗", shopping: "🛍️", utilities: "⚡",
  entertainment: "🎬", health: "💊", travel: "✈️", income: "💵",
};

// ── Stat Card ────────────────────────────────────────────────────────────────

function StatCard({
  title,
  value,
  subtitle,
  color,
  delay = 0,
}: {
  title: string;
  value: string;
  subtitle?: string;
  color: string;
  delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4 }}
      className="glass-card p-5"
    >
      <p className="text-xs uppercase tracking-wider text-[var(--text-muted)] mb-1">{title}</p>
      <p className="text-2xl font-bold" style={{ color }}>
        {value}
      </p>
      {subtitle && (
        <p className="text-xs text-[var(--text-muted)] mt-1">{subtitle}</p>
      )}
    </motion.div>
  );
}

// ── Custom Tooltip ───────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ value: number; name: string; color: string }>; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[var(--bg-card)] border border-[var(--border-color)] rounded-xl px-3 py-2 shadow-xl">
      <p className="text-xs text-[var(--text-muted)] mb-1">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="text-sm font-medium" style={{ color: entry.color }}>
          {entry.name}: ${Number(entry.value).toLocaleString()}
        </p>
      ))}
    </div>
  );
}

// ── Main Dashboard ───────────────────────────────────────────────────────────

export default function DashboardCharts() {
  const [spending, setSpending] = useState<Array<{ category: string; total: number; count: number }>>([]);
  const [trends, setTrends] = useState<Array<{ month: string; spending: number; income: number }>>([]);
  const [netWorth, setNetWorth] = useState<{
    total_income: number;
    total_expenses: number;
    net_flow: number;
    total_transactions: number;
  } | null>(null);
  const [alerts, setAlerts] = useState<Array<{ category: string; spent: number; budget: number; over_by: number }>>([]);
  const [merchants, setMerchants] = useState<Array<{ merchant: string; total: number; visit_count: number }>>([]);
  const [transactions, setTransactions] = useState<Array<{ id: number; merchant: string; amount: number; category: string; timestamp: string }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [s, t, n, a, m, tx] = await Promise.all([
          fetchSpendingByCategory(180),
          fetchMonthlyTrends(6),
          fetchNetWorth(30),
          fetchBudgetAlerts(30),
          fetchTopMerchants(30, 8),
          fetchRecentTransactions(10),
        ]);
        setSpending(s);
        setTrends(t);
        setNetWorth(n);
        setAlerts(a);
        setMerchants(m);
        setTransactions(tx);
      } catch (err) {
        console.error("Failed to load analytics:", err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="space-y-4 p-1">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="shimmer h-24 rounded-2xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-5 p-1 overflow-y-auto">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          title="Income (30d)"
          value={`$${Number(netWorth?.total_income || 0).toLocaleString()}`}
          color="var(--accent-green)"
          delay={0}
        />
        <StatCard
          title="Expenses (30d)"
          value={`$${Number(netWorth?.total_expenses || 0).toLocaleString()}`}
          color="var(--accent-red)"
          delay={0.1}
        />
        <StatCard
          title="Net Flow"
          value={`${Number(netWorth?.net_flow || 0) >= 0 ? "+" : ""}$${Number(netWorth?.net_flow || 0).toLocaleString()}`}
          color={Number(netWorth?.net_flow || 0) >= 0 ? "var(--accent-green)" : "var(--accent-red)"}
          delay={0.2}
        />
        <StatCard
          title="Transactions"
          value={String(netWorth?.total_transactions || 0)}
          subtitle="Last 30 days"
          color="var(--accent-blue)"
          delay={0.3}
        />
      </div>

      {/* Budget Alerts */}
      {alerts.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card p-4"
        >
          <h3 className="text-sm font-semibold text-[var(--accent-amber)] mb-2 flex items-center gap-2">
            ⚡ Budget Alerts
          </h3>
          <div className="space-y-2">
            {alerts.map((alert, i) => (
              <div
                key={i}
                className="flex items-center justify-between text-sm bg-[var(--bg-primary)] rounded-lg px-3 py-2"
              >
                <span className="text-[var(--text-secondary)]">
                  {categoryEmojis[alert.category] || "📌"} {alert.category}
                </span>
                <span className="text-[var(--accent-red)] font-medium">
                  ${alert.spent.toLocaleString()} / ${alert.budget.toLocaleString()} (+${alert.over_by.toLocaleString()})
                </span>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Monthly Trends Chart */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass-card p-5"
      >
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">Monthly Trends</h3>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={trends}>
            <defs>
              <linearGradient id="incomeGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="spendGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
            <XAxis dataKey="month" tick={{ fill: "var(--text-muted)", fontSize: 11 }} axisLine={false} />
            <YAxis tick={{ fill: "var(--text-muted)", fontSize: 11 }} axisLine={false} tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} />
            <Tooltip content={<ChartTooltip />} />
            <Area type="monotone" dataKey="income" stroke="#10b981" fill="url(#incomeGrad)" strokeWidth={2} name="Income" />
            <Area type="monotone" dataKey="spending" stroke="#ef4444" fill="url(#spendGrad)" strokeWidth={2} name="Spending" />
          </AreaChart>
        </ResponsiveContainer>
      </motion.div>

      {/* Spending by Category */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="glass-card p-5"
      >
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-4">Spending by Category</h3>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={spending} barSize={28}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" />
            <XAxis dataKey="category" tick={{ fill: "var(--text-muted)", fontSize: 10 }} axisLine={false} />
            <YAxis tick={{ fill: "var(--text-muted)", fontSize: 11 }} axisLine={false} tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} />
            <Tooltip content={<ChartTooltip />} />
            <Bar dataKey="total" radius={[6, 6, 0, 0]} name="Spent">
              {spending.map((_entry, index) => (
                <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </motion.div>

      {/* Top Merchants */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35 }}
        className="glass-card p-5"
      >
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-3">Top Merchants (30d)</h3>
        <div className="space-y-2">
          {merchants.slice(0, 6).map((m, i) => {
            const maxTotal = merchants[0]?.total || 1;
            const pct = (Number(m.total) / Number(maxTotal)) * 100;
            return (
              <div key={i} className="relative">
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-[var(--text-secondary)]">{m.merchant}</span>
                  <span className="text-[var(--text-muted)]">${Number(m.total).toLocaleString()} ({m.visit_count}x)</span>
                </div>
                <div className="h-1.5 bg-[var(--bg-primary)] rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ delay: 0.4 + i * 0.05, duration: 0.6 }}
                    className="h-full rounded-full"
                    style={{ background: CHART_COLORS[i % CHART_COLORS.length] }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </motion.div>

      {/* Recent Transactions */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="glass-card p-5"
      >
        <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-3">Recent Transactions</h3>
        <div className="space-y-1.5">
          {transactions.slice(0, 8).map((tx, i) => (
            <div
              key={i}
              className="flex items-center justify-between text-sm py-2 px-3 rounded-lg hover:bg-[var(--bg-card-hover)] transition-colors"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span>{categoryEmojis[tx.category] || "📌"}</span>
                <span className="text-[var(--text-secondary)] truncate">{tx.merchant}</span>
              </div>
              <span
                className={`font-mono font-medium ${
                  tx.amount > 0
                    ? "text-[var(--accent-green)]"
                    : "text-[var(--accent-red)]"
                }`}
              >
                {tx.amount > 0 ? "+" : ""}${Math.abs(tx.amount).toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
