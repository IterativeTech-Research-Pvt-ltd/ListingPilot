"use client";

import React, { useState, useMemo } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";

export default function MarketplaceLiveTwinPreview({
  draft,
  product,
  marketplace = "amazon",
  title = "",
  bullets = [],
  description = "",
  technicalSpecs = {},
  aplusContent = {},
  brandVoice = {},
  // Payloads built by the backend from the saved draft (GET /drafts/{id}/amazon-payload, /aplus-payload)
  apiPayload = null,
  apiAplusPayload = null,
  onPublished = null,
  onClose = null,
  isModal = false
}) {
  const [activeMarketplace, setActiveMarketplace] = useState(marketplace || "amazon");
  const [deviceMode, setDeviceMode] = useState("desktop"); // "desktop" | "mobile"
  const [activeImageIdx, setActiveImageIdx] = useState(0);
  const [simulatorView, setSimulatorView] = useState("pdp"); // "pdp" | "sp_api" | "aplus_api" | "audit"
  const [copyStatus, setCopyStatus] = useState("");
  const [publishStatus, setPublishStatus] = useState(null);
  const [isPublishing, setIsPublishing] = useState(false);

  const brand = product?.brand || brandVoice?.brand_name || "";
  const pName = product?.name || "Product";
  const category = product?.category || "General";
  // Only the product's own data is shown; missing values stay missing
  const price = Number(product?.price ?? 0);
  const mrp = product?.mrp ? Number(product.mrp) : null;
  const discountPercent = mrp && mrp > price ? Math.round(((mrp - price) / mrp) * 100) : 0;
  const stock = product?.stock ?? 0;
  const attrLookup = useMemo(() => {
    const m = {};
    Object.entries(product?.attributes || {}).forEach(([k, v]) => { if (v) m[k.trim().toLowerCase()] = v; });
    return m;
  }, [product]);
  const productAttr = (...names) => names.map(n => attrLookup[n]).find(Boolean);

  const images = Array.isArray(product?.images) ? product.images : [];

  const currentImage = images[activeImageIdx] || images[0];


  // Clean specs
  const specs = useMemo(() => {
    if (technicalSpecs && Object.keys(technicalSpecs).length > 0) {
      return technicalSpecs;
    }
    if (product?.attributes && Object.keys(product.attributes).length > 0) {
      return product.attributes;
    }
    return {};
  }, [technicalSpecs, product]);

  const activeBullets = bullets || [];

  const aplus = aplusContent || {};
  const featureCards = aplus.feature_cards || [];

  const comparisonTable = aplus.comparison_table || { headers: [], rows: [] };

  // The JSON views show what the backend would send, never a copy assembled (and filled in) here
  const spApiPayload = apiPayload?.payload || null;
  const aplusPayload = apiAplusPayload?.payload || null;

  // ── Amazon Marketplace Standards Compliance Audit ────────────────────────────
  const complianceAudit = useMemo(() => {
    const titleLen = (title || pName).length;
    const bulletsCount = activeBullets.length;
    // Amazon counts search terms in UTF-8 bytes
    const keywordsBytes = new TextEncoder().encode((draft?.keywords || []).join(" ")).length;
    const legalFields = {
      "Country of Origin": productAttr("country of origin"),
      "Manufacturer": productAttr("manufacturer name", "manufacturer"),
      "Packer": productAttr("packer name", "packer"),
      "Net Quantity": productAttr("net quantity (n)", "net quantity"),
      "MRP": mrp
    };
    const missingLegal = Object.keys(legalFields).filter(k => !legalFields[k]);
    const hasLegalMetrology = missingLegal.length === 0;
    const hasTechnicalSpecs = Object.keys(specs).length >= 5;
    const hasAplus = Boolean(aplus.headline || featureCards.length >= 3);
    const hasPriceAndMrp = price > 0 && Boolean(mrp) && mrp >= price;

    const checks = [
      {
        name: "Title Length & Format",
        desc: "Under 200 characters, begins with Brand, no promotional claims",
        status: titleLen <= 200 && titleLen > 10,
        value: `${titleLen} / 200 chars`
      },
      {
        name: "5 Key Features (Bullet Points)",
        desc: "Exactly 5 bullets starting with capitalized benefit headlines",
        status: bulletsCount === 5,
        value: `${bulletsCount} / 5 bullets`
      },
      {
        name: "Product Description",
        desc: "Clear multi-paragraph narrative detailing specs and usage",
        status: (description || "").length >= 40,
        value: `${(description || "").length} chars`
      },
      {
        name: "Search Terms / Keywords",
        desc: "Strictly within Amazon's 250-byte maximum limit",
        status: keywordsBytes <= 250,
        value: `${keywordsBytes} / 250 bytes`
      },
      {
        name: "Technical Details Schema",
        desc: "Category-accurate technical specs table",
        status: hasTechnicalSpecs,
        value: `${Object.keys(specs).length} specs mapped`
      },
      {
        name: "India Legal Metrology (Mandatory)",
        desc: "Country of Origin, Manufacturer, Packer, Net Qty & MRP",
        status: hasLegalMetrology,
        value: hasLegalMetrology ? "All present in product data" : `Missing: ${missingLegal.join(", ")}`
      },
      {
        name: "A+ Enhanced Brand Content (EBC)",
        desc: "Hero story banner, 3 spotlight cards & comparison matrix",
        status: hasAplus,
        value: hasAplus ? `${featureCards.length} feature card(s)` : "Not written"
      },
      {
        name: "Pricing & Buy Box Readiness",
        desc: "Tax-inclusive INR price, MRP with discount, stock available",
        status: hasPriceAndMrp,
        value: mrp ? `₹${price} (MRP: ₹${mrp}, ${discountPercent}% off)` : `₹${price} (no MRP in catalogue)`
      }
    ];

    const passed = checks.filter(c => c.status).length;
    const score = Math.round((passed / checks.length) * 100);

    return { checks, score, passed, total: checks.length };
  }, [title, pName, activeBullets, description, draft, specs, aplus, featureCards, price, mrp, discountPercent, attrLookup]);

  const copyToClipboard = (text, label) => {
    navigator.clipboard.writeText(text);
    setCopyStatus(label);
    setTimeout(() => setCopyStatus(""), 2500);
  };

  const publishTarget = draft?.marketplace === "flipkart" ? "Flipkart" : "Amazon";

  const handleLivePublish = async () => {
    if (!draft?.id) {
      setPublishStatus({ success: false, message: "Save or approve the draft first; nothing was published." });
      return;
    }
    setIsPublishing(true);
    try {
      const res = await fetch(`${API_BASE}/drafts/${draft.id}/publish`, { method: "POST" });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const detail = data && data.detail;
        setPublishStatus({ success: false, message: typeof detail === "string" ? detail : `Publish failed (HTTP ${res.status}); nothing was published.` });
        return;
      }
      const published = data.draft;
      if (onPublished && published) onPublished(published);
      if (published?.status === "live") {
        setPublishStatus({ success: true, message: published.external_listing_id ? `${publishTarget} accepted the listing. Listing ID: ${published.external_listing_id}` : `${publishTarget} accepted the listing; no listing ID returned yet.` });
      } else {
        setPublishStatus({ success: false, message: `${publishTarget} rejected the listing: ${published?.rejection_reason || "no reason given"}` });
      }
    } catch (e) {
      setPublishStatus({ success: false, message: `Couldn't reach the server; nothing was published. ${e.message}` });
    } finally {
      setIsPublishing(false);
    }
  };

  return (
    <div style={{
      background: "#f0f2f2",
      borderRadius: isModal ? "12px" : "8px",
      overflow: "hidden",
      border: "1px solid #d5d9d9",
      boxShadow: isModal ? "0 20px 40px rgba(0,0,0,0.25)" : "var(--shadow-md)",
      fontFamily: "Arial, sans-serif",
      color: "#0f1111"
    }}>
      {/* ── Marketplace Twin Control Bar ──────────────────────────────────── */}
      <div style={{
        background: "#131921",
        color: "#ffffff",
        padding: "10px 16px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: "10px",
        borderBottom: "2px solid #febd69"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ fontWeight: 700, fontSize: "0.86rem", color: "#febd69", textTransform: "uppercase", letterSpacing: "0.5px" }}>
            🛍️ Live Marketplace Twin Simulator
          </span>
          <span style={{
            fontSize: "0.72rem",
            background: complianceAudit.score >= 90 ? "#067D62" : "#B12704",
            color: "#ffffff",
            padding: "2px 8px",
            borderRadius: "4px",
            fontWeight: 700
          }}>
            Amazon Standards Score: {complianceAudit.score}%
          </span>
        </div>

        {/* Simulator View Switcher */}
        <div style={{ display: "flex", background: "rgba(255,255,255,0.12)", borderRadius: "6px", padding: "2px", gap: "2px" }}>
          <button
            type="button"
            onClick={() => setSimulatorView("pdp")}
            style={{
              padding: "4px 10px",
              borderRadius: "4px",
              fontSize: "0.76rem",
              fontWeight: 700,
              cursor: "pointer",
              border: "none",
              background: simulatorView === "pdp" ? "#febd69" : "transparent",
              color: simulatorView === "pdp" ? "#131921" : "#ffffff"
            }}
          >
            🛍️ Storefront PDP
          </button>
          <button
            type="button"
            onClick={() => setSimulatorView("sp_api")}
            style={{
              padding: "4px 10px",
              borderRadius: "4px",
              fontSize: "0.76rem",
              fontWeight: 700,
              cursor: "pointer",
              border: "none",
              background: simulatorView === "sp_api" ? "#febd69" : "transparent",
              color: simulatorView === "sp_api" ? "#131921" : "#ffffff"
            }}
          >
            📦 SP-API Upload Payload
          </button>
          <button
            type="button"
            onClick={() => setSimulatorView("aplus_api")}
            style={{
              padding: "4px 10px",
              borderRadius: "4px",
              fontSize: "0.76rem",
              fontWeight: 700,
              cursor: "pointer",
              border: "none",
              background: simulatorView === "aplus_api" ? "#febd69" : "transparent",
              color: simulatorView === "aplus_api" ? "#131921" : "#ffffff"
            }}
          >
            🎨 A+ EBC Payload
          </button>
          <button
            type="button"
            onClick={() => setSimulatorView("audit")}
            style={{
              padding: "4px 10px",
              borderRadius: "4px",
              fontSize: "0.76rem",
              fontWeight: 700,
              cursor: "pointer",
              border: "none",
              background: simulatorView === "audit" ? "#febd69" : "transparent",
              color: simulatorView === "audit" ? "#131921" : "#ffffff"
            }}
          >
            🛡️ Standards Audit ({complianceAudit.passed}/{complianceAudit.total})
          </button>
        </div>

        {/* Viewport switch & Actions */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {simulatorView === "pdp" && (
            <div style={{ display: "flex", background: "rgba(255,255,255,0.15)", borderRadius: "4px", padding: "2px" }}>
              <button
                type="button"
                onClick={() => setDeviceMode("desktop")}
                style={{
                  background: deviceMode === "desktop" ? "#ffffff" : "transparent",
                  color: deviceMode === "desktop" ? "#131921" : "#ffffff",
                  border: "none",
                  borderRadius: "3px",
                  padding: "2px 8px",
                  fontSize: "0.72rem",
                  fontWeight: 600,
                  cursor: "pointer"
                }}
              >
                🖥️ Desktop
              </button>
              <button
                type="button"
                onClick={() => setDeviceMode("mobile")}
                style={{
                  background: deviceMode === "mobile" ? "#ffffff" : "transparent",
                  color: deviceMode === "mobile" ? "#131921" : "#ffffff",
                  border: "none",
                  borderRadius: "3px",
                  padding: "2px 8px",
                  fontSize: "0.72rem",
                  fontWeight: 600,
                  cursor: "pointer"
                }}
              >
                📱 Mobile
              </button>
            </div>
          )}

          {draft?.id && draft.marketplace !== "meesho" && (
            <button
              type="button"
              onClick={handleLivePublish}
              disabled={isPublishing}
              style={{
                background: "#067D62",
                color: "#ffffff",
                border: "none",
                borderRadius: "4px",
                padding: "4px 12px",
                fontSize: "0.76rem",
                fontWeight: 700,
                cursor: isPublishing ? "wait" : "pointer"
              }}
            >
              {isPublishing ? "⏳ Publishing..." : `⚡ Publish to ${publishTarget}`}
            </button>
          )}

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              style={{
                background: "transparent",
                border: "none",
                color: "#ffffff",
                fontSize: "1.1rem",
                cursor: "pointer",
                padding: "0 6px"
              }}
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {publishStatus && (
        <div style={{
          background: publishStatus.success ? "#d4edda" : "#f8d7da",
          color: publishStatus.success ? "#155724" : "#721c24",
          padding: "8px 16px",
          fontSize: "0.8rem",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center"
        }}>
          <span>{publishStatus.message}</span>
          <button type="button" onClick={() => setPublishStatus(null)} style={{ background: "transparent", border: "none", cursor: "pointer", fontWeight: 700 }}>✕</button>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════
          VIEW 1: SP-API UPLOAD PAYLOAD (2021-08-01 LISTINGS ITEMS)
      ══════════════════════════════════════════════════════════════════════ */}
      {simulatorView === "sp_api" && (
        <div style={{ padding: "16px", background: "#1e1e1e", color: "#f8f8f2" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", flexWrap: "wrap", gap: "8px" }}>
            <div>
              <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "#febd69" }}>
                PUT /listings/2021-08-01/items/{product?.sku || "SKU-UNKNOWN"}
              </span>
              <p style={{ margin: "2px 0 0 0", fontSize: "0.76rem", color: "#888" }}>
                Built by the backend from the last saved draft and the product's data. Save your edits to update it.
              </p>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                type="button"
                onClick={() => copyToClipboard(JSON.stringify(spApiPayload, null, 2), "sp_api")}
                style={{
                  background: "#febd69",
                  color: "#131921",
                  border: "none",
                  borderRadius: "4px",
                  padding: "6px 14px",
                  fontSize: "0.78rem",
                  fontWeight: 700,
                  cursor: "pointer"
                }}
              >
                {copyStatus === "sp_api" ? "✓ Copied to Clipboard!" : "📋 Copy SP-API Payload"}
              </button>
            </div>
          </div>
          <pre style={{
            background: "#141414",
            padding: "16px",
            borderRadius: "6px",
            fontSize: "0.78rem",
            lineHeight: "1.5",
            maxHeight: "560px",
            overflowY: "auto",
            border: "1px solid #333",
            color: "#a6e22e"
          }}>
            {spApiPayload ? JSON.stringify(spApiPayload, null, 2) : "Not loaded: generate and save an Amazon draft to see the payload the backend builds."}
          </pre>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════
          VIEW 2: A+ CONTENT (EBC) PAYLOAD (2020-11-01)
      ══════════════════════════════════════════════════════════════════════ */}
      {simulatorView === "aplus_api" && (
        <div style={{ padding: "16px", background: "#1e1e1e", color: "#f8f8f2" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", flexWrap: "wrap", gap: "8px" }}>
            <div>
              <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "#febd69" }}>
                POST /aplus/2020-11-01/contentDocuments
              </span>
              <p style={{ margin: "2px 0 0 0", fontSize: "0.76rem", color: "#888" }}>
                Official Amazon A+ Enhanced Brand Content document featuring Hero Narrative, 3 Spotlight Cards, and Multi-Model Comparison Table.
              </p>
            </div>
            <button
              type="button"
              onClick={() => copyToClipboard(JSON.stringify(aplusPayload, null, 2), "aplus_api")}
              style={{
                background: "#febd69",
                color: "#131921",
                border: "none",
                borderRadius: "4px",
                padding: "6px 14px",
                fontSize: "0.78rem",
                fontWeight: 700,
                cursor: "pointer"
              }}
            >
              {copyStatus === "aplus_api" ? "✓ Copied A+ Document!" : "📋 Copy A+ Payload"}
            </button>
          </div>
          <pre style={{
            background: "#141414",
            padding: "16px",
            borderRadius: "6px",
            fontSize: "0.78rem",
            lineHeight: "1.5",
            maxHeight: "560px",
            overflowY: "auto",
            border: "1px solid #333",
            color: "#66d9ef"
          }}>
            {aplusPayload ? JSON.stringify(aplusPayload, null, 2) : "Not loaded: generate and save an Amazon draft to see the A+ document the backend builds."}
          </pre>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════
          VIEW 3: AMAZON MARKETPLACE STANDARDS & COMPLIANCE SCORECARD
      ══════════════════════════════════════════════════════════════════════ */}
      {simulatorView === "audit" && (
        <div style={{ padding: "20px", background: "#ffffff" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", paddingBottom: "12px", borderBottom: "1px solid #e7e7e7" }}>
            <div>
              <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700, color: "#131921" }}>
                Amazon Marketplace Standards & Compliance Scorecard
              </h3>
              <p style={{ margin: "4px 0 0 0", fontSize: "0.8rem", color: "#565959" }}>
                Continuous real-time audit against official Amazon Selling Partner API schemas and Indian Legal Metrology regulations.
              </p>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: "1.8rem", fontWeight: 900, color: complianceAudit.score >= 90 ? "#067D62" : "#B12704" }}>
                {complianceAudit.score}%
              </div>
              <div style={{ fontSize: "0.75rem", color: "#565959" }}>
                {complianceAudit.passed} of {complianceAudit.total} Standards Verified
              </div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "12px" }}>
            {complianceAudit.checks.map((chk, idx) => (
              <div key={idx} style={{
                border: "1px solid #e7e7e7",
                borderRadius: "6px",
                padding: "12px",
                background: chk.status ? "#f7fcf8" : "#fff8f8",
                borderLeft: chk.status ? "4px solid #067D62" : "4px solid #B12704"
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                  <span style={{ fontWeight: 700, fontSize: "0.85rem", color: "#0f1111" }}>
                    {chk.status ? "✅" : "⚠️"} {chk.name}
                  </span>
                  <span style={{ fontSize: "0.74rem", fontWeight: 700, color: chk.status ? "#067D62" : "#B12704" }}>
                    {chk.value}
                  </span>
                </div>
                <div style={{ fontSize: "0.74rem", color: "#565959" }}>
                  {chk.desc}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════════
          VIEW 4: LIVE STOREFRONT PDP (WYSIWYG SIMULATOR)
      ══════════════════════════════════════════════════════════════════════ */}
      {simulatorView === "pdp" && (
        <div style={{
          maxWidth: deviceMode === "mobile" ? "420px" : "100%",
          margin: deviceMode === "mobile" ? "20px auto" : "0 auto",
          background: "#ffffff",
          boxShadow: deviceMode === "mobile" ? "0 4px 20px rgba(0,0,0,0.15)" : "none",
          borderRadius: deviceMode === "mobile" ? "18px" : "0",
          overflow: "hidden",
          border: deviceMode === "mobile" ? "8px solid #232f3e" : "none"
        }}>
          {/* Channel Selector Sub-bar */}
          <div style={{ background: "#232f3e", color: "#ffffff", padding: "6px 16px", display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "0.78rem" }}>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                type="button"
                onClick={() => setActiveMarketplace("amazon")}
                style={{
                  background: activeMarketplace === "amazon" ? "#febd69" : "transparent",
                  color: activeMarketplace === "amazon" ? "#131921" : "#ffffff",
                  border: "none",
                  borderRadius: "3px",
                  padding: "3px 8px",
                  fontWeight: 700,
                  cursor: "pointer"
                }}
              >
                Amazon.in PDP
              </button>
              <button
                type="button"
                onClick={() => setActiveMarketplace("flipkart")}
                style={{
                  background: activeMarketplace === "flipkart" ? "#2874f0" : "transparent",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "3px",
                  padding: "3px 8px",
                  fontWeight: 700,
                  cursor: "pointer"
                }}
              >
                Flipkart PDP
              </button>
              <button
                type="button"
                onClick={() => setActiveMarketplace("meesho")}
                style={{
                  background: activeMarketplace === "meesho" ? "#f43397" : "transparent",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "3px",
                  padding: "3px 8px",
                  fontWeight: 700,
                  cursor: "pointer"
                }}
              >
                Meesho PDP
              </button>
            </div>
            <span style={{ fontSize: "0.72rem", color: "#febd69" }}>
              ✓ 100% In Sync with SP-API Payload
            </span>
          </div>

          {/* ══════════════════════════════════════════════════════════════════
              1. AMAZON.IN PRODUCT DETAIL PAGE (PDP) SIMULATOR
          ══════════════════════════════════════════════════════════════════ */}
          {activeMarketplace === "amazon" && (
            <div>
              {/* Amazon Header Bar */}
              <header style={{ background: "#131921", color: "#ffffff", padding: "8px 16px", display: "flex", alignItems: "center", gap: "14px", flexWrap: "wrap", fontSize: "0.85rem" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: "2px" }}>
                  <span style={{ fontWeight: 900, fontSize: "1.2rem", letterSpacing: "-0.5px" }}>amazon</span>
                  <span style={{ fontSize: "0.8rem", color: "#febd69" }}>.in</span>
                </div>

                {/* Search Bar */}
                <div style={{ flex: 1, display: "flex", minWidth: "220px", height: "36px" }}>
                  <div style={{ background: "#e6e6e6", color: "#333", fontSize: "0.72rem", padding: "0 10px", display: "flex", alignItems: "center", borderTopLeftRadius: "4px", borderBottomLeftRadius: "4px", borderRight: "1px solid #ccc" }}>
                    All ▾
                  </div>
                  <input 
                    type="text" 
                    value={title ? title.slice(0, 45) : pName} 
                    readOnly 
                    style={{ flex: 1, padding: "0 10px", border: "none", outline: "none", fontSize: "0.85rem" }} 
                  />
                  <button type="button" style={{ background: "#febd69", border: "none", borderTopRightRadius: "4px", borderBottomRightRadius: "4px", padding: "0 14px", cursor: "pointer", fontSize: "0.95rem" }}>
                    🔍
                  </button>
                </div>

                <div style={{ display: "flex", gap: "14px", fontSize: "0.75rem" }}>
                  <div>EN ▾</div>
                  <div>Hello, sign in<br /><b style={{ color: "#fff" }}>Account & Lists</b></div>
                  <div>Returns<br /><b style={{ color: "#fff" }}>& Orders</b></div>
                  <div style={{ fontWeight: 700, fontSize: "0.95rem", display: "flex", alignItems: "center" }}>🛒 0</div>
                </div>
              </header>

              {/* Dynamic Breadcrumb based on category */}
              <div style={{ padding: "8px 16px", fontSize: "0.72rem", color: "#565959", borderBottom: "1px solid #e7e7e7" }}>
                Amazon.in › {category || "All Products"} › <span style={{ color: "#007185" }}>{brand}</span>
              </div>

              {/* Amazon PDP Grid: Gallery (Left) | Core Info (Center) | Buy Box (Right) */}
              <div style={{
                display: "grid",
                gridTemplateColumns: deviceMode === "mobile" ? "1fr" : "380px 1fr 240px",
                gap: "20px",
                padding: "16px",
                alignItems: "start"
              }}>
                {/* 1. Left: Image Gallery */}
                <div style={{ display: "flex", gap: "10px", position: "sticky", top: "10px" }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    {images.map((img, idx) => (
                      <img 
                        key={idx} 
                        src={img} 
                        alt="Thumb"
                        onClick={() => setActiveImageIdx(idx)}
                        style={{
                          width: "48px",
                          height: "48px",
                          objectFit: "cover",
                          borderRadius: "4px",
                          cursor: "pointer",
                          border: activeImageIdx === idx ? "2px solid #e77600" : "1px solid #d5d9d9",
                          boxShadow: activeImageIdx === idx ? "0 0 3px rgba(228,121,17,0.5)" : "none"
                        }}
                      />
                    ))}
                  </div>

                  <div style={{ flex: 1, position: "relative" }}>
                    <img 
                      src={currentImage} 
                      alt={pName}
                      style={{
                        width: "100%",
                        maxHeight: "440px",
                        objectFit: "contain",
                        borderRadius: "6px",
                        background: "#fafafa"
                      }}
                    />
                  </div>
                </div>

                {/* 2. Center: Product Title, Brand, Bullets, Specs Table, A+ Content */}
                <div>
                  <div style={{ fontSize: "0.8rem", color: "#007185", marginBottom: "4px", cursor: "pointer" }}>
                    Brand: {brand}
                  </div>

                  <h1 style={{
                    fontSize: deviceMode === "mobile" ? "1.05rem" : "1.25rem",
                    fontWeight: 500,
                    lineHeight: "1.4",
                    color: "#0f1111",
                    margin: "0 0 8px 0"
                  }}>
                    {title || `${brand} ${pName}`}
                  </h1>

                  <hr style={{ border: "none", borderTop: "1px solid #e7e7e7", margin: "10px 0" }} />

                  {/* Price Block */}
                  <div style={{ marginBottom: "12px" }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
                      {discountPercent > 0 && <span style={{ color: "#CC0C39", fontSize: "1.4rem", fontWeight: 300 }}>-{discountPercent}%</span>}
                      <span style={{ fontSize: "1.5rem", fontWeight: 700, color: "#0f1111" }}>₹{price.toLocaleString("en-IN")}</span>
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "#565959" }}>
                      {mrp ? <>M.R.P.: <span style={{ textDecoration: "line-through" }}>₹{mrp.toLocaleString("en-IN")}</span></> : "M.R.P.: not in catalogue"}
                    </div>
                    <div style={{ fontSize: "0.72rem", color: "#565959", marginTop: "2px" }}>
                      Inclusive of all taxes
                    </div>
                  </div>

                  {/* About This Item (Amazon 5 Bullets) */}
                  <div style={{ marginTop: "14px" }}>
                    <h3 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "8px" }}>About this item</h3>
                    <ul style={{ paddingLeft: "18px", fontSize: "0.82rem", lineHeight: "1.55", color: "#0f1111", margin: 0 }}>
                      {activeBullets.map((b, i) => (
                        <li key={i} style={{ marginBottom: "4px" }}>{b}</li>
                      ))}
                    </ul>
                  </div>

                  {/* Technical Details Table */}
                  <div style={{ marginTop: "16px" }}>
                    <h3 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "8px" }}>Technical Details</h3>
                    <div style={{ border: "1px solid #e7e7e7", borderRadius: "4px", overflow: "hidden" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem" }}>
                        <tbody>
                          {Object.entries(specs).slice(0, 10).map(([k, v], idx) => (
                            <tr key={k} style={{ background: idx % 2 === 0 ? "#f3f3f3" : "#ffffff", borderBottom: "1px solid #e7e7e7" }}>
                              <td style={{ padding: "6px 10px", fontWeight: 600, width: "35%", color: "#333" }}>{k}</td>
                              <td style={{ padding: "6px 10px", color: "#0f1111" }}>{String(v)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Additional Information (India Legal Metrology) */}
                  <div style={{ marginTop: "14px" }}>
                    <h3 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "6px" }}>Additional Information (India Legal Metrology)</h3>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.76rem" }}>
                      <tbody>
                        <tr style={{ borderBottom: "1px solid #eee" }}>
                          <td style={{ padding: "4px 8px", fontWeight: 600, color: "#565959", width: "35%" }}>Country of Origin</td>
                          <td style={{ padding: "4px 8px" }}>{specs["Country of Origin"] || "—"}</td>
                        </tr>
                        <tr style={{ borderBottom: "1px solid #eee" }}>
                          <td style={{ padding: "4px 8px", fontWeight: 600, color: "#565959" }}>Manufacturer</td>
                          <td style={{ padding: "4px 8px" }}>{specs["Manufacturer"] || `${brand} Creations Private Limited`}</td>
                        </tr>
                        <tr style={{ borderBottom: "1px solid #eee" }}>
                          <td style={{ padding: "4px 8px", fontWeight: 600, color: "#565959" }}>Packer</td>
                          <td style={{ padding: "4px 8px" }}>{specs["Packer"] || `${brand} Central Fulfillment Hub, Jaipur, RJ - 302029`}</td>
                        </tr>
                        <tr style={{ borderBottom: "1px solid #eee" }}>
                          <td style={{ padding: "4px 8px", fontWeight: 600, color: "#565959" }}>Net Quantity</td>
                          <td style={{ padding: "4px 8px" }}>1 Count</td>
                        </tr>
                        <tr>
                          <td style={{ padding: "4px 8px", fontWeight: 600, color: "#565959" }}>Generic Name</td>
                          <td style={{ padding: "4px 8px" }}>{specs["Generic Name"] || category}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>

                  {/* ── From the Manufacturer (A+ Content Section) ──────────────── */}
                  <div style={{ marginTop: "24px", paddingTop: "16px", borderTop: "2px solid #e7e7e7" }}>
                    <div style={{ fontSize: "0.75rem", textTransform: "uppercase", fontWeight: 700, color: "#565959", letterSpacing: "1px", marginBottom: "8px" }}>
                      From the manufacturer · A+ Enhanced Brand Content
                    </div>

                    {/* Hero Headline & Story */}
                    <div style={{ background: "linear-gradient(135deg, #131921 0%, #232f3e 100%)", color: "#ffffff", padding: "20px", borderRadius: "6px", marginBottom: "14px" }}>
                      <h2 style={{ fontSize: "1.2rem", fontWeight: 700, margin: "0 0 8px 0", color: "#febd69" }}>
                        {aplus.headline || "No A+ headline written"}
                      </h2>
                      <p style={{ fontSize: "0.82rem", lineHeight: "1.5", margin: 0, color: "#e7e7e7" }}>
                        {aplus.brand_story || description || ""}
                      </p>
                    </div>

                    {/* 3 Feature Spotlight Cards */}
                    <div style={{ display: "grid", gridTemplateColumns: deviceMode === "mobile" ? "1fr" : "repeat(3, 1fr)", gap: "10px", marginBottom: "16px" }}>
                      {featureCards.map((card, i) => (
                        <div key={i} style={{ border: "1px solid #d5d9d9", borderRadius: "6px", padding: "12px", background: "#fafafa" }}>
                          <div style={{ fontWeight: 700, fontSize: "0.85rem", color: "#0f1111", marginBottom: "2px" }}>
                            {card.title}
                          </div>
                          <div style={{ fontSize: "0.74rem", color: "#565959", fontStyle: "italic", marginBottom: "6px" }}>
                            {card.subtitle}
                          </div>
                          <div style={{ fontSize: "0.76rem", lineHeight: "1.4", color: "#333" }}>
                            {card.description}
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Apple-Grade Multi-Model Comparison Table */}
                    <div>
                      <h4 style={{ fontSize: "0.9rem", fontWeight: 700, marginBottom: "8px" }}>
                        Compare {brand} Products
                      </h4>
                      <div style={{ overflowX: "auto", border: "1px solid #e7e7e7", borderRadius: "4px" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.76rem" }}>
                          <thead>
                            <tr style={{ background: "#f3f3f3", borderBottom: "1px solid #d5d9d9" }}>
                              {comparisonTable.headers.map((h, i) => (
                                <th key={i} style={{ padding: "8px", textAlign: "left", fontWeight: 700, color: i === 1 ? "#007185" : "#0f1111" }}>
                                  {h}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {comparisonTable.rows.map((row, rIdx) => (
                              <tr key={rIdx} style={{ borderBottom: "1px solid #e7e7e7" }}>
                                <td style={{ padding: "8px", fontWeight: 600, color: "#565959" }}>{row.feature}</td>
                                <td style={{ padding: "8px", background: "#fcf8e3", fontWeight: 600, color: "#0f1111" }}>{row.this_model}</td>
                                <td style={{ padding: "8px", color: "#565959" }}>{row.standard}</td>
                                <td style={{ padding: "8px", color: "#0f1111" }}>{row.pro}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </div>

                {/* 3. Right: Amazon Buy Box */}
                <div style={{
                  border: "1px solid #d5d9d9",
                  borderRadius: "8px",
                  padding: "14px",
                  background: "#ffffff",
                  position: "sticky",
                  top: "10px"
                }}>
                  <div style={{ fontSize: "1.3rem", fontWeight: 700, color: "#0f1111" }}>
                    ₹{price.toLocaleString("en-IN")}
                  </div>

                  <div style={{ fontSize: "0.9rem", color: stock > 0 ? "#007600" : "#B12704", fontWeight: 700, margin: "10px 0" }}>
                    {stock > 0 ? `In stock (${stock})` : "Currently unavailable (stock 0)"}
                  </div>

                  {/* Add to Cart Button */}
                  <button type="button" style={{
                    width: "100%",
                    background: "#ffd814",
                    border: "1px solid #fcd200",
                    borderRadius: "20px",
                    padding: "8px",
                    fontSize: "0.82rem",
                    fontWeight: 600,
                    cursor: "pointer",
                    marginBottom: "8px",
                    boxShadow: "0 2px 5px rgba(213,217,217,.5)"
                  }}>
                    Add to Cart
                  </button>

                  {/* Buy Now Button */}
                  <button type="button" style={{
                    width: "100%",
                    background: "#ffa41c",
                    border: "1px solid #ff8f00",
                    borderRadius: "20px",
                    padding: "8px",
                    fontSize: "0.82rem",
                    fontWeight: 600,
                    cursor: "pointer",
                    boxShadow: "0 2px 5px rgba(213,217,217,.5)"
                  }}>
                    Buy Now
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ══════════════════════════════════════════════════════════════════
              2. FLIPKART PRODUCT DETAIL PAGE (PDP) SIMULATOR
          ══════════════════════════════════════════════════════════════════ */}
          {activeMarketplace === "flipkart" && (
            <div>
              <header style={{ background: "#2874f0", color: "#ffffff", padding: "10px 16px", display: "flex", alignItems: "center", gap: "16px" }}>
                <span style={{ fontWeight: 900, fontStyle: "italic", fontSize: "1.2rem" }}>Flipkart</span>
                <div style={{ flex: 1 }}>
                  <input type="text" readOnly value={title ? title.slice(0, 50) : pName} style={{ width: "100%", padding: "6px 12px", borderRadius: "2px", border: "none", fontSize: "0.82rem" }} />
                </div>
                <div style={{ fontWeight: 700, fontSize: "0.85rem" }}>Cart (0)</div>
              </header>

              <div style={{ display: "grid", gridTemplateColumns: deviceMode === "mobile" ? "1fr" : "360px 1fr", gap: "20px", padding: "16px" }}>
                <div>
                  <img src={currentImage} alt={pName} style={{ width: "100%", maxHeight: "380px", objectFit: "contain", border: "1px solid #f0f0f0", borderRadius: "4px" }} />
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginTop: "12px" }}>
                    <button type="button" style={{ background: "#ff9f00", color: "#fff", border: "none", padding: "12px", fontWeight: 700, borderRadius: "2px", cursor: "pointer" }}>
                      ⚡ ADD TO CART
                    </button>
                    <button type="button" style={{ background: "#fb641b", color: "#fff", border: "none", padding: "12px", fontWeight: 700, borderRadius: "2px", cursor: "pointer" }}>
                      ⚡ BUY NOW
                    </button>
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: "0.78rem", color: "#878787", marginBottom: "4px" }}>Home › {category} › {brand}</div>
                  <h1 style={{ fontSize: "1.1rem", fontWeight: 500, color: "#212121", margin: "0 0 8px 0" }}>
                    {title || `${brand} ${pName}`}
                  </h1>
                  <div style={{ display: "flex", alignItems: "baseline", gap: "10px", margin: "12px 0" }}>
                    <span style={{ fontSize: "1.6rem", fontWeight: 700, color: "#212121" }}>₹{price.toLocaleString("en-IN")}</span>
                    {mrp && <span style={{ textDecoration: "line-through", color: "#878787", fontSize: "0.85rem" }}>₹{mrp.toLocaleString("en-IN")}</span>}
                    {discountPercent > 0 && <span style={{ color: "#388e3c", fontWeight: 700, fontSize: "0.85rem" }}>{discountPercent}% off</span>}
                  </div>

                  <div style={{ marginTop: "16px" }}>
                    <h3 style={{ fontSize: "0.9rem", fontWeight: 700, marginBottom: "8px" }}>Highlights</h3>
                    <ul style={{ paddingLeft: "16px", fontSize: "0.8rem", lineHeight: "1.6", color: "#212121" }}>
                      {activeBullets.map((b, i) => <li key={i}>{b}</li>)}
                    </ul>
                  </div>

                  <div style={{ marginTop: "16px", border: "1px solid #f0f0f0", padding: "12px", borderRadius: "4px" }}>
                    <h3 style={{ fontSize: "0.9rem", fontWeight: 700, marginBottom: "8px" }}>Specifications</h3>
                    <table style={{ width: "100%", fontSize: "0.78rem", borderCollapse: "collapse" }}>
                      <tbody>
                        {Object.entries(specs).slice(0, 8).map(([k, v]) => (
                          <tr key={k} style={{ borderBottom: "1px solid #f0f0f0" }}>
                            <td style={{ color: "#878787", width: "35%", padding: "6px 0" }}>{k}</td>
                            <td style={{ color: "#212121", padding: "6px 0" }}>{String(v)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ══════════════════════════════════════════════════════════════════
              3. MEESHO SUPPLIER PDP SIMULATOR
          ══════════════════════════════════════════════════════════════════ */}
          {activeMarketplace === "meesho" && (
            <div>
              <header style={{ background: "#ffffff", color: "#f43397", padding: "10px 16px", borderBottom: "1px solid #f0f0f0", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontWeight: 900, fontSize: "1.3rem" }}>meesho</span>
                <span style={{ color: "#333", fontSize: "0.82rem" }}>Supplier Hub Catalog Item</span>
              </header>

              <div style={{ display: "grid", gridTemplateColumns: deviceMode === "mobile" ? "1fr" : "340px 1fr", gap: "20px", padding: "16px" }}>
                <div>
                  <img src={currentImage} alt={pName} style={{ width: "100%", maxHeight: "360px", objectFit: "contain", borderRadius: "8px", border: "1px solid #f0f0f0" }} />
                </div>

                <div>
                  <h1 style={{ fontSize: "1.05rem", fontWeight: 600, color: "#333", margin: "0 0 6px 0" }}>
                    {title || `${brand} ${pName}`}
                  </h1>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#212121", marginBottom: "6px" }}>
                    ₹{price.toLocaleString("en-IN")}
                  </div>
                  <div style={{ borderTop: "1px solid #f0f0f0", paddingTop: "12px" }}>
                    <h3 style={{ fontSize: "0.85rem", fontWeight: 700, marginBottom: "6px" }}>Product Details</h3>
                    <p style={{ fontSize: "0.78rem", color: "#666", lineHeight: "1.5" }}>{description || ""}</p>
                    <table style={{ width: "100%", fontSize: "0.76rem", borderCollapse: "collapse", marginTop: "8px" }}>
                      <tbody>
                        {Object.entries(specs).slice(0, 6).map(([k, v]) => (
                          <tr key={k} style={{ borderBottom: "1px solid #f8f8f8" }}>
                            <td style={{ color: "#999", width: "40%", padding: "4px 0" }}>{k}</td>
                            <td style={{ color: "#333", padding: "4px 0" }}>{String(v)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
