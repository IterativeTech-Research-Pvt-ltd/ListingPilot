"use client";

import React, { useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const DISCARD_URL = `${API_BASE}/catalogue/discard-images`;
// Meesho's templates have four image columns; a fifth photo would never reach the upload
const MAX_IMAGES = 4;
// Workers AI takes input photos under 512 x 512
const AI_INPUT_SIDE = 511;

const uploadedLinks = images => images.filter(i => i.uploaded).map(i => i.url);
// A saved product keeps only links; generated images are stored as "<SKU>_ai_<time>_<hex>" (storage_service.is_generated_photo)
export const isGeneratedImage = url => /_ai_\d{14}_[0-9a-f]{6}\.(?:jpg|png)$/.test(String(url).split("?")[0]);
// Image 1 must be a real photo, so generated images always sit after the real ones
const realFirst = list => [...list.filter(i => !i.generated), ...list.filter(i => i.generated)];

async function shrinkForGeneration(file) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, AI_INPUT_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) => canvas.toBlob(
    blob => (blob ? resolve(blob) : reject(new Error("The photo couldn't be prepared."))), "image/jpeg", 0.92
  ));
}

// One generated image from a photo (File or Blob) and the product's own facts; returns its stored link or
// throws with the backend's reason
async function requestGeneratedImage(photo, { sku, name, category, details, note, slot }) {
  const form = new FormData();
  form.append("file", await shrinkForGeneration(photo), "photo.jpg");
  form.append("sku", sku || "");
  form.append("name", name);
  form.append("category", category);
  form.append("details", details);
  form.append("note", note);
  form.append("slot", String(slot));
  const res = await fetch(`${API_BASE}/catalogue/generate-image`, { method: "POST", body: form });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.detail || `HTTP ${res.status}`);
  return body.url;
}

// Legal, tax and price fields describe the seller or the offer, not how the product looks
const NOT_VISUAL = /categor|manufactur|packer|importer|pincode|address|gst|hsn|country|quantity|price|mrp|weight|group|style id/i;

// A saved product's facts for the image prompt, from its stored fields only
export function productImageFacts(product) {
  return {
    name: product.name || "",
    category: product.category || "",
    details: Object.entries(product.attributes || {})
      .filter(([key, value]) => value != null && String(value).trim() && !NOT_VISUAL.test(key))
      .map(([key, value]) => `${key.replace(/^Meesho /, "")}: ${value}`)
      .join("; "),
  };
}

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
// images: [{ url, name, uploaded, file?, generated?, slot? }]; the first is the front photo, which the Meesho
// export writes to Image 1. Generated images come from an uploaded photo and the form's details (facts).
export default function ProductImagesField({ images, onChange, sku, onBusyChange, saving, facts }) {
  const [busy, setBusy] = useState("");
  const [errors, setErrors] = useState([]);
  const [link, setLink] = useState("");
  const [note, setNote] = useState("");

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
  const source = images.find(i => i.file);
  const hasGenerated = images.some(i => i.generated);

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
        onChange(list => realFirst([...list, { url: body.url, name: file.name, uploaded: true, file }]));
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
    onChange(list => realFirst([...list, { url, name: url, uploaded: false }]));
    setLink("");
    setErrors([]);
  };

  const remove = async (image) => {
    working("Removing…");
    setErrors([]);
    try {
      await discardUploadedImages([image]);
      onChange(list => realFirst(list.filter(i => i.url !== image.url)));
    } catch (err) {
      setErrors([`${image.name} wasn't removed: ${err.message}`]);
    } finally {
      working("");
    }
  };

  const makeFront = image => onChange(list => [image, ...list.filter(i => i.url !== image.url)]);

  // A new image, or a fresh attempt in the same place when replacing one the seller didn't like
  const generate = async (replacing) => {
    if (!facts.name.trim()) {
      setErrors(["Enter the product name first; the image is made from it."]);
      return;
    }
    working("Generating…");
    setErrors([]);
    try {
      const slot = replacing ? replacing.slot : images.filter(i => i.generated).length;
      const url = await requestGeneratedImage(source.file, { sku, ...facts, note, slot });
      const made = { url, name: "AI-generated image", uploaded: true, generated: true, slot };
      onChange(list => (replacing ? list.map(i => (i.url === replacing.url ? made : i)) : [...list, made]));
      if (replacing) await discardUploadedImages([replacing]);
    } catch (err) {
      setErrors([`Not generated: ${err.message}`]);
    } finally {
      working("");
    }
  };

  return (
    <div className="draft-field">
      <label>Product Images ({images.length} of {MAX_IMAGES})</label>

      {images.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "8px" }}>
          {images.map((image, i) => (
            <div key={image.url} style={{ width: "112px", fontSize: "0.72rem" }}>
              <img src={image.url} alt={image.name} style={{ width: "112px", height: "84px", objectFit: "cover", borderRadius: "4px", border: "1px solid var(--line)" }} />
              <div style={{ fontWeight: 600 }}>{image.generated ? "AI-generated" : i === 0 ? "Front photo" : `Photo ${i + 1}`}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "2px 8px" }}>
                {i > 0 && !image.generated && <button type="button" className="channel-cell-action" onClick={() => makeFront(image)} disabled={!!busy}>Make front</button>}
                {image.generated && source && <button type="button" className="channel-cell-action" onClick={() => generate(image)} disabled={!!busy}>Regenerate</button>}
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

      {source && (room > 0 || hasGenerated) && (
        <div style={{ display: "flex", gap: "8px", alignItems: "center", marginTop: "8px" }}>
          <input
            id="ai-image-note"
            type="text"
            value={note}
            maxLength={200}
            onChange={e => setNote(e.target.value)}
            placeholder="Optional: describe the background you want"
            aria-label="Background for AI images"
            style={{ flex: 1, minWidth: 0 }}
          />
          {room > 0 && (
            <button type="button" className="btn btn-sm" onClick={() => generate()} disabled={!!busy}>
              {busy === "Generating…" ? busy : "Generate with AI"}
            </button>
          )}
        </div>
      )}
      {hasGenerated && (
        <div style={{ color: "var(--muted)", fontSize: "0.76rem", marginTop: "4px" }}>
          AI can change colours and details. Compare each image with the real product, and regenerate or remove any that don't match.
        </div>
      )}

      {errors.map(message => <div key={message} style={{ color: "var(--bad)", fontSize: "0.76rem", marginTop: "4px" }}>{message}</div>)}
    </div>
  );
}

