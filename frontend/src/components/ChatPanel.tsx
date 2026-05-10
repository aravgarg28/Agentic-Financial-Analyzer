"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { streamAgentQuery, AgentEvent } from "@/lib/api";

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  toolCalls?: { tool: string; input: Record<string, unknown> }[];
  timestamp: Date;
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "system",
      content:
        "Hello! I'm your AI financial analyst. Ask me anything about your spending, budgets, or financial trends.",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeTools, scrollToBottom]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsStreaming(true);
    setActiveTools([]);

    const toolCalls: { tool: string; input: Record<string, unknown> }[] = [];
    let answer = "";

    try {
      for await (const event of streamAgentQuery(userMsg.content, sessionId)) {
        const evt = event as AgentEvent;
        if (evt.event === "session") {
          setSessionId(evt.data as string);
        } else if (evt.event === "tool_call") {
          const data = evt.data as { tool: string; input: Record<string, unknown> };
          toolCalls.push(data);
          setActiveTools((prev) => [...prev, data.tool]);
        } else if (evt.event === "tool_result") {
          // Tool result received — clear from active
          setActiveTools((prev) => prev.slice(1));
        } else if (evt.event === "answer") {
          answer = evt.data as string;
        } else if (evt.event === "error") {
          answer = `⚠️ Error: ${evt.data}`;
        }
      }
    } catch (err) {
      answer = `⚠️ Connection error: ${err instanceof Error ? err.message : "Unknown error"}`;
    }

    const assistantMsg: ChatMessage = {
      id: `assistant-${Date.now()}`,
      role: "assistant",
      content: answer,
      toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, assistantMsg]);
    setIsStreaming(false);
    setActiveTools([]);
    inputRef.current?.focus();
  };

  const toolIcons: Record<string, string> = {
    query_transactions: "🔍",
    get_spending_by_category: "📊",
    get_monthly_trends: "📈",
    detect_anomalies: "🚨",
    get_merchant_analysis: "🏪",
    get_net_worth_snapshot: "💰",
    generate_financial_summary: "📋",
    budget_alert: "⚡",
  };

  const suggestedQueries = [
    "What did I spend on food last month?",
    "Show me my monthly spending trends",
    "Are there any unusual transactions?",
    "Am I over budget in any category?",
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Chat messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                  msg.role === "user"
                    ? "bg-[var(--accent-blue)] text-white"
                    : msg.role === "system"
                    ? "bg-[var(--bg-card)] border border-[var(--border-color)] text-[var(--text-secondary)]"
                    : "bg-[var(--bg-card)] border border-[var(--border-color)]"
                }`}
              >
                {/* Tool calls badge */}
                {msg.toolCalls && msg.toolCalls.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {msg.toolCalls.map((tc, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-[var(--bg-primary)] border border-[var(--border-color)] text-[var(--text-muted)]"
                      >
                        {toolIcons[tc.tool] || "🔧"} {tc.tool.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                )}
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Active tool indicator */}
        {isStreaming && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex justify-start"
          >
            <div className="bg-[var(--bg-card)] border border-[var(--border-color)] rounded-2xl px-4 py-3 max-w-[85%]">
              {activeTools.length > 0 ? (
                <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
                  <span className="pulse-glow">
                    {toolIcons[activeTools[activeTools.length - 1]] || "🔧"}
                  </span>
                  <span>
                    Running{" "}
                    <span className="text-[var(--accent-blue)] font-medium">
                      {activeTools[activeTools.length - 1]?.replace(/_/g, " ")}
                    </span>
                    ...
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5">
                  <span className="typing-dot w-2 h-2 rounded-full bg-[var(--accent-blue)]" />
                  <span className="typing-dot w-2 h-2 rounded-full bg-[var(--accent-blue)]" />
                  <span className="typing-dot w-2 h-2 rounded-full bg-[var(--accent-blue)]" />
                </div>
              )}
            </div>
          </motion.div>
        )}

        {/* Suggestions (only show when no user messages yet) */}
        {messages.length <= 1 && !isStreaming && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-4">
            {suggestedQueries.map((q, i) => (
              <motion.button
                key={i}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 * i }}
                onClick={() => {
                  setInput(q);
                  inputRef.current?.focus();
                }}
                className="text-left text-sm px-3 py-2.5 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] text-[var(--text-secondary)] hover:border-[var(--accent-blue)] hover:text-[var(--text-primary)] transition-all duration-200 cursor-pointer"
              >
                {q}
              </motion.button>
            ))}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="p-4 border-t border-[var(--border-color)] bg-[var(--bg-secondary)]"
      >
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your finances..."
            disabled={isStreaming}
            className="flex-1 px-4 py-3 rounded-xl bg-[var(--bg-input)] border border-[var(--border-color)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent-blue)] focus:ring-1 focus:ring-[var(--accent-blue)] transition-all text-sm disabled:opacity-50"
            id="chat-input"
          />
          <button
            type="submit"
            disabled={isStreaming || !input.trim()}
            className="px-5 py-3 rounded-xl bg-[var(--accent-blue)] text-white font-medium text-sm hover:bg-blue-600 transition-all disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            id="send-button"
          >
            {isStreaming ? "..." : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}
