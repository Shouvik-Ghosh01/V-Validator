/**
 * ValidationNotepad.tsx
 *
 * Paste fix: replaced `fetch(imageDataUrl)` with direct atob() → Blob conversion.
 * fetch() on a data: URL is blocked by CSP in most browsers.
 */

import { useState, useRef, useCallback, useEffect } from "react";
import {
  ClipboardPaste, Upload, Trash2,
  Copy, FileText, Plus, X, Check, Image, Minimize2, ChevronDown, ChevronUp,
} from "lucide-react";

type NoteTag = "text_incorrect" | "screenshot_incorrect" | "step_incorrect" | "other";

interface NoteEntry {
  id: string;
  imageDataUrl: string | null;
  comment: string;
  tag: NoteTag;
  stepRef: string;
  timestamp: string;
}

const TAG_META: Record<NoteTag, { label: string; color: string; bg: string; border: string }> = {
  text_incorrect:       { label: "Text Incorrect",       color: "#ef4444", bg: "rgba(239,68,68,0.1)",    border: "rgba(239,68,68,0.3)" },
  screenshot_incorrect: { label: "Screenshot Incorrect", color: "#f59e0b", bg: "rgba(245,158,11,0.1)",   border: "rgba(245,158,11,0.3)" },
  step_incorrect:       { label: "Step Incorrect",       color: "#F5A623", bg: "rgba(245,166,35,0.1)",   border: "rgba(245,166,35,0.3)" },
  other:                { label: "Other",                color: "#6b7280", bg: "rgba(107,114,128,0.1)",  border: "rgba(107,114,128,0.3)" },
};

const MAX_W = 960, MAX_H = 720;

function uid() { return Math.random().toString(36).slice(2, 9); }

function resizeImage(dataUrl: string): Promise<string> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      let { width, height } = img;
      if (width > MAX_W || height > MAX_H) {
        const r = Math.min(MAX_W / width, MAX_H / height);
        width = Math.round(width * r);
        height = Math.round(height * r);
      }
      const c = document.createElement("canvas");
      c.width = width; c.height = height;
      c.getContext("2d")!.drawImage(img, 0, 0, width, height);
      resolve(c.toDataURL("image/jpeg", 0.9));
    };
    img.src = dataUrl;
  });
}

/**
 * Convert a data URL to a Blob WITHOUT using fetch().
 * fetch(dataUrl) is blocked by CSP in most browser environments.
 */
function dataUrlToBlob(dataUrl: string): Blob {
  const [header, base64] = dataUrl.split(",");
  const mimeMatch = header.match(/:(.*?);/);
  const mime = mimeMatch ? mimeMatch[1] : "image/jpeg";
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

function noteToText(n: NoteEntry, idx: number) {
  return [
    `[${TAG_META[n.tag].label}] Note #${idx + 1}`,
    n.stepRef ? `Step: ${n.stepRef}` : "",
    `Time: ${n.timestamp}`,
    n.comment ? `\n${n.comment}` : "",
    n.imageDataUrl ? "\n[Screenshot included]" : "",
  ].filter(Boolean).join("\n");
}

async function copyNoteToClipboard(text: string, imageDataUrl: string | null) {
  // Try to write both text + image using ClipboardItem (Chrome/Edge only)
  if (imageDataUrl && typeof ClipboardItem !== "undefined") {
    try {
      const imgBlob = dataUrlToBlob(imageDataUrl); // ← no fetch(), uses atob()
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/plain": new Blob([text], { type: "text/plain" }),
          [imgBlob.type]: imgBlob,
        }),
      ]);
      return;
    } catch {
      // ClipboardItem with image not supported — fall through to text only
    }
  }
  await navigator.clipboard.writeText(text);
}

// ─── Note card ────────────────────────────────────────────────────────────────

