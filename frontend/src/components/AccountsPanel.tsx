"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Account,
  ACCOUNT_TYPES,
  Institution,
  archiveAccount,
  createAccount,
  createInstitution,
  fetchAccounts,
  fetchInstitutions,
  formatMinor,
  unarchiveAccount,
  updateAccount,
} from "@/lib/api";

// Account types that default to balance-only tracking (D10: snapshots, not
// transaction feeds).
const BALANCE_ONLY_DEFAULT = new Set(["investment", "property", "loan"]);

const prettyType = (t: string) =>
  t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export default function AccountsPanel() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(true);
  const [showArchived, setShowArchived] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");

  const [form, setForm] = useState({
    name: "",
    type: "checking",
    tracking_mode: "transactions",
    opening_balance: "",
    institution_id: "",
  });

  const load = async (includeArchived: boolean) => {
    setLoading(true);
    try {
      const [accts, insts] = await Promise.all([
        fetchAccounts(includeArchived),
        fetchInstitutions(),
      ]);
      setAccounts(accts);
      setInstitutions(insts);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load accounts");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(showArchived);
  }, [showArchived]);

  const onTypeChange = (type: string) =>
    setForm((f) => ({
      ...f,
      type,
      tracking_mode: BALANCE_ONLY_DEFAULT.has(type) ? "balance_only" : "transactions",
    }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!form.name.trim()) return;
    try {
      const opening =
        form.tracking_mode === "balance_only" && form.opening_balance
          ? Math.round(parseFloat(form.opening_balance) * 100)
          : undefined;
      await createAccount({
        name: form.name.trim(),
        type: form.type,
        tracking_mode: form.tracking_mode,
        institution_id: form.institution_id || null,
        opening_balance_minor: opening,
      });
      setForm({ name: "", type: "checking", tracking_mode: "transactions", opening_balance: "", institution_id: "" });
      setShowForm(false);
      await load(showArchived);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create account");
    }
  };

  const rename = async (a: Account) => {
    const name = window.prompt("Rename account", a.name);
    if (!name || name.trim() === a.name) return;
    try {
      await updateAccount(a.id, { name: name.trim() });
      await load(showArchived);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rename failed");
    }
  };

  const toggleArchive = async (a: Account) => {
    try {
      await (a.archived ? unarchiveAccount(a.id) : archiveAccount(a.id));
      await load(showArchived);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Archive failed");
    }
  };

  const addInstitution = async () => {
    const name = window.prompt("New institution name");
    if (!name?.trim()) return;
    try {
      const inst = await createInstitution({ name: name.trim() });
      setInstitutions((prev) => [...prev, inst].sort((x, y) => x.name.localeCompare(y.name)));
      setForm((f) => ({ ...f, institution_id: inst.id }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add institution");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, maxWidth: 900 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <label style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-secondary)", fontSize: 14 }}>
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
          />
          Show archived
        </label>
        <button className="sleek-button primary" onClick={() => setShowForm((s) => !s)}>
          {showForm ? "Cancel" : "+ Add Account"}
        </button>
      </div>

      {error && <p style={{ color: "var(--brand-error)", fontSize: 14 }}>{error}</p>}

      {showForm && (
        <motion.form
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          onSubmit={submit}
          className="glass-panel"
          style={{ padding: 24, display: "grid", gap: 16, gridTemplateColumns: "1fr 1fr" }}
        >
          <div style={{ gridColumn: "1 / -1" }}>
            <label style={labelStyle}>Account Name</label>
            <input
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="sleek-input"
              style={{ width: "100%" }}
              placeholder="e.g. Everyday Checking"
            />
          </div>
          <div>
            <label style={labelStyle}>Type</label>
            <select
              value={form.type}
              onChange={(e) => onTypeChange(e.target.value)}
              className="sleek-input"
              style={{ width: "100%" }}
            >
              {ACCOUNT_TYPES.map((t) => (
                <option key={t} value={t}>{prettyType(t)}</option>
              ))}
            </select>
          </div>
          <div>
            <label style={labelStyle}>Tracking</label>
            <select
              value={form.tracking_mode}
              onChange={(e) => setForm({ ...form, tracking_mode: e.target.value })}
              className="sleek-input"
              style={{ width: "100%" }}
            >
              <option value="transactions">Transactions</option>
              <option value="balance_only">Balance only</option>
            </select>
          </div>
          {form.tracking_mode === "balance_only" && (
            <div>
              <label style={labelStyle}>Current Balance ($)</label>
              <input
                type="number"
                step="0.01"
                value={form.opening_balance}
                onChange={(e) => setForm({ ...form, opening_balance: e.target.value })}
                className="sleek-input"
                style={{ width: "100%" }}
                placeholder="e.g. 10000.00"
              />
            </div>
          )}
          <div>
            <label style={labelStyle}>Institution (optional)</label>
            <div style={{ display: "flex", gap: 8 }}>
              <select
                value={form.institution_id}
                onChange={(e) => setForm({ ...form, institution_id: e.target.value })}
                className="sleek-input"
                style={{ flex: 1 }}
              >
                <option value="">None</option>
                {institutions.map((i) => (
                  <option key={i.id} value={i.id}>{i.name}</option>
                ))}
              </select>
              <button type="button" className="sleek-button secondary" onClick={addInstitution}>
                + New
              </button>
            </div>
          </div>
          <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "flex-end" }}>
            <button type="submit" className="sleek-button primary">Create Account</button>
          </div>
        </motion.form>
      )}

      {loading ? (
        <p style={{ color: "var(--text-secondary)" }}>Loading accounts…</p>
      ) : accounts.length === 0 ? (
        <div className="glass-panel" style={{ padding: 40, textAlign: "center", color: "var(--text-secondary)" }}>
          No accounts yet. Add one to start tracking transactions.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {accounts.map((a) => (
            <div
              key={a.id}
              className="glass-panel"
              style={{
                padding: "16px 20px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                opacity: a.archived ? 0.55 : 1,
              }}
            >
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ color: "var(--text-primary)", fontSize: 16, fontWeight: 500 }}>{a.name}</span>
                  <span style={badgeStyle}>{prettyType(a.type)}</span>
                  {a.archived && <span style={{ ...badgeStyle, color: "var(--brand-error)" }}>Archived</span>}
                </div>
                <div style={{ color: "var(--text-secondary)", fontSize: 12, marginTop: 4 }}>
                  {a.institution?.name ? `${a.institution.name} • ` : ""}
                  {a.tracking_mode === "balance_only" ? "Balance only" : "Transactions"}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <span style={{ fontSize: 18, fontWeight: 500, color: "var(--text-primary)" }}>
                  {a.current_balance_minor != null
                    ? formatMinor(a.current_balance_minor, a.currency)
                    : "—"}
                </span>
                <button className="sleek-button secondary" onClick={() => rename(a)} style={{ padding: "6px 12px", fontSize: 12 }}>
                  Rename
                </button>
                <button className="sleek-button secondary" onClick={() => toggleArchive(a)} style={{ padding: "6px 12px", fontSize: 12 }}>
                  {a.archived ? "Unarchive" : "Archive"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  color: "var(--text-secondary)",
  marginBottom: 8,
  display: "block",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const badgeStyle: React.CSSProperties = {
  fontSize: 11,
  color: "var(--text-secondary)",
  border: "1px solid rgba(255,255,255,0.15)",
  borderRadius: 6,
  padding: "2px 8px",
  textTransform: "capitalize",
};
