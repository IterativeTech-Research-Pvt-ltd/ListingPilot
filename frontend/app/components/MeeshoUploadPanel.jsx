"use client";

import React, { useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const SELECTION_KEY = "listingpilot.meeshoUpload.selected";

// The selection is a per-browser convenience; the server checks whatever is sent
function loadSelection() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(SELECTION_KEY) || "[]");
    return Array.isArray(saved) ? saved.filter(Number.isInteger) : [];
  } catch {
    return [];
  }
}

function saveSelection(ids) {
  try { window.localStorage.setItem(SELECTION_KEY, JSON.stringify(ids)); } catch { /* storage unavailable */ }
}

async function download(res, fallbackName) {
  const blob = await res.blob();
  let name = fallbackName;
  const match = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(res.headers.get("content-disposition") || "");
  if (match && match[1]) name = match[1].replace(/['"]/g, "");
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
  return name;
}

async function errorText(res) {
  const body = await res.json().catch(() => null);
  const detail = body && body.detail;
  return (detail && detail.message) || (typeof detail === "string" ? detail : `HTTP ${res.status}`);
}

// One Meesho bulk upload: the seller picks which catalogue products go in it. The file is made only
// when every picked product is ready (all or nothing); a product that isn't is fixed or taken out.
export default function MeeshoUploadPanel({ open, onClose, notify }) {
  const [rows, setRows] = useState(null);
  const [checkedWith, setCheckedWith] = useState("all");
  const [loadError, setLoadError] = useState("");
  const [selected, setSelected] = useState([]);
  const [expanded, setExpanded] = useState({});
  const [busy, setBusy] = useState("");

  const fetchReadiness = async (ids) => {
    const qs = ids ? `?product_ids=${ids.join(",")}` : "";
    const res = await fetch(`${API_BASE}/drafts/meesho/readiness${qs}`);
    if (!res.ok) throw new Error(await errorText(res));
    return (await res.json()).products;
  };

  const loadAll = async () => {
    setLoadError("");
    try {
      const products = await fetchReadiness(null);
      setRows(products);
      setCheckedWith("all");
      const known = new Set(products.map(p => p.id));
      setSelected(prev => prev.filter(id => known.has(id)));
    } catch (err) {
      setLoadError(err.message);
    }
  };

  useEffect(() => {
    if (!open) return;
    setRows(null);
    setSelected(loadSelection());
    loadAll();
  }, [open]);

  useEffect(() => { if (open) saveSelection(selected); }, [selected, open]);

  const byId = useMemo(() => Object.fromEntries((rows || []).map(r => [r.id, r])), [rows]);
  const picked = selected.filter(id => byId[id]);
  const notReady = picked.filter(id => !byId[id].ready);

  const groups = useMemo(() => {
    const out = {};
    for (const r of rows || []) {
      const key = r.meesho_category || "No Meesho category chosen";
      (out[key] = out[key] || []).push(r);
    }
    return Object.entries(out).sort(([a], [b]) => a.localeCompare(b));
  }, [rows]);

  if (!open) return null;

  const toggle = id => setSelected(s => (s.includes(id) ? s.filter(x => x !== id) : [...s, id]));

  // Rechecks just the picked products together, as the upload will be (e.g. shared Product Names)
  const recheckSelection = async () => {
    if (!picked.length) return;
    setBusy("check");
    try {
      const updated = await fetchReadiness(picked);
      setRows(prev => prev.map(r => updated.find(u => u.id === r.id) || r));
      setCheckedWith("selection");
    } catch (err) {
      notify && notify("Check Failed", err.message, "error");
    } finally {
      setBusy("");
    }
  };

  const exportUpload = async () => {
    setBusy("export");
    try {
      const res = await fetch(`${API_BASE}/drafts/meesho/export?as_zip=true&product_ids=${picked.join(",")}`);
      if (!res.ok) {
        const message = await errorText(res);
        await recheckSelection();
        throw new Error(message);
      }
      const name = await download(res, `ListingPilot_Meesho_${new Date().toISOString().slice(0, 10)}.zip`);
      notify && notify("Meesho Upload File Ready 📦", `${name}: ${picked.length} product(s). Upload each file under its category in the supplier panel's Bulk Catalog Upload.`, "success");
    } catch (err) {
      notify && notify("Meesho Export Blocked", err.message, "error");
    } finally {
      setBusy("");
    }
  };

  const fillInSheet = async () => {
    setBusy("fill");
    try {
      const res = await fetch(`${API_BASE}/drafts/meesho/fill-in-sheet?product_ids=${notReady.join(",")}`);
      if (!res.ok) throw new Error(await errorText(res));
      const name = await download(res, "Meesho_fill_in_Selection.xlsx");
      notify && notify("Fill-in Sheet Downloaded", `${name}: fill the highlighted cells, import it in the Catalogue tab, then recheck.`, "info");
    } catch (err) {
      notify && notify("Fill-in Sheet Failed", err.message, "error");
    } finally {
      setBusy("");
    }
  };

  const badge = r => (
    <span
      className={`chip chip-flat ${r.ready ? "chip-good" : "chip-bad"}`}
      style={{ fontSize: "0.7rem", cursor: r.ready ? "default" : "pointer" }}
      onClick={() => !r.ready && setExpanded(e => ({ ...e, [r.id]: !e[r.id] }))}
    >
      {r.ready ? "✓ Ready" : `${r.problems.length} problem${r.problems.length === 1 ? "" : "s"} ${expanded[r.id] ? "▴" : "▾"}`}
    </span>
  );

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: "980px", width: "96%" }} onClick={e => e.stopPropagation()}>
        <div className="modal-header" style={{ borderBottom: "1px solid var(--line)", paddingBottom: "12px" }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "1.1rem" }}>Meesho Upload</h3>
            <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>
              Pick the products for this bulk upload. The file is made only when every picked product is ready; fix or take out the rest.
            </div>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: "1.2rem", cursor: "pointer", color: "var(--muted)" }}>✕</button>
        </div>

        <div className="modal-body" style={{ maxHeight: "62vh", overflowY: "auto", padding: "12px 20px" }}>
          {loadError && <div style={{ color: "var(--bad)", fontSize: "0.84rem" }}>Couldn't check products: {loadError}</div>}
          {!rows && !loadError && <div style={{ color: "var(--muted)", fontSize: "0.84rem" }}>Checking every product against Meesho's templates…</div>}
          {rows && rows.length === 0 && <div style={{ color: "var(--muted)", fontSize: "0.84rem" }}>No products in the catalogue yet.</div>}

          {groups.map(([group, items]) => (
            <div key={group} style={{ marginBottom: "14px" }}>
              <div style={{ fontSize: "0.76rem", fontWeight: 700, color: "var(--muted)", marginBottom: "4px" }}>
                {group} · {items.length}
              </div>
              {items.map(r => (
                <div key={r.id} style={{ borderTop: "1px solid var(--line)", padding: "6px 0" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "10px", fontSize: "0.84rem", cursor: "pointer" }}>
                    <input type="checkbox" checked={selected.includes(r.id)} onChange={() => toggle(r.id)} />
                    <span style={{ fontWeight: 600, minWidth: "80px" }}>{r.sku}</span>
                    <span style={{ flex: 1 }}>{r.name}</span>
                    <span style={{ color: "var(--muted)", fontSize: "0.76rem" }}>{r.category}</span>
                    {badge(r)}
                  </label>
                  {!r.ready && expanded[r.id] && (
                    <ul style={{ margin: "6px 0 0 34px", paddingLeft: "14px", fontSize: "0.78rem", color: "var(--muted)" }}>
                      {r.problems.map((p, i) => <li key={i}><b>{p.field}</b>: {p.reason}</li>)}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>

        <div className="modal-footer" style={{ borderTop: "1px solid var(--line)", paddingTop: "12px", display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ fontSize: "0.8rem" }}>
            <b>{picked.length}</b> picked
            {picked.length > 0 && (notReady.length
              ? <span style={{ color: "var(--bad)" }}> · {notReady.length} not ready: fix or take them out</span>
              : <span style={{ color: "var(--good)" }}> · all ready</span>)}
            <span style={{ color: "var(--muted)" }}> · checked {checkedWith === "selection" ? "as this selection" : "across the whole catalogue"}</span>
          </div>
          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
            <button className="btn btn-sm" onClick={() => setSelected((rows || []).filter(r => r.ready).map(r => r.id))} disabled={!rows || !!busy}>Pick all ready</button>
            <button className="btn btn-sm" onClick={() => setSelected([])} disabled={!picked.length || !!busy}>Clear</button>
            <button className="btn btn-sm" onClick={recheckSelection} disabled={!picked.length || !!busy}>{busy === "check" ? "Checking…" : "Recheck selection"}</button>
            {notReady.length > 0 && (
              <button className="btn btn-sm" onClick={fillInSheet} disabled={!!busy}>{busy === "fill" ? "Preparing…" : "Fill-in sheet for the not-ready"}</button>
            )}
            <button
              className="btn btn-sm btn-primary"
              style={{ background: "var(--purple)", borderColor: "var(--purple)" }}
              onClick={exportUpload}
              disabled={!picked.length || notReady.length > 0 || !!busy}
              title={notReady.length ? "Every picked product must be ready" : ""}
            >
              {busy === "export" ? "Exporting…" : `📥 Export ${picked.length || ""} for Meesho`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