function NoteCard({ note, index, onChange, onDelete }: {
  note: NoteEntry; index: number;
  onChange: (id: string, p: Partial<NoteEntry>) => void;
  onDelete: (id: string) => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [copied, setCopied] = useState(false);
  const tag = TAG_META[note.tag];

  const handleCopy = async () => {
    await copyNoteToClipboard(noteToText(note, index), note.imageDataUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div style={{
      border: `1px solid ${collapsed ? "hsl(var(--border))" : tag.border}`,
      borderRadius: 8, overflow: "hidden", background: "hsl(var(--card))",
    }}>
      <div
        style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 10px", background: collapsed ? "transparent" : tag.bg, cursor: "pointer" }}
        onClick={() => setCollapsed(v => !v)}
      >
        <span style={{ fontSize: 10, color: "hsl(var(--muted-foreground))", fontWeight: 500 }}>#{index + 1}</span>
        <span style={{ fontSize: 10, fontWeight: 600, padding: "1px 7px", borderRadius: 20, background: tag.bg, color: tag.color, border: `1px solid ${tag.border}`, flexShrink: 0 }}>
          {tag.label}
        </span>
        {note.imageDataUrl && <Image size={11} style={{ color: "hsl(var(--muted-foreground))", flexShrink: 0 }} />}
        <span style={{ fontSize: 11, color: "hsl(var(--muted-foreground))", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {note.stepRef ? `${note.stepRef} · ` : ""}{note.comment?.slice(0, 40) || "No comment"}
        </span>
        <div style={{ display: "flex", gap: 1 }} onClick={e => e.stopPropagation()}>
          <button onClick={handleCopy} title="Copy note + image" style={{ padding: 3, background: "none", border: "none", cursor: "pointer", color: copied ? "#22c55e" : "hsl(var(--muted-foreground))", display: "flex" }}>
            {copied ? <Check size={12} /> : <Copy size={12} />}
          </button>
          <button onClick={() => onDelete(note.id)} style={{ padding: 3, background: "none", border: "none", cursor: "pointer", color: "hsl(var(--muted-foreground))", display: "flex" }}>
            <X size={12} />
          </button>
        </div>
        <div style={{ color: "hsl(var(--muted-foreground))", display: "flex" }}>
          {collapsed ? <ChevronDown size={12} /> : <ChevronUp size={12} />}
        </div>
      </div>

      {!collapsed && (
        <div style={{ padding: "10px", display: "flex", flexDirection: "column", gap: 8 }}>
          {note.imageDataUrl ? (
            <div style={{ position: "relative" }}>
              <img src={note.imageDataUrl} alt="" style={{ width: "100%", display: "block", borderRadius: 5, border: "1px solid hsl(var(--border))", maxHeight: 260, objectFit: "contain", background: "#000" }} />
              <button onClick={() => onChange(note.id, { imageDataUrl: null })} style={{ position: "absolute", top: 5, right: 5, background: "rgba(0,0,0,0.65)", border: "none", borderRadius: "50%", width: 22, height: 22, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff" }}>
                <Trash2 size={11} />
              </button>
            </div>
          ) : (
            <div style={{ fontSize: 11, color: "hsl(var(--muted-foreground))", padding: "8px", textAlign: "center", border: "1px dashed hsl(var(--border))", borderRadius: 5 }}>
              No screenshot — Ctrl+V to paste anywhere
            </div>
          )}

          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {(Object.entries(TAG_META) as [NoteTag, typeof TAG_META[NoteTag]][]).map(([k, v]) => (
              <button key={k} onClick={() => onChange(note.id, { tag: k })} style={{
                fontSize: 10, fontWeight: 500, padding: "2px 8px", borderRadius: 20, cursor: "pointer",
                border: `1px solid ${note.tag === k ? v.color : "hsl(var(--border))"}`,
                background: note.tag === k ? v.bg : "transparent",
                color: note.tag === k ? v.color : "hsl(var(--muted-foreground))",
              }}>{v.label}</button>
            ))}
          </div>

          <input value={note.stepRef} onChange={e => onChange(note.id, { stepRef: e.target.value })}
            placeholder="Step ref (e.g. Exec Step 2)" style={{ width: "100%", padding: "5px 8px", borderRadius: 5, border: "1px solid hsl(var(--border))", background: "hsl(var(--muted))", color: "hsl(var(--foreground))", fontSize: 11 }} />
          <textarea value={note.comment} onChange={e => onChange(note.id, { comment: e.target.value })}
            placeholder="Describe the issue…" rows={2} style={{ width: "100%", padding: "5px 8px", borderRadius: 5, border: "1px solid hsl(var(--border))", background: "hsl(var(--muted))", color: "hsl(var(--foreground))", fontSize: 11, resize: "vertical", fontFamily: "inherit" }} />
        </div>
      )}
    </div>
  );
}

// ─── Main floating widget ─────────────────────────────────────────────────────

export default function ValidationNotepad({ scriptId = "Validation" }: { scriptId?: string }) {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState<NoteEntry[]>([]);
  const [allCopied, setAllCopied] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Stable ref — keeps addImage current without re-registering the paste listener
  const addImageRef = useRef<(dataUrl: string) => void>(() => {});
  addImageRef.current = async (dataUrl: string) => {
    const resized = await resizeImage(dataUrl);
    setNotes(prev => [...prev, {
      id: uid(), imageDataUrl: resized, comment: "",
      tag: "text_incorrect", stepRef: "",
      timestamp: new Date().toLocaleTimeString(),
    }]);
    setOpen(true);
  };

  // Global paste — registered ONCE, always calls latest addImageRef
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const items = Array.from(e.clipboardData?.items || []);
      const imgItem = items.find(it => it.type.startsWith("image/"));
      if (!imgItem) return;
      const blob = imgItem.getAsFile();
      if (!blob) return;
      e.preventDefault();
      const reader = new FileReader();
      reader.onload = ev => {
        const dataUrl = ev.target?.result as string;
        if (dataUrl) addImageRef.current(dataUrl);
      };
      reader.readAsDataURL(blob);
    };
    // Use capture:true so we get the event before anything else consumes it
    document.addEventListener("paste", onPaste, true);
    return () => document.removeEventListener("paste", onPaste, true);
  }, []); // registered exactly once

  const handleFileUpload = (files: FileList | null) => {
    if (!files?.length) return;
    Array.from(files).forEach(file => {
      if (!file.type.startsWith("image/")) return;
      const reader = new FileReader();
      reader.onload = e => {
        const dataUrl = e.target?.result as string;
        if (dataUrl) addImageRef.current(dataUrl);
      };
      reader.readAsDataURL(file);
    });
  };

  // "Paste screenshot" button — uses Clipboard API (requires browser permission)
  const handlePasteButton = async () => {
    try {
      const clipItems = await navigator.clipboard.read();
      for (const item of clipItems) {
        const imgType = item.types.find(t => t.startsWith("image/"));
        if (imgType) {
          const blob = await item.getType(imgType);
          const reader = new FileReader();
          reader.onload = e => {
            const dataUrl = e.target?.result as string;
            if (dataUrl) addImageRef.current(dataUrl);
          };
          reader.readAsDataURL(blob);
          return;
        }
      }
    } catch {
      /* Permission denied or no image — fall through */
    }
    // Add empty text note as fallback
    setNotes(p => [...p, { id: uid(), imageDataUrl: null, comment: "", tag: "text_incorrect", stepRef: "", timestamp: new Date().toLocaleTimeString() }]);
    setOpen(true);
  };

  const copyAll = useCallback(async () => {
    if (!notes.length) return;
    await navigator.clipboard.writeText(notes.map((n, i) => noteToText(n, i)).join("\n\n---\n\n"));
    setAllCopied(true);
    setTimeout(() => setAllCopied(false), 2000);
  }, [notes]);

  const actionBtn: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: 5, padding: "5px 10px",
    borderRadius: 6, border: "1px solid hsl(var(--border))",
    background: "transparent", cursor: "pointer", fontSize: 11, color: "hsl(var(--foreground))",
  };

  return (
    <>
      <style>{`
        @keyframes notepad-pop {
          from { opacity: 0; transform: scale(0.88) translateY(8px); }
          to   { opacity: 1; transform: scale(1) translateY(0); }
        }
      `}</style>

      {open && (
        <div style={{
          position: "fixed", bottom: 82, right: 24, width: 430,
          maxHeight: "76vh", zIndex: 9998,
          background: "hsl(var(--card))",
          border: "1px solid hsl(var(--border))",
          borderRadius: 14,
          boxShadow: "0 10px 40px rgba(0,0,0,0.2), 0 2px 8px rgba(0,0,0,0.1)",
          display: "flex", flexDirection: "column", overflow: "hidden",
          transformOrigin: "bottom right",
          animation: "notepad-pop 0.2s cubic-bezier(0.16,1,0.3,1)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "11px 14px", background: "hsl(var(--secondary))", borderBottom: "1px solid hsl(var(--border))", flexShrink: 0 }}>
            <FileText size={15} style={{ color: "#F5A623" }} />
            <span style={{ fontWeight: 700, fontSize: 13, color: "hsl(var(--foreground))", flex: 1 }}>Validation Notepad</span>
            {notes.length > 0 && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 20, background: "rgba(239,68,68,0.1)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.2)" }}>
                {notes.length}
              </span>
            )}
            <button onClick={() => setOpen(false)} style={{ padding: 4, background: "none", border: "none", cursor: "pointer", color: "hsl(var(--muted-foreground))", display: "flex" }}>
              <Minimize2 size={14} />
            </button>
          </div>

          <div style={{ display: "flex", gap: 6, padding: "9px 12px", flexWrap: "wrap", borderBottom: "1px solid hsl(var(--border))", flexShrink: 0 }}>
            <button style={actionBtn} onClick={handlePasteButton} title="Or just press Ctrl+V anywhere">
              <ClipboardPaste size={12} /> Paste screenshot
            </button>
            <button style={actionBtn} onClick={() => fileInputRef.current?.click()}>
              <Upload size={12} /> Upload
            </button>
            <button style={actionBtn} onClick={() => {
              setNotes(p => [...p, { id: uid(), imageDataUrl: null, comment: "", tag: "text_incorrect", stepRef: "", timestamp: new Date().toLocaleTimeString() }]);
            }}>
              <Plus size={12} /> Text note
            </button>
            <input ref={fileInputRef} type="file" accept="image/*" multiple style={{ display: "none" }} onChange={e => handleFileUpload(e.target.files)} />
            {notes.length > 0 && (
              <button onClick={copyAll} style={{ ...actionBtn, marginLeft: "auto", border: `1px solid ${allCopied ? "#22c55e" : "#F5A623"}`, background: allCopied ? "rgba(34,197,94,0.08)" : "rgba(245,166,35,0.1)", color: allCopied ? "#22c55e" : "#F5A623", fontWeight: 600 }}>
                {allCopied ? <Check size={12} /> : <Copy size={12} />}
                {allCopied ? "Copied!" : "Copy all"}
              </button>
            )}
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: "10px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
            {notes.length === 0 ? (
              <div style={{ textAlign: "center", padding: "2rem 1rem", color: "hsl(var(--muted-foreground))", fontSize: 12, border: "1px dashed hsl(var(--border))", borderRadius: 8 }}>
                <div style={{ fontSize: 26, marginBottom: 8 }}>📋</div>
                Press <strong>Ctrl+V</strong> anywhere to paste a screenshot.<br />
                <span style={{ fontSize: 11, marginTop: 4, display: "block" }}>It will appear here automatically.</span>
              </div>
            ) : (
              notes.map((n, i) => (
                <NoteCard
                  key={n.id} note={n} index={i}
                  onChange={(id, p) => setNotes(prev => prev.map(x => x.id === id ? { ...x, ...p } : x))}
                  onDelete={id => setNotes(prev => prev.filter(x => x.id !== id))}
                />
              ))
            )}
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen(v => !v)}
        title="Validation Notepad — Ctrl+V to paste screenshots"
        style={{
          position: "fixed", bottom: 24, right: 24, zIndex: 9999,
          width: 54, height: 54, borderRadius: "50%",
          background: "#F5A623", border: "none", cursor: "pointer",
          boxShadow: "0 4px 18px rgba(245,166,35,0.5), 0 2px 6px rgba(0,0,0,0.15)",
          display: "flex", alignItems: "center", justifyContent: "center",
          transition: "transform 0.15s",
        }}
        onMouseEnter={e => { e.currentTarget.style.transform = "scale(1.1)"; }}
        onMouseLeave={e => { e.currentTarget.style.transform = "scale(1)"; }}
      >
        {open ? <X size={22} color="#fff" /> : <FileText size={22} color="#fff" />}
        {notes.length > 0 && !open && (
          <span style={{ position: "absolute", top: -4, right: -4, width: 20, height: 20, borderRadius: "50%", background: "#ef4444", fontSize: 10, fontWeight: 700, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", border: "2px solid hsl(var(--background))" }}>
            {notes.length > 9 ? "9+" : notes.length}
          </span>
        )}
      </button>
    </>
  );
}
