"use client";

import React, { useEffect, useState } from "react";
import MeeshoCategoryPicker from "./MeeshoCategoryPicker";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
// Longer option lists get a search box; a plain select is unusable past this
const SELECT_LIMIT = 50;

export const EMPTY_MEESHO_CHOICE = { id: "", breadcrumb: "", fields: [], values: {} };

const filled = (choice, f) => (choice.values[f.attribute] || "").trim();

// What the form can't save (a typed value that isn't one of Meesho's options) and what the export still needs
export function meeshoChoiceIssues(choice) {
  return {
    invalid: choice.fields.filter(f => filled(choice, f) && f.options.length > 0 && !f.options.includes(filled(choice, f))),
    missing: choice.fields.filter(f => f.required && !filled(choice, f)),
  };
}

// The attributes to save with the product: the category, and only what the seller filled in
export function meeshoChoiceAttributes(choice) {
  if (!choice.id) return {};
  const values = choice.fields.filter(f => filled(choice, f)).map(f => [f.attribute, filled(choice, f)]);
  return { "Meesho Category": choice.id, ...Object.fromEntries(values) };
}

function Field({ field, value, onChange }) {
  const { options } = field;
  const invalid = value.trim() && options.length > 0 && !options.includes(value.trim());
  const listId = `meesho-options-${field.attribute}`;

  return (
    <div className="draft-field" style={{ margin: 0 }}>
      <label title={field.hint} style={{ fontSize: "0.74rem" }}>{field.field}{field.required ? " *" : ""}</label>
      {options.length > 0 && options.length <= SELECT_LIMIT ? (
        <select value={value} onChange={e => onChange(e.target.value)} style={{ width: "100%", fontSize: "0.8rem", padding: "4px 6px" }}>
          <option value="">— choose —</option>
          {options.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <>
          <input
            type="text"
            list={options.length > 0 ? listId : undefined}
            value={value}
            onChange={e => onChange(e.target.value)}
            placeholder={options.length > 0 ? `Search ${options.length} options…` : ""}
            title={field.hint}
            style={{ fontSize: "0.8rem", padding: "4px 6px" }}
          />
          {options.length > 0 && (
            <datalist id={listId}>
              {options.map(o => <option key={o} value={o} />)}
            </datalist>
          )}
        </>
      )}
      {invalid && <div style={{ color: "var(--bad)", fontSize: "0.72rem" }}>Not one of Meesho's options; pick one from the list.</div>}
    </div>
  );
}

// Add Product's Meesho section: the seller picks the category and fills only that category's fields.
// Skipping it is fine; the product is then saved as before and has no Meesho category yet.
export default function MeeshoCategoryFields({ choice, onChange }) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [showOptional, setShowOptional] = useState(false);
  const [attempt, setAttempt] = useState(0);

  const { id } = choice;

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    setLoadError("");
    fetch(`${API_BASE}/drafts/meesho/category-fields/${id}`)
      .then(async res => {
        const body = await res.json().catch(() => null);
        if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`);
        return body;
      })
      .then(body => { if (!cancelled) onChange(c => ({ ...c, fields: body.fields })); })
      .catch(err => { if (!cancelled) setLoadError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id, attempt]);

  const pick = (pickedId, breadcrumb) => {
    setPickerOpen(false);
    setShowOptional(false);
    // Each category has its own fields and options, so values from another category don't carry over
    if (pickedId !== id) onChange({ ...EMPTY_MEESHO_CHOICE, id: pickedId, breadcrumb });
  };

  const setValue = (attribute, value) => onChange(c => ({ ...c, values: { ...c.values, [attribute]: value } }));
  const required = choice.fields.filter(f => f.required);
  const optional = choice.fields.filter(f => !f.required);
  const { missing } = meeshoChoiceIssues(choice);
  const grid = { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "8px" };
  const fieldList = fields => (
    <div style={grid}>
      {fields.map(f => (
        <Field key={f.attribute} field={f} value={choice.values[f.attribute] || ""} onChange={v => setValue(f.attribute, v)} />
      ))}
    </div>
  );

  return (
    <div style={{ marginTop: "12px", padding: "10px 12px", borderRadius: "var(--radius-sm)", background: "var(--sunk)", fontSize: "0.8rem" }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px" }}>
        <b>Meesho category</b>
        <span style={{ flex: 1, color: choice.breadcrumb ? "inherit" : "var(--muted)" }}>
          {choice.breadcrumb || "Optional. Choose it to fill this category's Meesho fields now."}
        </span>
        <button type="button" className="btn btn-sm" onClick={() => setPickerOpen(true)}>{id ? "Change" : "Choose"}</button>
        {id && <button type="button" className="btn btn-sm" onClick={() => onChange(EMPTY_MEESHO_CHOICE)}>Remove</button>}
      </div>

      <MeeshoCategoryPicker
        open={pickerOpen}
        title="Meesho category for this product"
        valueId={id}
        onPick={pick}
        onClose={() => setPickerOpen(false)}
      />

      {loading && <div style={{ marginTop: "8px", color: "var(--muted)" }}>Loading this category's fields…</div>}
      {loadError && (
        <div style={{ marginTop: "8px", color: "var(--bad)" }}>
          Couldn't load this category's fields: {loadError}{" "}
          <button type="button" className="btn btn-sm" onClick={() => setAttempt(a => a + 1)}>Try again</button>
        </div>
      )}

      {!loading && !loadError && choice.fields.length > 0 && (
        <div style={{ marginTop: "10px" }}>
          <div style={{ fontWeight: 700, marginBottom: "6px" }}>
            Required by Meesho ({required.length - missing.length} of {required.length} filled)
          </div>
          {fieldList(required)}
          {optional.length > 0 && (
            <div style={{ marginTop: "10px" }}>
              <button type="button" className="btn btn-sm" onClick={() => setShowOptional(s => !s)}>
                {showOptional ? "Hide" : "Show"} {optional.length} optional field{optional.length === 1 ? "" : "s"}
              </button>
              {showOptional && <div style={{ marginTop: "8px" }}>{fieldList(optional)}</div>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
