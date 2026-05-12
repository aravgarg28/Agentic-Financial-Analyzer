"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { streamAgentQuery, AgentEvent } from "@/lib/api";
import LogoIcon from "@/components/LogoIcon";

interface Msg {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  tools?: { tool: string }[];
  ts: Date;
}

const msgAnim = {
  enter:   { opacity: 0, scale: 0.95, y: 10 },
  visible: { opacity: 1, scale: 1, y: 0, transition: { type: "spring" as const, duration: 0.5, bounce: 0.3 } },
  exit:    { opacity: 0, scale: 0.95, y: -10, transition: { duration: 0.2 } },
};

const PROMPTS = [
  "Summarize my last 30 days",
  "Which categories am I overspending?",
  "Find any unusual transactions",
  "What's my savings rate this month?",
];

export default function ChatPanel({ userId }: { userId: string }) {
  const [msgs, setMsgs] = useState<Msg[]>([{
    id: "sys",
    role: "system",
    content: "Intelligence system active. How can I assist with your financial analysis today?",
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
      for await (const evt of streamAgentQuery(userId, userMsg.content, sessionId)) {
        const e = evt as AgentEvent;
        if (e.event === "session")     setSessionId(e.data as string);
        if (e.event === "tool_call")   { const d = e.data as { tool: string }; tools.push(d); setActiveTools(p => [...p, d.tool]); }
        if (e.event === "tool_result") setActiveTools(p => p.slice(1));
        if (e.event === "answer")      answer = e.data as string;
        if (e.event === "error")       answer = `Error: ${e.data}`;
      }
    } catch (err) {
      answer = `Connection error: ${err instanceof Error ? err.message : "Unknown"}`;
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
      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 24, padding: "16px 8px 32px", scrollbarWidth: "none" }}>
        <AnimatePresence initial={false}>
          {msgs.map(m => (
            <motion.div
              key={m.id}
              variants={msgAnim}
              initial="enter" animate="visible" exit="exit"
              style={{ display: "flex", justifyContent: m.role === "user" ? "flex-end" : "flex-start", alignItems: "flex-end", gap: 12 }}
            >
              {m.role !== "user" && (
                <div style={{ width: 32, height: 32, borderRadius: "50%", background: "rgba(204, 163, 94, 0.1)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, border: "1px solid var(--brand-accent)" }}>
                  <LogoIcon size={16} color="var(--brand-accent)" />
                </div>
              )}
              
              <div className="glass-panel" style={{
                maxWidth: "75%",
                padding: "16px 20px",
                borderRadius: m.role === "user" ? "20px 20px 4px 20px" : "20px 20px 20px 4px",
                background: m.role === "user" ? "rgba(255, 255, 255, 0.05)" : "var(--bg-card)",
                border: m.role === "user" ? "1px solid rgba(255, 255, 255, 0.1)" : "var(--glass-border)",
                color: "var(--text-primary)",
              }}>
                {/* Tool pills */}
                {m.tools && m.tools.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
                    {m.tools.map((t, i) => (
                      <span key={i} style={{
                        fontSize: 10, fontWeight: 600, textTransform: "uppercase",
                        letterSpacing: "0.5px", padding: "4px 10px", borderRadius: 12,
                        background: "rgba(255,255,255,0.05)",
                        color: "var(--text-secondary)",
                        display: "inline-flex", alignItems: "center", gap: 6,
                        border: "1px solid rgba(255,255,255,0.1)"
                      }}>
                        {fmt(t.tool)}
                      </span>
                    ))}
                  </div>
                )}
                <p style={{
                  fontSize: 15, lineHeight: 1.6, whiteSpace: "pre-wrap", fontWeight: 400
                }}>
                  {m.content}
                </p>
              </div>

              {m.role === "user" && (
                <div style={{ width: 32, height: 32, borderRadius: "50%", background: "var(--text-secondary)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <div style={{ width: 12, height: 12, borderRadius: "50%", background: "var(--bg-app)" }} />
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Streaming indicator */}
        <AnimatePresence>
          {streaming && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ type: "spring", bounce: 0.3 }}
              style={{ display: "flex", alignItems: "flex-end", gap: 12 }}
            >
              <div style={{ width: 32, height: 32, borderRadius: "50%", background: "rgba(204, 163, 94, 0.1)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, border: "1px solid var(--brand-accent)" }}>
                <LogoIcon size={16} color="var(--brand-accent)" />
              </div>
              <div className="glass-panel" style={{
                padding: "16px 20px", borderRadius: "20px 20px 20px 4px",
                display: "flex", alignItems: "center", gap: 12,
              }}>
                {activeTools.length > 0 ? (
                  <>
                    <div style={{ width: 12, height: 12, border: "2px solid var(--text-secondary)", borderTopColor: "var(--brand-accent)", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
                    <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text-secondary)" }}>
                      {fmt(activeTools[activeTools.length - 1] ?? "")}
                    </span>
                  </>
                ) : (
                  <div style={{ display: "flex", gap: 6, alignItems: "center", height: 20 }}>
                    <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--text-secondary)", animation: "pulse 1.5s infinite" }} />
                    <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--text-secondary)", animation: "pulse 1.5s infinite 0.2s" }} />
                    <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--text-secondary)", animation: "pulse 1.5s infinite 0.4s" }} />
                    <style>{`@keyframes pulse { 0%, 100% { opacity: 0.3; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1); } }`}</style>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Suggested prompts */}
        {msgs.length <= 1 && !streaming && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 12, marginTop: 24, maxWidth: "80%", alignSelf: "center" }}>
            {PROMPTS.map((q, i) => (
              <motion.button
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ type: "spring", bounce: 0.3, delay: 0.1 * i }}
                onClick={() => send(q)}
                className="glass-panel"
                style={{
                  textAlign: "left", padding: "16px 20px",
                  borderRadius: 12, fontSize: 14, fontWeight: 500,
                  color: "var(--text-primary)", cursor: "pointer",
                  transition: "all 0.2s ease"
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--brand-accent)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.08)"; }}
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
          placeholder="Ask me anything..."
          disabled={streaming}
          className="sleek-input"
          style={{
            flex: 1, padding: "16px 20px",
            borderRadius: 12, fontSize: 15,
          }}
        />
        <button
          className="sleek-button primary"
          id="send-button"
          type="submit"
          disabled={streaming || !input.trim()}
          style={{ height: "100%", padding: "0 24px" }}
        >
          {streaming ? <div style={{ width: 16, height: 16, border: "2px solid #000", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite" }} /> : "Send"}
        </button>
      </form>
    </div>
  );
}
