"use client";

import React, { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";

const GROUPS = [
  ["Manufacturer", ["Manufacturer Name", "Manufacturer Address", "Manufacturer Pincode"]],
  ["Packer", ["Packer Name", "Packer Address", "Packer Pincode"]],
  ["Importer", ["Importer Name", "Importer Address", "Importer Pincode"]],
];

// The seller's legal details, entered once and used for every product's marketplace export
// (a product's own value, if it has one, still wins).
export default function SellerDetailsCard({ notify }) {
  const [details, setDetails] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/settings/seller-details`)
      .then(async r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setDetails)
      .catch(err => setLoadError(err.message));
  }, []);

  const set = (field, value) => setDetails(d => ({ ...d, [field]: value }));

  const save = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/settings/seller-details`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(details)
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`);
      setDetails(body);
      notify && notify("Seller Details Saved", "Used for every product that doesn't have its own value.", "success");
    } catch (err) {
      notify && notify("Seller Details Not Saved", err.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const input = (field) => (
    <div className="draft-field" key={field}>
      <label>{field}</label>
      <input
        type="text"
        value={details[field] || ""}
        onChange={e => set(field, e.target.value)}
        inputMode={field.endsWith("Pincode") ? "numeric" : undefined}
        maxLength={field.endsWith("Pincode") ? 6 : undefined}
      />
    </div>
  );

  return (
    <div className="admin-card" style={{ marginTop: "20px" }}>
      <div className="admin-card-header">
        <div>
          <h3 className="admin-card-title">🏭 Seller Details (Legal Information)</h3>
          <p style={{ fontSize: "0.84rem", color: "var(--muted)", marginTop: "4px" }}>
            Entered once and used in every product's marketplace export (Meesho's compulsory legal columns).
            A product that has its own value for a field keeps it. Fields left empty stay empty; nothing is filled in for you.
          </p>
        </div>
        <button className="btn btn-primary" onClick={save} disabled={saving || !details}>
          {saving ? <span className="spinner"></span> : "Save Seller Details"}
        </button>
      </div>

      {loadError && <div style={{ color: "var(--bad)", fontSize: "0.84rem" }}>Couldn't load seller details: {loadError}</div>}
      {details && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "12px" }}>
            {input("Country of Origin")}
          </div>
          {GROUPS.map(([label, fields]) => (
            <div key={label} style={{ marginTop: "10px" }}>
              <div style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", marginBottom: "4px" }}>{label}</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr 0.7fr", gap: "12px" }}>
                {fields.map(input)}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
