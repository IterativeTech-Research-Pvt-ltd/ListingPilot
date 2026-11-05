"use client";

import React from "react";

// The draft's real rule results from the backend: each error (blocks approval) and warning with its
// message, so the seller sees what to fix. Never a stand-in pass list.
export default function RuleChecks({ ruleResults, rejectionReason }) {
  // Why the draft was last rejected (by the seller or by Meesho's QC), until it's approved again
  const rejected = rejectionReason ? (
    <div className="rule-item fail">
      <span style={{ fontSize: "1rem" }}>↩</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600 }}>Rejected last time</div>
        <div style={{ fontSize: "0.74rem" }}>{rejectionReason}</div>
      </div>
    </div>
  ) : null;

  if (!ruleResults) {
    return (
      <div className="rule-checks">
        <div className="rule-item">
          <span style={{ fontSize: "1rem" }}>…</span>
          <div style={{ flex: 1, color: "var(--muted)" }}>Not checked yet: generate the copy to run the rule checks.</div>
        </div>
      </div>
    );
  }

  const issues = (ruleResults.issues || []).filter(i => i.level === "error" || i.level === "warning");
  if (!issues.length) {
    return (
      <div className="rule-checks">
        {rejected}
        <div className="rule-item pass">
          <span style={{ fontSize: "1rem" }}>✓</span>
          <div style={{ flex: 1, fontWeight: 600 }}>No rule problems found</div>
        </div>
      </div>
    );
  }

  const errors = issues.filter(i => i.level === "error").length;
  return (
    <div className="rule-checks">
      {rejected}
      <div style={{ fontSize: "0.74rem", color: "var(--muted)" }}>
        {errors ? `${errors} error(s) block approval` : "Warnings only; approval isn't blocked"}
      </div>
      {issues.map((issue, i) => (
        <div key={i} className={`rule-item ${issue.level === "error" ? "fail" : "warn"}`}>
          <span style={{ fontSize: "1rem" }}>{issue.level === "error" ? "✕" : "⚠"}</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600 }}>{issue.level === "error" ? "Error" : "Warning"} · {issue.field}</div>
            <div style={{ fontSize: "0.74rem" }}>{issue.message}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
