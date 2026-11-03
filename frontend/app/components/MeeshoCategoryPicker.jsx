"use client";

import React, { useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";

// The category tree is the same for every product; fetch it once per page load
let taxonomyRequest = null;
function loadTaxonomy() {
  if (!taxonomyRequest) {
    taxonomyRequest = fetch(`${API_BASE}/drafts/meesho/taxonomy`)
      .then(async r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .catch(err => {
        taxonomyRequest = null; // let the next open try again
        throw err;
      });
  }
  return taxonomyRequest;
}

// Every leaf as { id, segments }, for search and for finding the current choice
function flatten(nodes, trail = [], out = []) {
  for (const n of nodes) {
    if (n.children) flatten(n.children, [...trail, n.name], out);
    else out.push({ id: n.id, segments: [...trail, n.name] });
  }
  return out;
}

// Picks a Meesho category the way the supplier panel's Bulk Catalog Upload does: four columns
// (e.g. Men Fashion > Mens Clothing > Men Top Wear > Shirts) or a search. Only leaves with an
// official template can be picked; nothing is chosen for the seller.
export default function MeeshoCategoryPicker({ open, title, valueId, suggestions = [], onPick, onClose }) {
  const [tree, setTree] = useState(null);
  const [separator, setSeparator] = useState(" > ");
  const [loadError, setLoadError] = useState("");
  const [trail, setTrail] = useState([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoadError("");
    loadTaxonomy()
      .then(body => {
        if (cancelled) return;
        setTree(body.tree);
        setSeparator(body.separator || " > ");
      })
      .catch(err => { if (!cancelled) setLoadError(err.message); });
    return () => { cancelled = true; };
  }, [open]);

  const leaves = useMemo(() => (tree ? flatten(tree) : []), [tree]);
  const current = useMemo(() => leaves.find(l => l.id === valueId) || null, [leaves, valueId]);

  // Open on the current choice, as the panel keeps your last category
  useEffect(() => {
    if (open) {
      setTrail(current ? current.segments.slice(0, 3) : []);
      setQuery("");
    }
  }, [open, current]);

  if (!open) return null;

  const columns = [];
  if (tree) {
    let level = tree;
    for (let depth = 0; depth < 4 && level; depth++) {
      columns.push(level);
      const picked = level.find(n => n.name === trail[depth] && n.children);
      level = picked ? picked.children : null;
    }
  }

  const q = query.trim().toLowerCase();
  const results = q.length >= 2
    ? leaves.filter(l => l.segments.join(separator).toLowerCase().includes(q)).slice(0, 60)
    : [];

  const pick = leaf => onPick && onPick(leaf.id, leaf.segments.join(separator));

  const cell = (active) => ({
    padding: "9px 12px",
    cursor: "pointer",
    borderBottom: "1px solid var(--line)",
    fontSize: "0.84rem",
    background: active ? "var(--purple)" : "transparent",
    color: active ? "#fff" : "inherit",
    fontWeight: active ? 600 : 400,
  });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: "1000px", width: "96%" }} onClick={e => e.stopPropagation()}>
        <div className="modal-header" style={{ borderBottom: "1px solid var(--line)", paddingBottom: "12px" }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "1.1rem" }}>{title || "Choose Meesho category"}</h3>
            <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>
              Same tree as the supplier panel's Bulk Catalog Upload. The product is filled into this category's official template.
            </div>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: "1.2rem", cursor: "pointer", color: "var(--muted)" }}>✕</button>
        </div>

        <div className="modal-body" style={{ padding: "14px 20px" }}>
          {loadError && <div style={{ color: "var(--bad)", fontSize: "0.84rem" }}>Couldn't load Meesho categories: {loadError}</div>}
          {!tree && !loadError && <div style={{ color: "var(--muted)", fontSize: "0.84rem" }}>Loading Meesho categories…</div>}

          {tree && (
            <>
              {current && (
                <div style={{ fontSize: "0.8rem", marginBottom: "10px" }}>
                  Current: <b>{current.segments.join(separator)}</b>
                </div>
              )}
              {suggestions.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", alignItems: "center", marginBottom: "10px", fontSize: "0.78rem" }}>
                  <span style={{ color: "var(--muted)" }}>Matches for this category's name (check before choosing):</span>
                  {suggestions.map(s => (
                    <button key={s.id} className="btn btn-sm" onClick={() => onPick && onPick(s.id, s.breadcrumb)}>{s.breadcrumb}</button>
                  ))}
                </div>
              )}

              <input
                type="text"
                placeholder="Search a category, e.g. Bedsheets, Kurtis, Puja"
                value={query}
                onChange={e => setQuery(e.target.value)}
                style={{ width: "100%", padding: "8px 10px", fontSize: "0.86rem", marginBottom: "10px" }}
              />

              {q.length >= 2 ? (
                <div style={{ maxHeight: "52vh", overflowY: "auto", border: "1px solid var(--line)", borderRadius: "var(--radius-sm)" }}>
                  {results.length === 0 && <div style={{ padding: "10px", color: "var(--muted)", fontSize: "0.84rem" }}>No category matches “{query}”.</div>}
                  {results.map(l => (
                    <div key={l.id} style={cell(l.id === valueId)} onClick={() => pick(l)}>
                      {l.segments.join(separator)}
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", border: "1px solid var(--line)", borderRadius: "var(--radius-sm)" }}>
                  {[0, 1, 2, 3].map(depth => (
                    <div key={depth} style={{ maxHeight: "52vh", overflowY: "auto", borderLeft: depth ? "1px solid var(--line)" : "none" }}>
                      {(columns[depth] || []).map(n => {
                        const isLeaf = !n.children;
                        const active = isLeaf ? n.id === valueId : trail[depth] === n.name;
                        return (
                          <div
                            key={isLeaf ? n.id : n.name}
                            style={cell(active)}
                            onClick={() => (isLeaf ? pick({ id: n.id, segments: [...trail.slice(0, 3), n.name] }) : setTrail([...trail.slice(0, depth), n.name]))}
                          >
                            {n.name}{isLeaf ? "" : " ›"}
                          </div>
                        );
                      })}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