// The product drawer's "Generate with AI": one image from a saved product's real front photo, added after its
// photos with onSave(images), which throws when the server didn't save. A file that didn't reach the product
// is removed from the bucket again. To redo an image, the seller removes it and generates another.
export function GenerateForProduct({ product, onSave, notify }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const images = Array.isArray(product.images) ? product.images : [];
  const front = images[0];
  const blocked = !front ? "Add a real photo first; AI images are made from it."
    : isGeneratedImage(front) ? "Make a real photo #1 first; AI images are made from it."
    : images.length >= MAX_IMAGES ? `This product has ${MAX_IMAGES} photos, as many as Meesho takes.`
    : "";

  const generate = async () => {
    setBusy(true);
    let url;
    try {
      const photo = await fetch(front).then(res => {
        if (!res.ok) throw new Error(`The front photo couldn't be read (HTTP ${res.status}).`);
        return res.blob();
      }, () => {
        throw new Error("The front photo couldn't be read from its link. Upload it as a file here, make it #1, and try again.");
      });
      url = await requestGeneratedImage(photo, {
        sku: product.sku, ...productImageFacts(product), note, slot: images.filter(isGeneratedImage).length,
      });
    } catch (err) {
      notify("Image Not Generated", err.message, "error");
      setBusy(false);
      return;
    }
    try {
      await onSave([...images, url]);
      notify("AI Image Added", "Compare it with the real product. If it doesn't match, remove it and generate another.", "success");
    } catch (err) {
      let leftover = "";
      try { await discardUploadedImages([{ url, uploaded: true }]); } catch { leftover = " The generated file is still in storage."; }
      notify("Image Not Added", `The generated image wasn't saved to the product. ${err.message}${leftover}`, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ marginTop: "8px" }}>
      <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
        <input
          type="text"
          value={note}
          maxLength={200}
          onChange={e => setNote(e.target.value)}
          placeholder="Optional: describe the background you want"
          aria-label="Background for AI images"
          disabled={busy || !!blocked}
          style={{ flex: 1, minWidth: 0, padding: "5px 8px", fontSize: "0.78rem", border: "1px solid var(--line)", borderRadius: "var(--radius-sm)" }}
        />
        <button type="button" className="btn btn-sm" onClick={generate} disabled={busy || !!blocked}>
          {busy ? "Generating…" : "✨ Generate with AI"}
        </button>
      </div>
      {blocked && <div style={{ color: "var(--muted)", fontSize: "0.74rem", marginTop: "4px" }}>{blocked}</div>}
      {images.some(isGeneratedImage) && (
        <div style={{ color: "var(--muted)", fontSize: "0.74rem", marginTop: "4px" }}>
          AI can change colours and details. Compare each AI image with the real product, and remove any that don't match.
        </div>
      )}
    </div>
  );
}
