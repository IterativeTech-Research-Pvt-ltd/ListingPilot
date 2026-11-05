"use client";

import React, { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";

// Confirms deleting a product. The product is only reported gone after the backend says so.
export default function DeleteProductDialog({ product, drafts, onClose, onDeleted }) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  if (!product) return null;

  const productDrafts = drafts.filter(d => d.product_id === product.id);
  const sentOut = productDrafts.filter(d => d.status === "exported" || d.status === "live");
  const close = () => { if (!deleting) onClose(); };

  const confirmDelete = async () => {
    setDeleting(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/catalogue/products/${product.id}`, { method: "DELETE" });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      onDeleted(product);
    } catch (err) {
      setError(err.message);
      setDeleting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={e => { e.stopPropagation(); close(); }}>
      <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: "460px" }}>
        <div className="modal-header">
          <h3>Delete {product.sku}?</h3>
        </div>
        <div className="modal-body" style={{ fontSize: "0.86rem" }}>
          <p style={{ marginTop: 0 }}><b>{product.name}</b></p>
          <p>
            This permanently deletes the product
            {productDrafts.length > 0 ? ` and its ${productDrafts.length} draft${productDrafts.length === 1 ? "" : "s"}` : ""}.
            It can't be undone. Its photos stay in storage.
          </p>
          {sentOut.length > 0 && (
            <p style={{ color: "var(--bad)" }}>
              It was sent to {sentOut.map(d => d.marketplace.charAt(0).toUpperCase() + d.marketplace.slice(1)).join(", ")}.
              This doesn't remove that listing: pause or remove it in the seller panel.
            </p>
          )}
          {error && <p style={{ color: "var(--bad)", marginBottom: 0 }}>Not deleted: {error}</p>}
        </div>
        <div className="modal-footer">
          <button className="btn" onClick={close} disabled={deleting}>Cancel</button>
          <button className="btn btn-danger" onClick={confirmDelete} disabled={deleting}>
            {deleting ? "Deleting…" : "Delete product"}
          </button>
        </div>
      </div>
    </div>
  );
}
