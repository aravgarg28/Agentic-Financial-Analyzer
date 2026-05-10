"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import dynamic from "next/dynamic";

const ChatPanel = dynamic(() => import("@/components/ChatPanel"), { ssr: false });
const DashboardCharts = dynamic(() => import("@/components/DashboardCharts"), { ssr: false });

type Tab = "dashboard" | "chat";

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>("dashboard");

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      {/* ── Header ──────────────────────────────────────────────── */}
      <header className="shrink-0 border-b border-[var(--border-color)] bg-[var(--bg-secondary)]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center text-lg" style={{ background: "var(--gradient-blue)" }}>
              📊
            </div>
            <div>
              <h1 className="text-base font-bold gradient-text leading-tight">
                Agentic Financial Analyzer
              </h1>
              <p className="text-[10px] text-[var(--text-muted)] uppercase tracking-widest">
                AI-Powered Insights
              </p>
            </div>
          </div>

          {/* Tab switcher */}
          <div className="flex bg-[var(--bg-primary)] rounded-xl p-1 border border-[var(--border-color)]">
            {(["dashboard", "chat"] as Tab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`relative px-4 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer ${
                  activeTab === tab
                    ? "text-white"
                    : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                }`}
                id={`tab-${tab}`}
              >
                {activeTab === tab && (
                  <motion.div
                    layoutId="activeTab"
                    className="absolute inset-0 rounded-lg"
                    style={{ background: "var(--gradient-blue)" }}
                    transition={{ type: "spring", bounce: 0.2, duration: 0.5 }}
                  />
                )}
                <span className="relative z-10 capitalize">
                  {tab === "dashboard" ? "📈 Dashboard" : "💬 Chat"}
                </span>
              </button>
            ))}
          </div>

          {/* Status indicator */}
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-[var(--accent-green)] pulse-glow" />
            <span className="text-xs text-[var(--text-muted)]">Live</span>
          </div>
        </div>
      </header>

      {/* ── Content ─────────────────────────────────────────────── */}
      <main className="flex-1 overflow-hidden">
        <AnimatePresence mode="wait">
          {activeTab === "dashboard" ? (
            <motion.div
              key="dashboard"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ duration: 0.3 }}
              className="h-full overflow-y-auto"
            >
              <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
                <DashboardCharts />
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="chat"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.3 }}
              className="h-full"
            >
              <div className="max-w-3xl mx-auto h-full">
                <ChatPanel />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}
