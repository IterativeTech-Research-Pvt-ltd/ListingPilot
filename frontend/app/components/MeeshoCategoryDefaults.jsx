"use client";

import React, { useEffect, useState } from "react";
import MeeshoCategoryPicker from "./MeeshoCategoryPicker";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";

// The Meesho category for every product in one of the seller's own categories, chosen once
// (e.g. Bedsheets > Home & Kitchen > Home Furnishings > Bedding & Linen > Bedsheets). A product's
// own choice, made on the product, still wins. Nothing is chosen automatically.
export default function MeeshoCategoryDefaults({ notify }) {
  const [rows, setRows] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/drafts/meesho/category-defaults`)
      .then(async r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(body => setRows(body.defaults))
      .catch(err => setLoadError(err.message));
  }, []);

  const save = async (category, id, breadcrumb) => {
    setEditing(null);
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/drafts/meesho/category-defaults`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category, meesho_category: id || "" })
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`);
      setRows(body.defaults);
      notify && notify("Meesho Category Saved", id ? `${category} → ${breadcrumb}` : `${category} has no default now.`, "success");
    } catch (err) {
      notify && notify("Meesho Category Not Saved", err.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const editingRow = rows && rows.find(r => r.category === editing);

  return (
    <div className="admin-card" style={{ marginTop: "20px" }}>
      <div className="admin-card-header">
        <div>
          <h3 className="admin-card-title">🗂️ Meesho Categories</h3>
          <p style={{ fontSize: "0.84rem", color: "var(--muted)", marginTop: "4px" }}>
            Choose the Meesho category once for each of your categories, as in the supplier panel. Every product in it is
            filled into that category's official template, unless the product has its own choice (set on the product, e.g. for a
            women's kurta in a mixed Kurtas category). Products without either are left out of Meesho exports.
          </p>
        </div>
      </div>

      {loadError && <div style={{ color: "var(--bad)", fontSize: "0.84rem" }}>Couldn't load Meesho categories: {loadError}</div>}
      {rows && rows.length === 0 && <div style={{ color: "var(--muted)", fontSize: "0.84rem" }}>No products yet.</div>}
      {rows && rows.length > 0 && (
        <table style={{ width: "100%", fontSize: "0.84rem", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", color: "var(--muted)" }}>
              <th style={{ padding: "6px 4px" }}>Your category</th>
              <th style={{ padding: "6px 4px" }}>Products</th>
              <th style={{ padding: "6px 4px" }}>Meesho category</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.category} style={{ borderTop: "1px solid var(--line)" }}>
                <td style={{ padding: "6px 4px", fontWeight: 600 }}>{r.category}</td>
                <td style={{ padding: "6px 4px" }}>{r.products}</td>
                <td style={{ padding: "6px 4px" }}>
                  {r.breadcrumb || (r.invalid_value
                    ? <span style={{ color: "var(--bad)" }}>“{r.invalid_value}” is no longer a Meesho category; choose again</span>
                    : <span style={{ color: "var(--muted)" }}>not chosen</span>)}
                </td>
                <td style={{ padding: "6px 4px", whiteSpace: "nowrap", textAlign: "right" }}>
                  <button className="btn btn-sm" onClick={() => setEditing(r.category)} disabled={saving}>
                    {r.breadcrumb ? "Change" : "Choose"}
                  </button>
                  {(r.breadcrumb || r.invalid_value) && (
                    <button className="btn btn-sm" style={{ marginLeft: "6px" }} onClick={() => save(r.category, "", "")} disabled={saving}>
                      Clear
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <MeeshoCategoryPicker
        open={!!editingRow}
        title={editingRow ? `Meesho category for all “${editingRow.category}” products` : ""}
        valueId={editingRow?.id}
        suggestions={editingRow?.suggestions || []}
        onPick={(id, breadcrumb) => save(editingRow.category, id, breadcrumb)}
        onClose={() => setEditing(null)}
      />
    </div>
  );
}
