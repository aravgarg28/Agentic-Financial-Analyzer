"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import {
  fetchSpendingByCategory,
  fetchMonthlyTrends,
  fetchNetWorth,
  fetchTopMerchants,
  fetchRecentTransactions,
} from "@/lib/api";

const PALETTE = ["#ff4b72", "#ff8f3d", "#58cc02", "#1cb0f6", "#ce82ff", "#ffc800"];

const BUDGETS: Record<string, number> = {
  food: 1500, transport: 2200, shopping: 4500,
  utilities: 1500, entertainment: 600, health: 1800, travel: 7000,
};

const CATEGORY_EMOJIS: Record<string, string> = {
  food: "🍔", transport: "🚕", shopping: "🛍️", utilities: "⚡",
  entertainment: "🍿", health: "💊", travel: "✈️"
};

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1 } },
};

const item = {
  hidden: { opacity: 0, scale: 0.8, y: 20 },
  show:   { opacity: 1, scale: 1, y: 0,
            transition: { type: "spring" as const, duration: 0.6, bounce: 0.5 } },
};

type Spending = { category: string; total: number; count: number };
type Trend    = { month: string; spending: number; income: number };
type NetWorth = { total_income: number; total_expenses: number; net_flow: number; total_transactions: number };
type Merchant = { merchant: string; total: number; visit_count: number };
type Tx       = { id: number; merchant: string; amount: number; category: string; timestamp: string };

