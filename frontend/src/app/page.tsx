"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import dynamic from "next/dynamic";
import { addTransaction, loginUser, registerUser } from "@/lib/api";
import Hero3DBackground from "@/components/Hero3DBackground";
import LogoIcon from "@/components/LogoIcon";

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
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [userId, setUserId] = useState("");
  const [username, setUsername] = useState("player1");
  const [isProfileHovered, setIsProfileHovered] = useState(false);
  
  const [tab, setTab] = useState<Tab>("dashboard");
  const [showAddLog, setShowAddLog] = useState(false);
  const [showBankLink, setShowBankLink] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [formData, setFormData] = useState({ merchant: "", amount: "", category: "food" });
  const [loginData, setLoginData] = useState({ username: "player1", password: "password" });
  const [authError, setAuthError] = useState("");

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    try {
      let res;
      if (authMode === "login") {
        res = await loginUser(loginData);
      } else {
        res = await registerUser(loginData);
      }
      setUserId(res.user_id);
      setUsername(res.username);
      setIsLoggedIn(true);
    } catch (err: any) {
      setAuthError(err.message || "An error occurred");
    }
  };

  const handleLogout = () => {
    setIsLoggedIn(false);
    setUserId("");
    setUsername("");
    setTab("dashboard");
  };

  const handleAddLog = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.merchant || !formData.amount) return;
    try {
      await addTransaction(userId, {
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
      <div style={{ background: "var(--bg-app)", minHeight: "100vh", width: "100vw", overflowX: "hidden" }}>
        
        {/* Fixed 3D WebGL Background (Higgsfield Style) */}
        <div style={{ position: "fixed", top: 0, left: 0, width: "100vw", height: "100vh", zIndex: 0 }}>
          <Hero3DBackground />
        </div>
        
        {/* Scrollable Content Overlay */}
        <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column" }}>
          
          {/* Hero / Login Section */}
          <div style={{ display: "flex", height: "100vh", width: "100%", maxWidth: 1200, margin: "0 auto", padding: 40, alignItems: "center", gap: 80 }}>
            
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
                <LogoIcon size={32} color="var(--brand-accent)" />
                <span className="sleek-text" style={{ fontSize: 20, letterSpacing: "4px", textTransform: "uppercase", fontWeight: 500 }}>Finlytics</span>
              </div>
              <h1 className="sleek-text" style={{ fontSize: 72, marginBottom: 24, lineHeight: 1.1 }}>
                Intelligence for <br/>
                <span style={{ color: "var(--brand-accent)" }}>Your Wealth.</span>
              </h1>
              <p style={{ color: "var(--text-secondary)", fontSize: 20, maxWidth: 460, lineHeight: 1.6 }}>
                A sophisticated, AI-driven financial platform that adapts to your portfolio. Experience private-banking level insights with absolute clarity.
              </p>
            </div>

          <div className="glass-panel" style={{ padding: 48, width: 440 }}>
            <h2 className="sleek-text" style={{ fontSize: 28, marginBottom: 32, fontWeight: 500 }}>
              {authMode === "login" ? "Welcome back" : "Create account"}
            </h2>
            
            <form onSubmit={handleAuth} style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              <input 
                required 
                value={loginData.username} 
                onChange={e => setLoginData({...loginData, username: e.target.value})} 
                placeholder="Username" 
                className="sleek-input"
              />
              <input 
                required 
                type="password"
                value={loginData.password} 
                onChange={e => setLoginData({...loginData, password: e.target.value})} 
                placeholder="Password" 
                className="sleek-input"
              />
              {authError && <p style={{ color: "var(--brand-error)", fontSize: 14 }}>{authError}</p>}
              <button type="submit" className="sleek-button primary" style={{ padding: 16, fontSize: 16, marginTop: 8 }}>
                {authMode === "login" ? "Sign In" : "Register"}
              </button>
            </form>
            
            <p style={{ marginTop: 32, fontSize: 14, color: "var(--text-secondary)", textAlign: "center" }}>
              {authMode === "login" ? "Don't have an account? " : "Already have an account? "}
              <button 
                onClick={() => setAuthMode(m => m === "login" ? "register" : "login")}
                style={{ background: "none", border: "none", color: "var(--text-primary)", cursor: "pointer", textDecoration: "underline", textUnderlineOffset: 4 }}
              >
                {authMode === "login" ? "Register here" : "Sign in"}
              </button>
            </p>
          </div>
          </div>

          {/* Product Feature Sections (Scroll down) */}
          <div style={{ width: "100%", maxWidth: 1200, margin: "0 auto", padding: "120px 40px", display: "flex", flexDirection: "column", gap: 160 }}>
            
            <div style={{ display: "flex", alignItems: "center", gap: 80 }}>
              <div className="glass-panel" style={{ flex: 1, height: 400, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(204, 163, 94, 0.05)" }}>
                <LogoIcon size={120} color="var(--brand-accent)" />
              </div>
              <div style={{ flex: 1 }}>
                <h2 className="sleek-text" style={{ fontSize: 40, marginBottom: 24 }}>
                  <span style={{ color: "var(--brand-accent)" }}>01.</span> Unprecedented Clarity
                </h2>
                <p style={{ fontSize: 18, color: "var(--text-secondary)", lineHeight: 1.7 }}>
                  Our proprietary engine strips away the noise. By combining real-time ledger sync with beautiful, instantaneous WebGL visualizations, you see exactly where your capital is flowing at any given millisecond.
                </p>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 80, flexDirection: "row-reverse" }}>
              <div className="glass-panel" style={{ flex: 1, height: 400, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(255, 255, 255, 0.02)" }}>
                 <div style={{ width: 120, height: 120, borderRadius: "50%", border: "2px solid var(--text-primary)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <div style={{ width: 60, height: 60, borderRadius: "50%", background: "var(--text-primary)" }} />
                 </div>
              </div>
              <div style={{ flex: 1 }}>
                <h2 className="sleek-text" style={{ fontSize: 40, marginBottom: 24 }}>
                  <span style={{ color: "var(--brand-accent)" }}>02.</span> Autonomous Intelligence
                </h2>
                <p style={{ fontSize: 18, color: "var(--text-secondary)", lineHeight: 1.7 }}>
                  Forget manual categorization. Your personal AI agent continuously analyzes transaction streams, flags anomalies, and dynamically rebalances your predictive budget targets, allowing you to remain completely hands-off.
                </p>
              </div>
            </div>

          </div>

          <footer style={{ padding: "60px 40px", borderTop: "1px solid rgba(255,255,255,0.05)", textAlign: "center", color: "var(--text-sidebar)", fontSize: 14 }}>
             &copy; {new Date().getFullYear()} Finlytics. All rights reserved.
          </footer>
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
              className="glass-panel" style={{ padding: 40, width: 440 }}
            >
              <h2 className="sleek-text" style={{ fontSize: 24, marginBottom: 24 }}>Add Transaction</h2>
              <form onSubmit={handleAddLog} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div>
                  <label style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8, display: "block", textTransform: "uppercase", letterSpacing: "0.05em" }}>Merchant Name</label>
                  <input required value={formData.merchant} onChange={e => setFormData({ ...formData, merchant: e.target.value })} className="sleek-input" style={{ width: "100%" }} placeholder="e.g. Starbucks" />
                </div>
                <div>
                  <label style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8, display: "block", textTransform: "uppercase", letterSpacing: "0.05em" }}>Amount ($)</label>
                  <input required type="number" step="0.01" value={formData.amount} onChange={e => setFormData({ ...formData, amount: e.target.value })} className="sleek-input" style={{ width: "100%" }} placeholder="e.g. 5.50" />
                </div>
                <div>
                  <label style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 8, display: "block", textTransform: "uppercase", letterSpacing: "0.05em" }}>Category</label>
                  <select value={formData.category} onChange={e => setFormData({ ...formData, category: e.target.value })} className="sleek-input" style={{ width: "100%" }}>
                    <option value="food">Food</option>
                    <option value="transport">Transport</option>
                    <option value="shopping">Shopping</option>
                    <option value="utilities">Utilities</option>
                    <option value="entertainment">Entertainment</option>
                    <option value="health">Health</option>
                    <option value="travel">Travel</option>
                    <option value="income">Income</option>
                  </select>
                </div>
                <div style={{ display: "flex", gap: 12, marginTop: 24 }}>
                  <button type="button" className="sleek-button secondary" onClick={() => setShowAddLog(false)} style={{ flex: 1 }}>Cancel</button>
                  <button type="submit" className="sleek-button primary" style={{ flex: 1 }}>Save Log</button>
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
              className="glass-panel" style={{ padding: 40, width: 400, textAlign: "center" }}
            >
              <h2 className="sleek-text" style={{ fontSize: 24, marginBottom: 8 }}>Link Bank</h2>
              <p style={{ color: "var(--text-secondary)", marginBottom: 32, fontSize: 14 }}>Secure connection via Plaid</p>
              
              {isSyncing ? (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{ padding: 40 }}>
                  <div style={{ width: 40, height: 40, border: "2px solid var(--text-secondary)", borderTopColor: "var(--brand-accent)", borderRadius: "50%", margin: "0 auto 16px", animation: "spin 1s linear infinite" }} />
                  <p style={{ color: "var(--text-primary)" }}>Syncing data...</p>
                  <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
                </motion.div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <button onClick={handleLinkBank} className="sleek-button secondary" style={{ padding: "16px 20px", display: "flex", justifyContent: "space-between" }}>
                    <span>Chase</span> <span>→</span>
                  </button>
                  <button onClick={handleLinkBank} className="sleek-button secondary" style={{ padding: "16px 20px", display: "flex", justifyContent: "space-between" }}>
                    <span>Bank of America</span> <span>→</span>
                  </button>
                  <button onClick={handleLinkBank} className="sleek-button secondary" style={{ padding: "16px 20px", display: "flex", justifyContent: "space-between" }}>
                    <span>Wells Fargo</span> <span>→</span>
                  </button>
                  <button type="button" className="sleek-button" onClick={() => setShowBankLink(false)} style={{ marginTop: 16 }}>Cancel</button>
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Sidebar (Sleek Dark Style) ────────────────────── */}
      <nav style={{
        width: 260,
        backgroundColor: "var(--bg-sidebar)",
        color: "white",
        display: "flex",
        flexDirection: "column",
        padding: "32px 24px",
        flexShrink: 0,
        borderRight: "1px solid rgba(255,255,255,0.05)",
        zIndex: 50,
      }}>
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 64 }}>
          <LogoIcon size={32} color="var(--brand-accent)" />
          <div>
            <h1 className="sleek-text" style={{ fontSize: 18, letterSpacing: "4px", fontWeight: 500 }}>
              FINLYTICS
            </h1>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: 1 }}>
          <p style={{ fontSize: 11, textTransform: "uppercase", color: "var(--text-sidebar)", letterSpacing: "0.1em", marginBottom: 12, paddingLeft: 12 }}>
            Overview
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
                
                <span className="sleek-text" style={{ textTransform: "capitalize", position: "relative", zIndex: 1, fontSize: 14 }}>
                  {t}
                </span>

                {isActive && (
                  <motion.div
                    layoutId="sidebar-active"
                    transition={{ type: "spring", bounce: 0, duration: 0.3 }}
                    style={{
                      position: "absolute",
                      left: 0, top: "25%", bottom: "25%", width: 2,
                      background: "var(--brand-accent)",
                    }}
                  />
                )}
              </button>
            );
          })}
        </div>

        {/* Bottom Status Profile with Hover Logout */}
        <div 
          onMouseEnter={() => setIsProfileHovered(true)}
          onMouseLeave={() => setIsProfileHovered(false)}
          style={{ 
            position: "relative",
            background: "rgba(255,255,255,0.02)", 
            borderRadius: 12, 
            padding: 16,
            display: "flex", alignItems: "center", gap: 12,
            border: "1px solid rgba(255,255,255,0.05)",
            cursor: "pointer",
            transition: "all 0.2s ease"
          }}
        >
          {isProfileHovered ? (
            <button 
              onClick={handleLogout}
              style={{ width: "100%", height: "100%", background: "transparent", border: "none", color: "var(--brand-error)", fontWeight: 500, fontSize: 14, cursor: "pointer", padding: "10px 0" }}
            >
              Log Out
            </button>
          ) : (
            <>
              <div style={{ width: 32, height: 32, borderRadius: "50%", background: "var(--text-secondary)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <div style={{ width: 12, height: 12, borderRadius: "50%", background: "var(--bg-sidebar)" }} />
              </div>
              <div>
                <p className="sleek-text" style={{ fontSize: 14 }}>{username}</p>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
                  <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--brand-success)", boxShadow: "0 0 8px var(--brand-success)" }} />
                  <span style={{ fontSize: 11, color: "var(--text-sidebar)" }}>Secure Session</span>
                </div>
              </div>
            </>
          )}
        </div>
      </nav>

      {/* ── Main Content Area ──────────────────────────────── */}
      <main style={{ flex: 1, overflow: "hidden", position: "relative", padding: "24px" }}>
        
        {/* Top Header */}
        <header style={{ 
          display: "flex", justifyContent: "space-between", alignItems: "center", 
          marginBottom: 32, padding: "0 16px" 
        }}>
          <h2 className="sleek-text" style={{ fontSize: 24, color: "var(--text-primary)" }}>
            {tab === "dashboard" ? "Overview" : "Intelligence"}
          </h2>
          <div style={{ display: "flex", gap: 12 }}>
            <button 
              className="sleek-button secondary" 
              onClick={() => alert("No new notifications at this time.")}
            >
              Alerts
            </button>
            <button 
              className="sleek-button secondary" 
              onClick={() => setShowBankLink(true)}
            >
              Link Bank
            </button>
            <button 
              className="sleek-button primary" 
              onClick={() => setShowAddLog(true)}
            >
              Add Entry
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
                <DashboardCharts userId={userId} />
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
                <ChatPanel userId={userId} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
