"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import dynamic from "next/dynamic";
import { addTransaction } from "@/lib/api";

const ChatPanel = dynamic(() => import("@/components/ChatPanel"), { ssr: false });
const DashboardCharts = dynamic(() => import("@/components/DashboardCharts"), { ssr: false });

type Tab = "dashboard" | "chat";

const slide = {
  enter: { opacity: 0, scale: 0.95, y: 20 },
  show:  { opacity: 1, scale: 1, y: 0, 
           transition: { type: "spring" as const, duration: 0.6, bounce: 0.4 } },
  exit:  { opacity: 0, scale: 0.95, y: -20, 
           transition: { duration: 0.2 } },
};

export default function Home() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [tab, setTab] = useState<Tab>("dashboard");
  const [showAddLog, setShowAddLog] = useState(false);
  const [showBankLink, setShowBankLink] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [formData, setFormData] = useState({ merchant: "", amount: "", category: "food" });
  const [loginData, setLoginData] = useState({ username: "player1", password: "password" });

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoggedIn(true);
  };

  const handleAddLog = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.merchant || !formData.amount) return;
    try {
      await addTransaction({
        merchant: formData.merchant,
        amount: parseFloat(formData.amount),
        category: formData.category
      });
      alert("✅ Transaction added! Reload the page to see your new stats.");
      setShowAddLog(false);
      setFormData({ merchant: "", amount: "", category: "food" });
    } catch (err) {
      alert("Error adding transaction. Please try again.");
    }
  };

  const handleLinkBank = () => {
    setIsSyncing(true);
    setTimeout(() => {
      setIsSyncing(false);
      setShowBankLink(false);
      alert("✅ Successfully synced 42 new transactions from Chase Bank via Plaid Sandbox!");
    }, 2000);
  };

  if (!isLoggedIn) {
    return (
      <div style={{ display: "flex", height: "100dvh", width: "100vw", background: "var(--bg-app)", alignItems: "center", justifyContent: "center" }}>
        <div className="bubbly-card" style={{ padding: 40, width: 400, textAlign: "center" }}>
          <div className="animate-bouncy" style={{ fontSize: 64, marginBottom: 16 }}>🎮</div>
          <h1 className="bubbly-text" style={{ fontSize: 32, marginBottom: 8 }}>Finlytics</h1>
          <p style={{ color: "var(--text-secondary)", fontWeight: 700, marginBottom: 32 }}>Level up your wealth.</p>
          
          <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <input 
              required 
              value={loginData.username} 
              onChange={e => setLoginData({...loginData, username: e.target.value})} 
              placeholder="Username" 
              style={{ width: "100%", padding: 16, borderRadius: 16, border: "2px solid #e5e5e5", fontSize: 16, outline: "none", fontWeight: 700 }} 
            />
            <input 
              required 
              type="password"
              value={loginData.password} 
              onChange={e => setLoginData({...loginData, password: e.target.value})} 
              placeholder="Password" 
              style={{ width: "100%", padding: 16, borderRadius: 16, border: "2px solid #e5e5e5", fontSize: 16, outline: "none", fontWeight: 700 }} 
            />
            <button type="submit" className="bubbly-button" style={{ padding: 16, fontSize: 18, marginTop: 8 }}>
              START GAME
            </button>
          </form>
          <p style={{ marginTop: 24, fontSize: 12, color: "var(--text-secondary)", fontWeight: 700 }}>
            Demo Account: player1 / password
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", height: "100dvh", overflow: "hidden", backgroundColor: "var(--bg-app)" }}>

      {/* ── Add Transaction Modal ── */}
      <AnimatePresence>
        {showAddLog && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <motion.div 
              initial={{ scale: 0.9, y: 20, filter: "blur(4px)" }}
              animate={{ scale: 1, y: 0, filter: "blur(0px)" }}
              exit={{ scale: 0.95, y: 10, filter: "blur(4px)", transition: { duration: 0.15 } }}
              transition={{ type: "spring", duration: 0.5, bounce: 0.4 }}
              className="bubbly-card" style={{ padding: 32, width: 400, background: "white", borderRadius: 24, boxShadow: "0 20px 40px rgba(0,0,0,0.2)" }}
            >
              <h2 className="bubbly-text" style={{ fontSize: 24, marginBottom: 24 }}>New Quest (Add Log) 📝</h2>
              <form onSubmit={handleAddLog} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div>
                  <label style={{ fontWeight: 800, fontSize: 14, color: "var(--text-secondary)", marginBottom: 8, display: "block" }}>Merchant Name</label>
                  <input required value={formData.merchant} onChange={e => setFormData({ ...formData, merchant: e.target.value })} style={{ width: "100%", padding: 12, borderRadius: 12, border: "2px solid #e5e5e5", fontSize: 16, outline: "none" }} placeholder="e.g. Starbucks" />
                </div>
                <div>
                  <label style={{ fontWeight: 800, fontSize: 14, color: "var(--text-secondary)", marginBottom: 8, display: "block" }}>Amount ($)</label>
                  <input required type="number" step="0.01" value={formData.amount} onChange={e => setFormData({ ...formData, amount: e.target.value })} style={{ width: "100%", padding: 12, borderRadius: 12, border: "2px solid #e5e5e5", fontSize: 16, outline: "none" }} placeholder="e.g. 5.50" />
                </div>
                <div>
                  <label style={{ fontWeight: 800, fontSize: 14, color: "var(--text-secondary)", marginBottom: 8, display: "block" }}>Category</label>
                  <select value={formData.category} onChange={e => setFormData({ ...formData, category: e.target.value })} style={{ width: "100%", padding: 12, borderRadius: 12, border: "2px solid #e5e5e5", fontSize: 16, outline: "none" }}>
                    <option value="food">🍔 Food</option>
                    <option value="transport">🚕 Transport</option>
                    <option value="shopping">🛍️ Shopping</option>
                    <option value="utilities">⚡ Utilities</option>
                    <option value="entertainment">🍿 Entertainment</option>
                    <option value="health">💊 Health</option>
                    <option value="travel">✈️ Travel</option>
                    <option value="income">💰 Income (Earned)</option>
                  </select>
                </div>
                <div style={{ display: "flex", gap: 12, marginTop: 16 }}>
                  <button type="button" className="bubbly-button secondary" onClick={() => setShowAddLog(false)} style={{ flex: 1, padding: "12px" }}>Cancel</button>
                  <button type="submit" className="bubbly-button" style={{ flex: 1, padding: "12px" }}>Save Log</button>
                </div>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Link Bank (Plaid) Modal ── */}
      <AnimatePresence>
        {showBankLink && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <motion.div 
              initial={{ scale: 0.9, y: 20, filter: "blur(4px)" }}
              animate={{ scale: 1, y: 0, filter: "blur(0px)" }}
              exit={{ scale: 0.95, y: 10, filter: "blur(4px)", transition: { duration: 0.15 } }}
              transition={{ type: "spring", duration: 0.5, bounce: 0.4 }}
              className="bubbly-card" style={{ padding: 32, width: 400, background: "white", borderRadius: 24, boxShadow: "0 20px 40px rgba(0,0,0,0.2)", textAlign: "center" }}
            >
              <h2 className="bubbly-text" style={{ fontSize: 24, marginBottom: 8 }}>Link Your Bank 🏦</h2>
              <p style={{ color: "var(--text-secondary)", marginBottom: 24 }}>Powered by Plaid</p>
              
              {isSyncing ? (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ padding: 40 }}>
                  <div className="animate-bouncy" style={{ fontSize: 48, marginBottom: 16 }}>🔄</div>
                  <p style={{ fontWeight: 800, color: "var(--brand-blue)" }}>Syncing transactions...</p>
                </motion.div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <button onClick={handleLinkBank} className="bubbly-button secondary" style={{ padding: 16, display: "flex", justifyContent: "space-between", fontSize: 16 }}>
                    <span>Chase</span> <span>🔵</span>
                  </button>
                  <button onClick={handleLinkBank} className="bubbly-button secondary" style={{ padding: 16, display: "flex", justifyContent: "space-between", fontSize: 16 }}>
                    <span>Bank of America</span> <span>🔴</span>
                  </button>
                  <button onClick={handleLinkBank} className="bubbly-button secondary" style={{ padding: 16, display: "flex", justifyContent: "space-between", fontSize: 16 }}>
                    <span>Wells Fargo</span> <span>🟡</span>
                  </button>
                  <button type="button" className="bubbly-button" onClick={() => setShowBankLink(false)} style={{ marginTop: 16, padding: "12px", background: "#f0f0f5", color: "var(--text-secondary)", boxShadow: "none" }}>Cancel</button>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Sidebar (Dark Gamified Style) ────────────────────── */}
      <nav style={{
        width: 280,
        backgroundColor: "var(--bg-sidebar)",
        color: "white",
        display: "flex",
        flexDirection: "column",
        padding: "32px 24px",
        flexShrink: 0,
        borderRight: "4px solid rgba(0,0,0,0.2)",
        zIndex: 50,
      }}>
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 48 }}>
          <div style={{
            width: 48, height: 48, 
            background: "var(--gradient-hot)",
            borderRadius: 16,
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 4px 12px rgba(255, 75, 114, 0.4)",
            fontSize: 24,
          }}>
            🌟
          </div>
          <div>
            <h1 className="bubbly-text" style={{ fontSize: 24, letterSpacing: "0.5px" }}>
              Finlytics
            </h1>
            <p style={{ fontSize: 13, color: "var(--text-sidebar)", fontWeight: 600 }}>
              Level up your money!
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12, flex: 1 }}>
          <p style={{ fontSize: 12, textTransform: "uppercase", color: "var(--text-sidebar)", fontWeight: 800, letterSpacing: "1px", marginBottom: 8, paddingLeft: 12 }}>
            Menu
          </p>
          
          {(["dashboard", "chat"] as Tab[]).map((t) => {
            const isActive = tab === t;
            return (
              <button
                key={t}
                onClick={() => setTab(t)}
                style={{
                  position: "relative",
                  padding: "16px 20px",
                  borderRadius: 20,
                  border: "none",
                  background: isActive ? "rgba(255,255,255,0.1)" : "transparent",
                  color: isActive ? "white" : "var(--text-sidebar)",
                  fontSize: 16,
                  fontWeight: 700,
                  textAlign: "left",
                  display: "flex", alignItems: "center", gap: 16,
                  transition: "all 0.2s ease",
                  cursor: "pointer",
                }}
                onMouseEnter={(e) => {
                  if (!isActive) e.currentTarget.style.background = "rgba(255,255,255,0.05)";
                }}
                onMouseLeave={(e) => {
                  if (!isActive) e.currentTarget.style.background = "transparent";
                }}
              >
                {/* Icons */}
                <span style={{ fontSize: 22 }}>
                  {t === "dashboard" ? "📊" : "💬"}
                </span>
                
                <span className="bubbly-text" style={{ textTransform: "capitalize", position: "relative", zIndex: 1 }}>
                  {t}
                </span>

                {isActive && (
                  <motion.div
                    layoutId="sidebar-active"
                    transition={{ type: "spring", bounce: 0.4, duration: 0.6 }}
                    style={{
                      position: "absolute",
                      left: 0, top: "20%", bottom: "20%", width: 6,
                      background: "var(--brand-pink)",
                      borderRadius: "0 8px 8px 0",
                    }}
                  />
                )}
              </button>
            );
          })}
        </div>

        {/* Bottom Status Profile */}
        <div style={{ 
          background: "rgba(255,255,255,0.05)", 
          borderRadius: 20, 
          padding: 16,
          display: "flex", alignItems: "center", gap: 12,
          border: "2px solid rgba(255,255,255,0.1)"
        }}>
          <div style={{ width: 40, height: 40, borderRadius: "50%", background: "var(--brand-blue)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20 }}>
            😎
          </div>
          <div>
            <p className="bubbly-text" style={{ fontSize: 16 }}>Player 1</p>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--brand-green)", boxShadow: "0 0 8px var(--brand-green)" }} />
              <span style={{ fontSize: 12, color: "var(--text-sidebar)", fontWeight: 700 }}>Online</span>
            </div>
          </div>
        </div>
      </nav>

      {/* ── Main Content Area ──────────────────────────────── */}
      <main style={{ flex: 1, overflow: "hidden", position: "relative", padding: "24px" }}>
        
        {/* Top Header */}
        <header style={{ 
          display: "flex", justifyContent: "space-between", alignItems: "center", 
          marginBottom: 24, padding: "0 16px" 
        }}>
          <h2 className="bubbly-text" style={{ fontSize: 32, color: "var(--text-primary)" }}>
            {tab === "dashboard" ? "My Analytics 🚀" : "AI Helper 🤖"}
          </h2>
          <div style={{ display: "flex", gap: 12 }}>
            <button 
              className="bubbly-button secondary" 
              style={{ padding: "8px 16px" }}
              onClick={() => alert("No new notifications at this time.")}
            >
              🔔
            </button>
            <button 
              className="bubbly-button secondary" 
              style={{ padding: "8px 16px" }}
              onClick={() => setShowBankLink(true)}
            >
              🔗 Link Bank
            </button>
            <button 
              className="bubbly-button" 
              style={{ padding: "8px 24px" }}
              onClick={() => setShowAddLog(true)}
            >
              + Add Log
            </button>
          </div>
        </header>

        {/* Content Wrapper */}
        <div style={{ height: "calc(100% - 80px)", overflow: "hidden", position: "relative" }}>
          <AnimatePresence mode="wait">
            {tab === "dashboard" ? (
              <motion.div
                key="dashboard"
                variants={slide}
                initial="enter"
                animate="show"
                exit="exit"
                style={{ height: "100%", overflowY: "auto", padding: "8px 16px 48px" }}
              >
                <DashboardCharts />
              </motion.div>
            ) : (
              <motion.div
                key="chat"
                variants={slide}
                initial="enter"
                animate="show"
                exit="exit"
                style={{ height: "100%", padding: "0 16px" }}
              >
                <ChatPanel />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
