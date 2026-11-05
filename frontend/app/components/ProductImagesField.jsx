"use client";

import React, { useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const DISCARD_URL = `${API_BASE}/catalogue/discard-images`;
// Meesho's templates have four image columns; a fifth photo would never reach the upload
const MAX_IMAGES = 4;

const uploadedLinks = images => images.filter(i => i.uploaded).map(i => i.url);

function discardForm(urls) {
  const form = new FormData();
  urls.forEach(url => form.append("urls", url));
  return form;
}

// Removes this form's uploads from the bucket; throws with the backend's reason when it can't
export async function discardUploadedImages(images) {
  const urls = uploadedLinks(images);
  if (!urls.length) return;
  const res = await fetch(DISCARD_URL, { method: "POST", body: discardForm(urls) });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `HTTP ${res.status}`);
  }
}

// The product's photos, each a pasted web link or a JPEG/PNG stored in the seller's bucket through the backend.
// images: [{ url, name, uploaded }]; the first is the front photo, which the Meesho export writes to Image 1.
export default function ProductImagesField({ images, onChange, sku, onBusyChange, saving }) {
  const [busy, setBusy] = useState("");
  const [errors, setErrors] = useState([]);
  const [link, setLink] = useState("");

  // Closing or reloading the page loses the form, so its uploads go too. Best effort: nothing can wait for an answer here.
  // Not during a save: it may still commit, and a leftover file beats a product with broken photos.
  const latest = useRef({ images, saving });
  latest.current = { images, saving };
  useEffect(() => {
    const onHide = () => {
      if (latest.current.saving) return;
      const urls = uploadedLinks(latest.current.images);
      if (urls.length) navigator.sendBeacon(DISCARD_URL, discardForm(urls));
    };
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, []);

  const working = state => {
    setBusy(state);
    onBusyChange && onBusyChange(Boolean(state));
  };

  const room = MAX_IMAGES - images.length;

  const upload = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;
    const failed = files.slice(room).map(f => `${f.name}: only ${MAX_IMAGES} photos fit.`);
    const toUpload = files.slice(0, room);
    setErrors([]);
    for (const [n, file] of toUpload.entries()) {
      working(toUpload.length > 1 ? `Uploading ${n + 1} of ${toUpload.length}…` : "Uploading…");
      try {
        const form = new FormData();
        form.append("file", file);
        form.append("sku", sku || "");
        const res = await fetch(`${API_BASE}/catalogue/upload-image`, { method: "POST", body: form });
        const body = await res.json().catch(() => null);
        if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`);
        onChange(list => [...list, { url: body.url, name: file.name, uploaded: true }]);
      } catch (err) {
        failed.push(`${file.name}: ${err.message}`);
      }
    }
    working("");
    setErrors(failed);
  };

  const addLink = () => {
    const url = link.trim();
    if (!url) return;
    if (!/^https?:\/\//i.test(url)) {
      setErrors(["Paste a full https:// link to the photo."]);
      return;
    }
    if (images.some(i => i.url === url)) {
      setErrors(["That link is already added."]);
      return;
    }
    onChange(list => [...list, { url, name: url, uploaded: false }]);
    setLink("");
    setErrors([]);
  };

  const remove = async (image) => {
    working("Removing…");
    setErrors([]);
    try {
      await discardUploadedImages([image]);
      onChange(list => list.filter(i => i.url !== image.url));
    } catch (err) {
      setErrors([`${image.name} wasn't removed: ${err.message}`]);
    } finally {
      working("");
    }
  };

  const makeFront = image => onChange(list => [image, ...list.filter(i => i.url !== image.url)]);

  return (
    <div className="draft-field">
      <label>Product Images ({images.length} of {MAX_IMAGES})</label>

      {images.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "8px" }}>
          {images.map((image, i) => (
            <div key={image.url} style={{ width: "112px", fontSize: "0.72rem" }}>
              <img src={image.url} alt={image.name} style={{ width: "112px", height: "84px", objectFit: "cover", borderRadius: "4px", border: "1px solid var(--line)" }} />
              <div style={{ fontWeight: 600 }}>{i === 0 ? "Front photo" : `Photo ${i + 1}`}</div>
              <div style={{ display: "flex", gap: "8px" }}>
                {i > 0 && <button type="button" className="channel-cell-action" onClick={() => makeFront(image)} disabled={!!busy}>Make front</button>}
                <button type="button" className="channel-cell-action" onClick={() => remove(image)} disabled={!!busy}>Remove</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {room > 0 && (
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <input
            type="text"
            value={link}
            onChange={e => setLink(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addLink(); } }}
            placeholder="Paste an https:// link, or upload files"
            style={{ flex: 1, minWidth: 0 }}
          />
          <button type="button" className="btn btn-sm" onClick={addLink} disabled={!link.trim() || !!busy}>Add link</button>
          <label className="btn btn-sm" style={{ cursor: busy ? "wait" : "pointer", margin: 0, whiteSpace: "nowrap" }}>
            {busy || "Upload files"}
            <input type="file" accept="image/jpeg,image/png" multiple onChange={upload} disabled={!!busy} style={{ display: "none" }} />
          </label>
        </div>
      )}

      {errors.map(message => <div key={message} style={{ color: "var(--bad)", fontSize: "0.76rem", marginTop: "4px" }}>{message}</div>)}
    </div>
  );
}