function ChartTip({ active, payload, label }: { active?: boolean; payload?: any[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bubbly-card" style={{ padding: "12px 16px", border: "none", boxShadow: "0 8px 24px rgba(0,0,0,0.15)" }}>
      <p style={{ color: "var(--text-secondary)", fontWeight: 700, marginBottom: 8 }}>{label}</p>
      {payload.map((e, i) => (
        <p key={i} style={{ color: e.color, fontWeight: 800, fontSize: 16 }}>
          {e.name}: ${Number(e.value).toLocaleString()}
        </p>
      ))}
    </div>
  );
}

export default function DashboardCharts() {
  const [spending, setSpending] = useState<Spending[]>([]);
  const [trends,   setTrends]   = useState<Trend[]>([]);
  const [net,      setNet]      = useState<NetWorth | null>(null);
  const [merchants,setMerchants]= useState<Merchant[]>([]);
  const [txns,     setTxns]     = useState<Tx[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [monthOffset, setMonthOffset] = useState(0);

  useEffect(() => {
    setLoading(true);
    (async () => {
      try {
        const [s, t, n, m, tx] = await Promise.all([
          fetchSpendingByCategory(monthOffset),
          fetchMonthlyTrends(6),
          fetchNetWorth(monthOffset),
          fetchTopMerchants(monthOffset, 8),
          fetchRecentTransactions(10),
        ]);
        setSpending(s); setTrends(t); setNet(n); setMerchants(m); setTxns(tx);
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, [monthOffset]);

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}>
        <div className="animate-bouncy" style={{ fontSize: 64 }}>🪙</div>
      </div>
    );
  }

  const income   = Number(net?.total_income   ?? 0);
  const expenses = Number(net?.total_expenses ?? 0);
  const flow     = Number(net?.net_flow       ?? 0);

  const spendMap: Record<string, number> = {};
  spending.forEach(s => { spendMap[s.category] = Number(s.total); });

  return (
    <motion.div variants={container} initial="hidden" animate="show" style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      
      {/* Month Selector */}
      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 12 }}>
        <button 
          className="bubbly-button secondary" 
          onClick={() => setMonthOffset(p => Math.min(p + 1, 11))}
          style={{ padding: "8px 16px", borderRadius: 12, fontSize: 14 }}
        >
          ⬅️ Prev Month
        </button>
        <div style={{ fontWeight: 800, color: "var(--text-primary)", fontSize: 16, minWidth: 140, textAlign: "center" }}>
          {monthOffset === 0 ? "This Month 📅" : monthOffset === 1 ? "Last Month 📅" : `${monthOffset} Months Ago 📅`}
        </div>
        <button 
          className="bubbly-button secondary" 
          onClick={() => setMonthOffset(p => Math.max(p - 1, 0))}
          disabled={monthOffset === 0}
          style={{ padding: "8px 16px", borderRadius: 12, fontSize: 14, opacity: monthOffset === 0 ? 0.5 : 1 }}
        >
          Next Month ➡️
        </button>
      </div>

      {/* Overview Stats Row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 24 }}>
        
        {/* Income Card (Hot gradient) */}
        <motion.div variants={item} className="bubbly-card" style={{ padding: 24, background: "var(--gradient-hot)", color: "white", border: "none" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <p style={{ fontWeight: 700, opacity: 0.9, marginBottom: 8 }}>Total Income 💰</p>
              <h3 className="bubbly-text" style={{ fontSize: 36, lineHeight: 1 }}>${(income / 1000).toFixed(1)}k</h3>
            </div>
            <div style={{ background: "rgba(255,255,255,0.2)", borderRadius: 12, padding: "8px 12px", fontWeight: 800 }}>+12%</div>
          </div>
        </motion.div>

        {/* Expenses Card (Cool gradient) */}
        <motion.div variants={item} className="bubbly-card" style={{ padding: 24, background: "var(--gradient-cool)", color: "white", border: "none" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <p style={{ fontWeight: 700, opacity: 0.9, marginBottom: 8 }}>Total Spent 💸</p>
              <h3 className="bubbly-text" style={{ fontSize: 36, lineHeight: 1 }}>${(expenses / 1000).toFixed(1)}k</h3>
            </div>
            <div style={{ background: "rgba(255,255,255,0.2)", borderRadius: 12, padding: "8px 12px", fontWeight: 800 }}>-5%</div>
          </div>
        </motion.div>

        {/* Net Flow Card (White bubbly) */}
        <motion.div variants={item} className="bubbly-card" style={{ padding: 24, display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ fontSize: 48 }} className="animate-bouncy">
            {flow >= 0 ? "🤑" : "😰"}
          </div>
          <div>
            <p style={{ color: "var(--text-secondary)", fontWeight: 700, marginBottom: 4 }}>Net Flow</p>
            <h3 className="bubbly-text" style={{ fontSize: 32, color: flow >= 0 ? "var(--brand-green)" : "var(--brand-pink)" }}>
              {flow >= 0 ? "+" : ""}${(flow / 1000).toFixed(1)}k
            </h3>
          </div>
        </motion.div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        
        {/* Monthly Trends */}
        <motion.div variants={item} className="bubbly-card" style={{ padding: "24px 24px 16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
            <h3 className="bubbly-text" style={{ fontSize: 20 }}>Level Progress 📈</h3>
            <button className="bubbly-button secondary" style={{ padding: "6px 12px", fontSize: 12, borderRadius: 12 }}>6 Months</button>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={trends}>
              <defs>
                <linearGradient id="gInc" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--brand-green)" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="var(--brand-green)" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gExp" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--brand-pink)" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="var(--brand-pink)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="month" tick={{ fill: "var(--text-secondary)", fontWeight: 700, fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "var(--text-secondary)", fontWeight: 700, fontSize: 12 }} axisLine={false} tickLine={false} tickFormatter={v => `$${v/1000}k`} width={40} />
              <Tooltip content={<ChartTip />} cursor={{ stroke: 'rgba(0,0,0,0.1)', strokeWidth: 2 }} />
              <Area type="monotone" dataKey="income" stroke="var(--brand-green)" strokeWidth={4} fill="url(#gInc)" name="Income" />
              <Area type="monotone" dataKey="spending" stroke="var(--brand-pink)" strokeWidth={4} fill="url(#gExp)" name="Spending" />
            </AreaChart>
          </ResponsiveContainer>
        </motion.div>

        {/* Budget Goals */}
        <motion.div variants={item} className="bubbly-card" style={{ padding: 24 }}>
          <h3 className="bubbly-text" style={{ fontSize: 20, marginBottom: 20 }}>Budget Quests 🎯</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {Object.entries(BUDGETS).map(([cat, budget], i) => {
              const spent = spendMap[cat] ?? 0;
              const pct = Math.round((spent / budget) * 100);
              const isOver = spent > budget;
              const color = isOver ? "var(--brand-pink)" : (pct > 80 ? "var(--brand-orange)" : "var(--brand-blue)");
              
              return (
                <div key={cat} style={{ display: "grid", gridTemplateColumns: "32px 1fr", gap: 16, alignItems: "center" }}>
                  <div style={{ fontSize: 24, background: "#f0f0f5", width: 40, height: 40, borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center" }}>
                    {CATEGORY_EMOJIS[cat] || "✨"}
                  </div>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                      <span style={{ fontWeight: 800, textTransform: "capitalize", color: "var(--text-primary)" }}>{cat}</span>
                      <span style={{ fontWeight: 800, color: isOver ? "var(--brand-pink)" : "var(--text-secondary)" }}>
                        {isOver ? `Over by $${(spent - budget).toLocaleString()}! 😱` : `${pct}%`}
                      </span>
                    </div>
                    {/* Chunky Progress Bar */}
                    <div style={{ height: 16, background: "#f0f0f5", borderRadius: 99, overflow: "hidden", position: "relative" }}>
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.min(pct, 100)}%` }}
                        transition={{ type: "spring", bounce: 0.4, delay: i * 0.1 }}
                        style={{ height: "100%", background: color, borderRadius: 99, position: "relative" }}
                      >
                        {/* Inner highlight for 3D effect */}
                        <div style={{ position: "absolute", top: 2, left: 6, right: 6, height: 4, background: "rgba(255,255,255,0.3)", borderRadius: 99 }} />
                      </motion.div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </motion.div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        {/* Spending by Category (Donut Chart) */}
        <motion.div variants={item} className="bubbly-card" style={{ padding: "24px 24px 16px" }}>
          <h3 className="bubbly-text" style={{ fontSize: 20, marginBottom: 24 }}>Loot Distribution ⚔️</h3>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={spending}
                cx="50%"
                cy="50%"
                innerRadius={65}
                outerRadius={95}
                paddingAngle={4}
                dataKey="total"
                stroke="none"
              >
                {spending.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={PALETTE[index % PALETTE.length]} />
                ))}
              </Pie>
              <Tooltip content={<ChartTip />} />
            </PieChart>
          </ResponsiveContainer>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginTop: 16 }}>
            {spending.slice(0, 6).map((s, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ width: 12, height: 12, borderRadius: "50%", background: PALETTE[i % PALETTE.length] }} />
                  <span style={{ fontSize: 14, fontWeight: 700, color: "var(--text-secondary)", textTransform: "capitalize" }}>{s.category}</span>
                </div>
                <span style={{ fontSize: 14, fontWeight: 800, color: "var(--text-primary)" }}>${Number(s.total).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Activity Feed */}
        <motion.div variants={item} className="bubbly-card" style={{ padding: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
            <h3 className="bubbly-text" style={{ fontSize: 20 }}>Activity Feed 📜</h3>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {txns.slice(0, 5).map((tx, i) => (
              <motion.div key={tx.id} initial={{ x: -20, opacity: 0 }} animate={{ x: 0, opacity: 1 }} transition={{ delay: 0.2 + i * 0.1 }}
                style={{ 
                  display: "flex", alignItems: "center", justifyContent: "space-between", 
                  padding: "16px", borderRadius: 16, background: "#f8f8fb",
                  border: "2px solid #f0f0f5"
                }}>
                <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                  <div style={{ fontSize: 24, width: 44, height: 44, background: "white", borderRadius: 14, display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 4px 12px rgba(0,0,0,0.05)" }}>
                    {CATEGORY_EMOJIS[tx.category] || "🛍️"}
                  </div>
                  <div>
                    <p style={{ fontWeight: 800, color: "var(--text-primary)", fontSize: 15 }}>{tx.merchant}</p>
                    <p style={{ fontWeight: 600, color: "var(--text-secondary)", fontSize: 12, textTransform: "capitalize" }}>{tx.category}</p>
                  </div>
                </div>
                <div style={{ 
                  fontWeight: 800, fontSize: 16,
                  color: tx.amount > 0 ? "var(--brand-green)" : "var(--text-primary)" 
                }}>
                  {tx.amount > 0 ? "+" : ""}${Math.abs(tx.amount).toFixed(2)}
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>

    </motion.div>
  );
}
