"use client";

import React, { useEffect, useState } from "react";
import MeeshoCategoryPicker from "./MeeshoCategoryPicker";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";

// The compulsory Meesho fields a product still lacks, as the export itself checks them.
// Dropdowns list only the official template's options; nothing is pre-selected or guessed.
export default function MeeshoRequiredFields({ product, onSaved, notify }) {
  const [missing, setMissing] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [values, setValues] = useState({});
  const [saving, setSaving] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  const productId = product?.id;
  const attrsKey = JSON.stringify(product?.attributes || {});

  useEffect(() => {
    if (!productId) return;
    let cancelled = false;
    setMissing(null);
    setLoadError("");
    fetch(`${API_BASE}/drafts/meesho/missing-fields/${productId}`)
      .then(async r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => { if (!cancelled) setMissing(data); })
      .catch(err => { if (!cancelled) setLoadError(err.message); });
    return () => { cancelled = true; };
  }, [productId, attrsKey, product?.category]);

  if (!productId) return null;

  const box = { marginTop: "12px", padding: "10px 12px", borderRadius: "var(--radius-sm)", fontSize: "0.8rem" };

  if (loadError) {
    return <div style={{ ...box, background: "var(--bad-soft, #fdecea)" }}>Couldn't check Meesho fields: {loadError}</div>;
  }
  if (!missing) {
    return <div style={{ ...box, background: "var(--sunk)", color: "var(--muted)" }}>Checking Meesho fields…</div>;
  }
  const putValues = async (payload) => {
    const res = await fetch(`${API_BASE}/drafts/meesho/missing-fields/${productId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values: payload })
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      const errors = body?.detail?.errors;
      throw new Error(errors ? errors.join("; ") : (body?.detail?.message || body?.detail || `HTTP ${res.status}`));
    }
    setMissing(body.missing);
    // body.draft: the product's Meesho draft with its checks rerun on the saved values
    onSaved && onSaved(body.product, body.draft);
    return body;
  };

  // Empty id removes the product's own choice, so its category's default applies again
  const saveCategory = async (id, breadcrumb) => {
    setPickerOpen(false);
    setSaving(true);
    try {
      await putValues({ "Meesho Category": id || "" });
      notify && notify("Meesho Category Saved", id ? breadcrumb : "This product now follows its category's default.", "success");
    } catch (err) {
      notify && notify("Meesho Category Not Saved", err.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const chosen = missing.meesho_category || {};
  const categoryBar = (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
      <span style={{ fontWeight: 700 }}>Meesho category:</span>
      {chosen.breadcrumb ? (
        <span>
          {chosen.breadcrumb}{" "}
          <span style={{ color: "var(--muted)" }}>
            ({chosen.source === "product" ? "chosen for this product" : `default for ${missing.category}`})
          </span>
        </span>
      ) : (
        <span style={{ color: "var(--bad)" }}>not chosen, so this product is left out of Meesho exports</span>
      )}
      <button className="btn btn-sm" onClick={() => setPickerOpen(true)} disabled={saving}>
        {chosen.breadcrumb ? "Change" : "Choose"}
      </button>
      {chosen.source === "product" && (
        <button className="btn btn-sm" onClick={() => saveCategory("", "")} disabled={saving}>Use category default</button>
      )}
      <MeeshoCategoryPicker
        open={pickerOpen}
        title={`Meesho category for ${product.sku}`}
        valueId={chosen.id}
        suggestions={chosen.suggestions || []}
        onPick={saveCategory}
        onClose={() => setPickerOpen(false)}
      />
    </div>
  );

  if (!missing.template) {
    return (
      <div style={{ ...box, background: "var(--sunk)" }}>
        {categoryBar}
        {missing.other.map(o => <div key={o.field} style={{ color: "var(--muted)" }}>{o.reason}</div>)}
      </div>
    );
  }
  const seller = missing.seller || [];
  if (missing.fields.length === 0 && seller.length === 0 && missing.other.length === 0) {
    return (
      <div style={{ ...box, background: "var(--good-soft)" }}>
        {categoryBar}
        <div style={{ color: "var(--good)" }}>✓ Every compulsory Meesho field is filled.</div>
      </div>
    );
  }

  const filled = Object.entries(values).filter(([, v]) => v && v.trim());

  const save = async () => {
    setSaving(true);
    try {
      const body = await putValues(Object.fromEntries(filled));
      setValues({});
      notify && notify("Meesho Fields Saved", `${filled.length} field(s) saved to ${body.product.sku}.`, "success");
    } catch (err) {
      notify && notify("Meesho Fields Not Saved", err.message, "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ ...box, background: "var(--warn-soft)", borderLeft: "4px solid var(--warn)" }}>
      {categoryBar}
      <div style={{ fontWeight: 700, marginBottom: "6px" }}>
        Meesho required fields ({missing.fields.length + seller.length} missing)
      </div>
      <div style={{ color: "var(--muted)", marginBottom: "8px" }}>
        The Meesho export is blocked until these are filled. Enter the product's real details; dropdowns use Meesho's own spellings.
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "8px" }}>
        {missing.fields.map(f => (
          <div key={f.attribute} className="draft-field" style={{ margin: 0 }}>
            <label title={f.reason} style={{ fontSize: "0.74rem" }}>
              {f.field}
            </label>
            {f.options.length > 0 ? (
              <select
                value={values[f.attribute] || ""}
                onChange={e => setValues(v => ({ ...v, [f.attribute]: e.target.value }))}
                style={{ fontSize: "0.8rem", padding: "4px 6px" }}
              >
                <option value="">— choose —</option>
                {f.options.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : (
              <input
                type="text"
                value={values[f.attribute] || ""}
                onChange={e => setValues(v => ({ ...v, [f.attribute]: e.target.value }))}
                style={{ fontSize: "0.8rem", padding: "4px 6px" }}
              />
            )}
          </div>
        ))}
      </div>

      {seller.length > 0 && (
        <div style={{ marginTop: "8px" }}>
          <b>Same for every product</b>, set once in Admin &amp; Settings → Brand Voice → Seller Details: {seller.join(", ")}.
        </div>
      )}

      {missing.other.length > 0 && (
        <ul style={{ margin: "8px 0 0", paddingLeft: "18px", color: "var(--muted)" }}>
          {missing.other.map(o => <li key={o.field}><b>{o.field}</b>: {o.reason}</li>)}
        </ul>
      )}

      {missing.fields.length > 0 && (
        <button
          className="btn btn-sm btn-primary"
          style={{ marginTop: "10px" }}
          onClick={save}
          disabled={saving || filled.length === 0}
        >
          {saving ? "Saving…" : `Save ${filled.length || ""} Meesho field(s)`}
        </button>
      )}
    </div>
  );
}
