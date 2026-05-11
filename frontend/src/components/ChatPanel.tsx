"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { streamAgentQuery, AgentEvent } from "@/lib/api";

interface Msg {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  tools?: { tool: string }[];
  ts: Date;
}

const msgAnim = {
  enter:   { opacity: 0, scale: 0.8, y: 20 },
  visible: { opacity: 1, scale: 1, y: 0, transition: { type: "spring" as const, duration: 0.5, bounce: 0.5 } },
  exit:    { opacity: 0, scale: 0.8, y: -20, transition: { duration: 0.2 } },
};

const PROMPTS = [
  "Summarise my last 30 days 📅",
  "Which categories am I overspending? 🚨",
  "Find any unusual transactions 🕵️‍♂️",
  "What's my savings rate this month? 💰",
];

export default function ChatPanel() {
  const [msgs, setMsgs] = useState<Msg[]>([{
    id: "sys",
    role: "system",
    content: "Hi there! I'm your AI helper. 🤖 Ask me anything about your money quests!",
    ts: new Date(),
  }]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLInputElement>(null);

  const scrollDown = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);
  useEffect(() => { scrollDown(); }, [msgs, streaming, scrollDown]);

  const send = async (text: string) => {
    if (!text.trim() || streaming) return;
    const userMsg: Msg = { id: `u${Date.now()}`, role: "user", content: text.trim(), ts: new Date() };
    setMsgs(p => [...p, userMsg]);
    setInput("");
    setStreaming(true);
    setActiveTools([]);

    const tools: { tool: string }[] = [];
    let answer = "";

    try {
      for await (const evt of streamAgentQuery(userMsg.content, sessionId)) {
        const e = evt as AgentEvent;
        if (e.event === "session")     setSessionId(e.data as string);
        if (e.event === "tool_call")   { const d = e.data as { tool: string }; tools.push(d); setActiveTools(p => [...p, d.tool]); }
        if (e.event === "tool_result") setActiveTools(p => p.slice(1));
        if (e.event === "answer")      answer = e.data as string;
        if (e.event === "error")       answer = `Oops! Error: ${e.data} 😵`;
      }
    } catch (err) {
      answer = `Connection error: ${err instanceof Error ? err.message : "Unknown"} 📡`;
    }

    setMsgs(p => [...p, {
      id: `a${Date.now()}`, role: "assistant",
      content: answer, tools: tools.length ? tools : undefined, ts: new Date(),
    }]);
    setStreaming(false);
    setActiveTools([]);
    inputRef.current?.focus();
  };

  const fmt = (n: string) => n.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>

      {/* ── Messages ── */}
      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 16, padding: "16px 8px 32px", scrollbarWidth: "none" }}>
        <AnimatePresence initial={false}>
          {msgs.map(m => (
            <motion.div
              key={m.id}
              variants={msgAnim}
              initial="enter" animate="visible" exit="exit"
              style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start", alignItems: "flex-end", gap: 8 }}
            >
              {m.role !== "user" && (
                <div style={{ width: 36, height: 36, borderRadius: "50%", background: "var(--brand-blue)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, flexShrink: 0, boxShadow: "0 4px 0 var(--brand-blue-shadow)" }}>
                  🤖
                </div>
              )}
              
              <div className="bubbly-card" style={{
                maxWidth: "75%",
                padding: "14px 18px",
                borderRadius: m.role === "user" ? "24px 24px 4px 24px" : "24px 24px 24px 4px",
                background: m.role === "user" ? "var(--brand-green)" : "white",
                border: "2px solid #e5e5e5",
                boxShadow: m.role === "user" ? "0 4px 0 var(--brand-green-shadow)" : "0 4px 0 #e5e5e5",
                color: m.role === "user" ? "white" : "var(--text-primary)",
              }}>
                {/* Tool pills */}
                {m.tools && m.tools.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
                    {m.tools.map((t, i) => (
                      <span key={i} style={{
                        fontSize: 11, fontWeight: 800, textTransform: "uppercase",
                        letterSpacing: "0.5px", padding: "4px 10px", borderRadius: 12,
                        background: "#f0f0f5",
                        color: "var(--brand-purple)",
                        display: "inline-flex", alignItems: "center", gap: 6,
                        border: "2px solid #e0e0ea"
                      }}>
                        ⚙️ {fmt(t.tool)}
                      </span>
                    ))}
                  </div>
                )}
                <p style={{
                  fontSize: 16, lineHeight: 1.5, whiteSpace: "pre-wrap", fontWeight: 600
                }}>
                  {m.content}
                </p>
              </div>

              {m.role === "user" && (
                <div style={{ width: 36, height: 36, borderRadius: "50%", background: "var(--gradient-hot)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, flexShrink: 0, boxShadow: "0 4px 0 #e03b5d" }}>
                  😎
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Streaming indicator */}
        <AnimatePresence>
          {streaming && (
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={{ type: "spring", bounce: 0.5 }}
              style={{ display: "flex", alignItems: "flex-end", gap: 8 }}
            >
              <div style={{ width: 36, height: 36, borderRadius: "50%", background: "var(--brand-blue)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, flexShrink: 0, boxShadow: "0 4px 0 var(--brand-blue-shadow)" }}>
                🤖
              </div>
              <div className="bubbly-card" style={{
                padding: "14px 20px", borderRadius: "24px 24px 24px 4px",
                display: "flex", alignItems: "center", gap: 12,
                border: "2px solid #e5e5e5", boxShadow: "0 4px 0 #e5e5e5"
              }}>
                {activeTools.length > 0 ? (
                  <>
                    <span className="animate-bouncy" style={{ fontSize: 20 }}>⚙️</span>
                    <span style={{ fontSize: 14, fontWeight: 700, color: "var(--brand-purple)" }}>
                      {fmt(activeTools[activeTools.length - 1] ?? "")}
                    </span>
                  </>
                ) : (
                  <div style={{ display: "flex", gap: 6, alignItems: "center", height: 24 }}>
                    <div className="animate-bouncy" style={{ width: 10, height: 10, borderRadius: "50%", background: "var(--brand-blue)", animationDelay: "0ms" }} />
                    <div className="animate-bouncy" style={{ width: 10, height: 10, borderRadius: "50%", background: "var(--brand-blue)", animationDelay: "150ms" }} />
                    <div className="animate-bouncy" style={{ width: 10, height: 10, borderRadius: "50%", background: "var(--brand-blue)", animationDelay: "300ms" }} />
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Suggested prompts */}
        {msgs.length <= 1 && !streaming && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 12, marginTop: 16, maxWidth: "80%", alignSelf: "center" }}>
            {PROMPTS.map((q, i) => (
              <motion.button
                key={i}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ type: "spring", bounce: 0.5, delay: 0.1 * i }}
                onClick={() => send(q)}
                className="bubbly-card"
                style={{
                  textAlign: "left", padding: "16px 20px",
                  borderRadius: 20, fontSize: 15, fontWeight: 700,
                  color: "var(--brand-blue)", cursor: "pointer",
                  border: "2px solid #e5e5e5", boxShadow: "0 4px 0 #e5e5e5"
                }}
              >
                {q}
              </motion.button>
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Input bar ── */}
      <form
        onSubmit={e => { e.preventDefault(); send(input); }}
        style={{
          padding: "16px 0 24px",
          display: "flex",
          gap: 12,
        }}
      >
        <input
          ref={inputRef}
          id="chat-input"
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Ask me anything! 💬"
          disabled={streaming}
          style={{
            flex: 1, padding: "16px 20px",
            borderRadius: 20, fontSize: 16, fontWeight: 600,
            background: "white",
            border: "2px solid #e5e5e5",
            boxShadow: "0 4px 0 #e5e5e5",
            color: "var(--text-primary)",
            outline: "none",
            transition: "all 0.2s ease",
            fontFamily: "var(--font-body)",
          }}
          onFocus={e => { e.currentTarget.style.borderColor = "var(--brand-blue)"; e.currentTarget.style.boxShadow = "0 4px 0 var(--brand-blue-shadow)"; }}
          onBlur={e  => { e.currentTarget.style.borderColor = "#e5e5e5"; e.currentTarget.style.boxShadow = "0 4px 0 #e5e5e5"; }}
        />
        <button
          className="bubbly-button"
          id="send-button"
          type="submit"
          disabled={streaming || !input.trim()}
          style={{ height: "100%", padding: "0 24px" }}
        >
          {streaming ? "⏳" : "Send 🚀"}
        </button>
      </form>
    </div>
  );
}
