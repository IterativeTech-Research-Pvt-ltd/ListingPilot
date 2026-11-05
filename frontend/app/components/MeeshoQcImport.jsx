"use client";

import React, { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";

// Brings Meesho's QC result back: the seller uploads the error or warning file from the supplier panel.
// Failed products go back to unapproved with Meesho's reason; flagged words are learned for new copy.
export default function MeeshoQcImport({ onImported, onPickFailed, notify }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const importFile = async (e) => {
    const file = e.target.files?.[0];
    if (e.target) e.target.value = "";
    if (!file) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/drafts/meesho/processed-file`, { method: "POST", body: form });
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error((body && body.detail) || `HTTP ${res.status}`);
      setResult(body);
      onImported && onImported();
      notify && notify("Meesho QC Result Imported", `${body.failed.length} failed, ${body.passed.length} passed.`, body.failed.length ? "warn" : "success");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ marginBottom: "14px", padding: "10px 12px", borderRadius: "var(--radius-sm)", background: "var(--sunk)", fontSize: "0.8rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
        <b>Meesho QC result</b>
        <span style={{ color: "var(--muted)", flex: 1 }}>
          Got QC errors or a warning in the supplier panel? Download that file there and import it here.
        </span>
        <label className="btn btn-sm" style={{ cursor: busy ? "wait" : "pointer" }}>
          {busy ? "Importing…" : "Import error / warning file"}
          <input type="file" accept=".xlsx" onChange={importFile} disabled={busy} style={{ display: "none" }} />
        </label>
      </div>
      {error && <div style={{ color: "var(--bad)", marginTop: "6px" }}>Not imported: {error}</div>}
      {result && (
        <div style={{ marginTop: "8px" }}>
          <div>
            {result.failed.length} failed · {result.passed.length} passed
            {result.unknown_skus.length > 0 && <span style={{ color: "var(--bad)" }}> · not in the catalogue: {result.unknown_skus.join(", ")}</span>}
          </div>
          {result.learned_words.length > 0 && (
            <div style={{ color: "var(--muted)" }}>
              New words Meesho flags, now kept out of copy: {result.learned_words.join(", ")}
            </div>
          )}
          {result.failed.length > 0 && (
            <div style={{ marginTop: "6px", display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ color: "var(--muted)" }}>
                Their drafts are unapproved again: regenerate or edit them in AI Drafts &amp; Review, approve, then export just these.
              </span>
              <button className="btn btn-sm" onClick={() => onPickFailed && onPickFailed(result.failed.map(f => f.product_id))}>
                Pick the {result.failed.length} failed product(s)
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
