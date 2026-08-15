"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Account,
  ImportPreview,
  ImportRecord,
  bulkImportDecision,
  commitImport,
  dedupImport,
  fetchAccounts,
  formatMinor,
  listImportRecords,
  previewImport,
  stageImport,
  updateImportRecord,
  uploadCsv,
} from "@/lib/api";

type Step = "upload" | "map" | "review" | "done";

const labelStyle: React.CSSProperties = {
  fontSize: 12, color: "var(--text-secondary)", marginBottom: 8, display: "block",
  textTransform: "uppercase", letterSpacing: "0.05em",
};

const VERDICT_COLOR: Record<string, string> = {
  new: "var(--brand-success)",
  duplicate: "var(--text-secondary)",
  near_dup: "#ffc800",
};

export default function ImportWizard({ onDone }: { onDone?: () => void }) {
  const [step, setStep] = useState<Step>("upload");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [batchId, setBatchId] = useState("");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, unknown> | null>(null);
  const [chosenLabel, setChosenLabel] = useState("");
  const [records, setRecords] = useState<ImportRecord[]>([]);
  const [dedup, setDedup] = useState<Record<string, number> | null>(null);
  const [committed, setCommitted] = useState<{ committed: number; total_minor: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchAccounts().then((a) => {
      setAccounts(a);
      if (a.length && !accountId) setAccountId(a[0].id);
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reset = () => {
    setStep("upload"); setFile(null); setBatchId(""); setPreview(null);
    setMapping(null); setChosenLabel(""); setRecords([]); setDedup(null);
    setCommitted(null); setError("");
  };

  const doUpload = async () => {
    if (!file || !accountId) return;
    setBusy(true); setError("");
    try {
      const batch = await uploadCsv(file, accountId);
      setBatchId(batch.id);
      const pv = await previewImport(batch.id);
      setPreview(pv);
      // Default to the first matching preset, else the auto-suggested mapping.
      if (pv.presets.length) {
        setMapping(pv.presets[0].mapping); setChosenLabel(pv.presets[0].name);
      } else if (pv.suggested_mapping) {
        setMapping(pv.suggested_mapping); setChosenLabel("Auto-detected");
      }
      setStep("map");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally { setBusy(false); }
  };

  const toggleSign = () => {
    if (!mapping) return;
    const amount = { ...(mapping.amount as Record<string, unknown>) };
    if (amount.mode !== "single") return;
    amount.sign = amount.sign === "expense_positive" ? "natural" : "expense_positive";
    setMapping({ ...mapping, amount });
  };

  const doStageAndDedup = async () => {
    if (!mapping) return;
    setBusy(true); setError("");
    try {
      await stageImport(batchId, mapping);
      const d = await dedupImport(batchId, accountId);
      setDedup(d as unknown as Record<string, number>);
      const res = await listImportRecords(batchId, { limit: 500 });
      setRecords(res.data);
      setStep("review");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not process the file");
    } finally { setBusy(false); }
  };

  const reloadRecords = async () => {
    const res = await listImportRecords(batchId, { limit: 500 });
    setRecords(res.data);
  };

  const setDecision = async (row: ImportRecord, decision: string) => {
    try {
      await updateImportRecord(batchId, row.row_number, { decision });
      setRecords((rs) => rs.map((r) => (r.row_number === row.row_number ? { ...r, decision } : r)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    }
  };

  const bulk = async (decision: string, verdict?: string) => {
    setBusy(true);
    try {
      await bulkImportDecision(batchId, { decision, verdict });
      await reloadRecords();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Bulk update failed");
    } finally { setBusy(false); }
  };

  const doCommit = async () => {
    setBusy(true); setError("");
    try {
      const summary = await commitImport(batchId);
      setCommitted(summary);
      setStep("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally { setBusy(false); }
  };

  const acceptCount = useMemo(() => records.filter((r) => r.decision === "accept").length, [records]);

  return (
    <div style={{ maxWidth: 1000, display: "flex", flexDirection: "column", gap: 20 }}>
      <StepBar step={step} />
      {error && <p style={{ color: "var(--brand-error)", fontSize: 14 }}>{error}</p>}

      {step === "upload" && (
        <div className="glass-panel" style={{ padding: 28, display: "flex", flexDirection: "column", gap: 20 }}>
          <div>
            <label style={labelStyle}>Import into account</label>
            {accounts.length === 0 ? (
              <p style={{ color: "var(--text-secondary)", fontSize: 14 }}>
                Create an account first (Accounts tab).
              </p>
            ) : (
              <select value={accountId} onChange={(e) => setAccountId(e.target.value)} className="sleek-input" style={{ width: "100%" }}>
                {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            )}
          </div>
          <div>
            <label style={labelStyle}>CSV file</label>
            <input type="file" accept=".csv,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
          <div>
            <button className="sleek-button primary" disabled={!file || !accountId || busy} onClick={doUpload}>
              {busy ? "Uploading…" : "Upload & Preview"}
            </button>
          </div>
        </div>
      )}

      {step === "map" && preview && (
        <div className="glass-panel" style={{ padding: 28, display: "flex", flexDirection: "column", gap: 20 }}>
          <div>
            <label style={labelStyle}>Detected format</label>
            <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>
              {preview.total_rows} rows • delimiter “{preview.delimiter}” • {preview.encoding}
            </p>
          </div>
          <div>
            <label style={labelStyle}>Column mapping</label>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {preview.presets.map((p) => (
                <button key={p.key}
                  className={`sleek-button ${chosenLabel === p.name ? "primary" : "secondary"}`}
                  onClick={() => { setMapping(p.mapping); setChosenLabel(p.name); }}
                  style={{ padding: "6px 14px", fontSize: 13 }}>
                  {p.name}
                </button>
              ))}
              {preview.suggested_mapping && (
                <button
                  className={`sleek-button ${chosenLabel === "Auto-detected" ? "primary" : "secondary"}`}
                  onClick={() => { setMapping(preview.suggested_mapping); setChosenLabel("Auto-detected"); }}
                  style={{ padding: "6px 14px", fontSize: 13 }}>
                  Auto-detect
                </button>
              )}
            </div>
            {chosenLabel && mapping && (
              <MappingSummary mapping={mapping} onToggleSign={toggleSign} />
            )}
          </div>
          <PreviewTable preview={preview} />
          <div style={{ display: "flex", gap: 12 }}>
            <button className="sleek-button secondary" onClick={reset}>Cancel</button>
            <button className="sleek-button primary" disabled={!mapping || busy} onClick={doStageAndDedup}>
              {busy ? "Processing…" : "Continue to review"}
            </button>
          </div>
        </div>
      )}

      {step === "review" && (
        <div className="glass-panel" style={{ padding: 28, display: "flex", flexDirection: "column", gap: 16 }}>
          {dedup && (
            <div style={{ display: "flex", gap: 20, flexWrap: "wrap", color: "var(--text-secondary)", fontSize: 13 }}>
              <span><b style={{ color: "var(--brand-success)" }}>{dedup.new}</b> new</span>
              <span><b>{dedup.duplicate}</b> duplicate</span>
              <span><b style={{ color: "#ffc800" }}>{dedup.near_dup}</b> possible repeat</span>
              {dedup.error > 0 && <span><b style={{ color: "var(--brand-error)" }}>{dedup.error}</b> error</span>}
            </div>
          )}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="sleek-button secondary" style={{ fontSize: 12 }} onClick={() => bulk("accept", "new")}>Accept all new</button>
            <button className="sleek-button secondary" style={{ fontSize: 12 }} onClick={() => bulk("skip", "duplicate")}>Skip all duplicates</button>
            <button className="sleek-button secondary" style={{ fontSize: 12 }} onClick={() => bulk("accept", "near_dup")}>Accept repeats</button>
          </div>
          <RecordsTable records={records} onDecision={setDecision} />
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <button className="sleek-button secondary" onClick={reset}>Cancel</button>
            <button className="sleek-button primary" disabled={busy || acceptCount === 0} onClick={doCommit}>
              {busy ? "Importing…" : `Import ${acceptCount} transaction${acceptCount === 1 ? "" : "s"}`}
            </button>
          </div>
        </div>
      )}

      {step === "done" && committed && (
        <div className="glass-panel" style={{ padding: 40, textAlign: "center", display: "flex", flexDirection: "column", gap: 16 }}>
          <h3 className="sleek-text" style={{ fontSize: 22 }}>✅ Imported {committed.committed} transactions</h3>
          <p style={{ color: "var(--text-secondary)" }}>Your dashboard and account balance are updated.</p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
            <button className="sleek-button secondary" onClick={reset}>Import another file</button>
            {onDone && <button className="sleek-button primary" onClick={onDone}>View dashboard</button>}
          </div>
        </div>
      )}
    </div>
  );
}

function StepBar({ step }: { step: Step }) {
  const steps: [Step, string][] = [["upload", "Upload"], ["map", "Map"], ["review", "Review"], ["done", "Done"]];
  const idx = steps.findIndex(([s]) => s === step);
  return (
    <div style={{ display: "flex", gap: 8 }}>
      {steps.map(([s, label], i) => (
        <div key={s} style={{
          flex: 1, padding: "8px 12px", borderRadius: 8, fontSize: 12, textAlign: "center",
          background: i <= idx ? "rgba(204,163,94,0.15)" : "rgba(255,255,255,0.03)",
          color: i <= idx ? "var(--text-primary)" : "var(--text-secondary)",
          border: `1px solid ${i === idx ? "var(--brand-accent)" : "rgba(255,255,255,0.06)"}`,
        }}>{i + 1}. {label}</div>
      ))}
    </div>
  );
}

function MappingSummary({ mapping, onToggleSign }: { mapping: Record<string, unknown>; onToggleSign: () => void }) {
  const amount = mapping.amount as Record<string, unknown>;
  const isSingle = amount?.mode === "single";
  return (
    <div style={{ marginTop: 12, fontSize: 13, color: "var(--text-secondary)" }}>
      {isSingle && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span>Sign: <b>{amount.sign === "expense_positive" ? "positive = expense (card)" : "negative = expense (bank)"}</b></span>
          <button className="sleek-button secondary" style={{ padding: "2px 10px", fontSize: 12 }} onClick={onToggleSign}>Flip</button>
        </div>
      )}
    </div>
  );
}

function PreviewTable({ preview }: { preview: ImportPreview }) {
  return (
    <div style={{ overflowX: "auto", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 8 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr>{preview.headers.map((h) => <th key={h} style={cellHead}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {preview.sample_rows.slice(0, 5).map((row, i) => (
            <tr key={i}>{preview.headers.map((h) => <td key={h} style={cell}>{row[h]}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecordsTable({ records, onDecision }: { records: ImportRecord[]; onDecision: (r: ImportRecord, d: string) => void }) {
  return (
    <div style={{ overflowX: "auto", maxHeight: 380, overflowY: "auto", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 8 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead style={{ position: "sticky", top: 0, background: "var(--bg-sidebar)" }}>
          <tr>
            <th style={cellHead}>Date</th><th style={cellHead}>Description</th>
            <th style={cellHead}>Amount</th><th style={cellHead}>Status</th><th style={cellHead}>Decision</th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => {
            const hasError = r.validation && r.validation.errors.length > 0;
            return (
              <tr key={r.row_number}>
                <td style={cell}>{r.date ?? "—"}</td>
                <td style={cell}>{r.description ?? "—"}</td>
                <td style={{ ...cell, textAlign: "right" }}>
                  {r.amount_minor != null ? formatMinor(r.amount_minor, r.currency || "USD") : "—"}
                </td>
                <td style={cell}>
                  {hasError ? (
                    <span style={{ color: "var(--brand-error)" }} title={r.validation!.errors.join("; ")}>error</span>
                  ) : (
                    <span style={{ color: VERDICT_COLOR[r.verdict ?? ""] ?? "var(--text-secondary)" }}>
                      {r.verdict === "near_dup" ? "repeat?" : r.verdict}
                    </span>
                  )}
                </td>
                <td style={cell}>
                  <select
                    value={r.decision}
                    disabled={!!hasError}
                    onChange={(e) => onDecision(r, e.target.value)}
                    className="sleek-input" style={{ padding: "2px 6px", fontSize: 12 }}>
                    <option value="accept">Import</option>
                    <option value="skip">Skip</option>
                  </select>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const cellHead: React.CSSProperties = {
  textAlign: "left", padding: "8px 12px", color: "var(--text-secondary)",
  borderBottom: "1px solid rgba(255,255,255,0.08)", whiteSpace: "nowrap", fontWeight: 500,
};
const cell: React.CSSProperties = {
  padding: "6px 12px", color: "var(--text-primary)", borderBottom: "1px solid rgba(255,255,255,0.04)", whiteSpace: "nowrap",
};
