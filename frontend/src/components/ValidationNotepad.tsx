/**
 * ValidationNotepad.tsx
 *
 * Added: Export dropdown — Download as PDF / Markdown / Text
 * PDF uses jsPDF (loaded dynamically from CDN). Images are embedded in all formats.
 *
 * Paste fix: replaced `fetch(imageDataUrl)` with direct atob() → Blob conversion.
 * fetch() on a data: URL is blocked by CSP in most browsers.
 */

import { useState, useRef, useCallback, useEffect } from "react";
import {
  ClipboardPaste, Upload, Trash2,
  Copy, FileText, Plus, X, Check, Image as ImageIcon, Minimize2,
  ChevronDown, ChevronUp, Download,
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

/** Build a self-contained HTML string for one note, with base64 image embedded. */
function noteToHtml(n: NoteEntry, idx: number): string {
  const tag = TAG_META[n.tag];
  const metaLines = [
    n.stepRef ? `<div style="margin:2px 0;font-size:12px;color:#666"><b>Step ref:</b> ${n.stepRef}</div>` : "",
    `<div style="margin:2px 0;font-size:12px;color:#666"><b>Time:</b> ${n.timestamp}</div>`,
  ].filter(Boolean).join("");

  const commentHtml = n.comment
    ? `<div style="margin:8px 0;font-size:13px;color:#222;white-space:pre-wrap"><span style="font-weight:600;color:#555;font-size:11px">Comment: </span>${escHtml(n.comment)}</div>`
    : "";

  const imageHtml = n.imageDataUrl
    ? `<div style="margin-top:8px"><img src="${n.imageDataUrl}" style="max-width:100%;border-radius:4px;border:1px solid #ddd" /></div>`
    : "";

  return `
<div style="font-family:system-ui,sans-serif;border:1px solid ${tag.border};border-radius:8px;padding:12px 14px;margin-bottom:12px;background:#fff">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
    <span style="font-size:11px;color:#999">#${idx + 1}</span>
    <span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:20px;background:${tag.bg};color:${tag.color};border:1px solid ${tag.border}">${tag.label}</span>
  </div>
  ${metaLines}
  ${commentHtml}
  ${imageHtml}
</div>`.trim();
}

function escHtml(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/**
 * Write text/html + text/plain simultaneously to the clipboard.
 * Rich targets (Notion, Word, Gmail, Outlook) get the HTML with embedded images.
 * Plain-text targets (terminal, plain editors) get the fallback text.
 */
async function writeRichClipboard(html: string, plain: string) {
  if (typeof ClipboardItem === "undefined") {
    // Old browser — text-only fallback
    await navigator.clipboard.writeText(plain);
    return;
  }
  try {
    await navigator.clipboard.write([
      new ClipboardItem({
        "text/html":  new Blob([html],  { type: "text/html" }),
        "text/plain": new Blob([plain], { type: "text/plain" }),
      }),
    ]);
  } catch (e) {
    // Permission denied or unsupported — degrade to plain text
    console.warn("Rich clipboard write failed, falling back to plain text:", e);
    await navigator.clipboard.writeText(plain);
  }
}

async function copyNoteToClipboard(note: NoteEntry, idx: number) {
  const plain = noteToText(note, idx);
  const html  = `<!DOCTYPE html><html><body>${noteToHtml(note, idx)}</body></html>`;
  await writeRichClipboard(html, plain);
}

// ─── Export helpers ────────────────────────────────────────────────────────────

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

/** Plain text export — images noted as [Screenshot included] */
function exportAsText(notes: NoteEntry[], scriptId: string) {
  const lines: string[] = [
    `Validation Notepad — ${scriptId}`,
    `Exported: ${new Date().toLocaleString()}`,
    `Total notes: ${notes.length}`,
    "═".repeat(60),
    "",
  ];
  notes.forEach((n, i) => {
    lines.push(`NOTE #${i + 1} — ${TAG_META[n.tag].label}`);
    if (n.stepRef) lines.push(`Step ref : ${n.stepRef}`);
    lines.push(`Time     : ${n.timestamp}`);
    if (n.comment) lines.push(`Comment  : ${n.comment}`);
    if (n.imageDataUrl) lines.push(`\n[Screenshot included — see PDF or Markdown export for image]`);
    lines.push("", "─".repeat(60), "");
  });
  const blob = new Blob([lines.join("\n")], { type: "text/plain" });
  triggerDownload(blob, `validation-notes-${Date.now()}.txt`);
}

/** Markdown export — images embedded as base64 data URIs (self-contained file) */
function exportAsMarkdown(notes: NoteEntry[], scriptId: string) {
  const lines: string[] = [
    `# Validation Notepad — ${scriptId}`,
    ``,
    `**Exported:** ${new Date().toLocaleString()}  `,
    `**Total notes:** ${notes.length}`,
    ``,
    `---`,
    ``,
  ];
  notes.forEach((n, i) => {
    const tag = TAG_META[n.tag];
    lines.push(`## Note #${i + 1} — ${tag.label}`);
    lines.push(``);
    if (n.stepRef) lines.push(`**Step ref:** ${n.stepRef}  `);
    lines.push(`**Time:** ${n.timestamp}  `);
    lines.push(``);
    if (n.comment) {
      lines.push(`**Comment:** ${n.comment}`);
      lines.push(``);
    }
    if (n.imageDataUrl) {
      // Embed image as data URI — works in most Markdown renderers
      lines.push(`![Screenshot](${n.imageDataUrl})`);
      lines.push(``);
    }
    lines.push(`---`);
    lines.push(``);
  });
  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  triggerDownload(blob, `validation-notes-${Date.now()}.md`);
}

/** PDF export using jsPDF (loaded dynamically from CDN) */
async function exportAsPDF(notes: NoteEntry[], scriptId: string) {
  // Dynamically load jsPDF if not already present
  if (!(window as any).jspdf) {
    await new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js";
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Failed to load jsPDF"));
      document.head.appendChild(script);
    });
  }

  const { jsPDF } = (window as any).jspdf;
  const doc = new jsPDF({ unit: "mm", format: "a4" });

  const PAGE_W = 210;
  const PAGE_H = 297;
  const MARGIN = 15;
  const CONTENT_W = PAGE_W - MARGIN * 2;
  const LINE_H = 6; // mm per text line

  let y = MARGIN;

  function checkPageBreak(needed = 10) {
    if (y + needed > PAGE_H - MARGIN) {
      doc.addPage();
      y = MARGIN;
    }
  }

  // ── Cover / header ──
  doc.setFontSize(18);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(245, 166, 35); // brand orange
  doc.text("Validation Notepad", MARGIN, y);
  y += 9;

  doc.setFontSize(10);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(80, 80, 80);
  doc.text(`Script: ${scriptId}`, MARGIN, y);
  y += LINE_H;
  doc.text(`Exported: ${new Date().toLocaleString()}`, MARGIN, y);
  y += LINE_H;
  doc.text(`Total notes: ${notes.length}`, MARGIN, y);
  y += 4;

  // Divider line
  doc.setDrawColor(220, 220, 220);
  doc.setLineWidth(0.3);
  doc.line(MARGIN, y, PAGE_W - MARGIN, y);
  y += 6;

  for (let i = 0; i < notes.length; i++) {
    const n = notes[i];
    const tag = TAG_META[n.tag];

    checkPageBreak(20);

    // ── Note heading ──
    doc.setFontSize(12);
    doc.setFont("helvetica", "bold");
    doc.setTextColor(40, 40, 40);
    doc.text(`Note #${i + 1}`, MARGIN, y);

    // Tag badge (filled rect + white label)
    const badgeX = MARGIN + 22;
    const [r, g, b] = hexToRgb(tag.color);
    doc.setFillColor(r, g, b);
    doc.roundedRect(badgeX, y - 4, tag.label.length * 2.1 + 4, 5.5, 1, 1, "F");
    doc.setFontSize(8);
    doc.setFont("helvetica", "bold");
    doc.setTextColor(255, 255, 255);
    doc.text(tag.label, badgeX + 2, y - 0.3);
    y += LINE_H + 1;

    // ── Meta lines ──
    doc.setFontSize(9);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(100, 100, 100);

    if (n.stepRef) {
      doc.text(`Step ref: ${n.stepRef}`, MARGIN, y);
      y += LINE_H;
    }
    doc.text(`Time: ${n.timestamp}`, MARGIN, y);
    y += LINE_H;

    // ── Comment ──
    if (n.comment) {
      checkPageBreak(10);
      doc.setFontSize(9);
      doc.setFont("helvetica", "bold");
      doc.setTextColor(100, 100, 100);
      doc.text("Comment:", MARGIN, y);
      y += LINE_H;
      doc.setFontSize(10);
      doc.setFont("helvetica", "normal");
      doc.setTextColor(40, 40, 40);
      const wrappedLines = doc.splitTextToSize(n.comment, CONTENT_W);
      wrappedLines.forEach((line: string) => {
        checkPageBreak(LINE_H);
        doc.text(line, MARGIN, y);
        y += LINE_H;
      });
    }

    // ── Screenshot image ──
    if (n.imageDataUrl) {
      try {
        const { w: imgW, h: imgH } = await getImageDimensions(n.imageDataUrl);
        const aspectRatio = imgW / imgH;
        // Max width = content width; max height = 100mm
        let drawW = Math.min(CONTENT_W, 180);
        let drawH = drawW / aspectRatio;
        if (drawH > 100) { drawH = 100; drawW = drawH * aspectRatio; }

        checkPageBreak(drawH + 4);
        y += 2;
        doc.addImage(n.imageDataUrl, "JPEG", MARGIN, y, drawW, drawH);
        y += drawH + 4;
      } catch (err) {
        console.warn("Could not embed image in PDF:", err);
        doc.setFontSize(9);
        doc.setTextColor(150, 150, 150);
        doc.text("[Screenshot could not be embedded]", MARGIN, y);
        y += LINE_H;
      }
    }

    // ── Separator ──
    checkPageBreak(8);
    doc.setDrawColor(230, 230, 230);
    doc.setLineWidth(0.2);
    doc.line(MARGIN, y, PAGE_W - MARGIN, y);
    y += 7;
  }

  doc.save(`validation-notes-${Date.now()}.pdf`);
}

function hexToRgb(hex: string): [number, number, number] {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? [parseInt(result[1], 16), parseInt(result[2], 16), parseInt(result[3], 16)]
    : [100, 100, 100];
}

function getImageDimensions(dataUrl: string): Promise<{ w: number; h: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ w: img.width, h: img.height });
    img.onerror = reject;
    img.src = dataUrl;
  });
}

// ─── Export Dropdown ──────────────────────────────────────────────────────────

function ExportDropdown({
  notes,
  scriptId,
}: {
  notes: NoteEntry[];
  scriptId: string;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const run = async (label: string, fn: () => Promise<void> | void) => {
    setBusy(label);
    setOpen(false);
    try { await fn(); } catch (e) {
      console.error("Export failed:", e);
      alert(`Export failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const items: { label: string; icon: string; fn: () => void }[] = [
    {
      label: "Download as PDF",
      icon: "📄",
      fn: () => run("pdf", () => exportAsPDF(notes, scriptId)),
    },
    {
      label: "Download as Markdown",
      icon: "📝",
      fn: () => run("md", () => exportAsMarkdown(notes, scriptId)),
    },
    {
      label: "Download as Text",
      icon: "🗒️",
      fn: () => run("txt", () => exportAsText(notes, scriptId)),
    },
  ];

  const btnStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 5,
    padding: "5px 10px",
    borderRadius: 6,
    border: "1px solid hsl(var(--border))",
    background: open ? "hsl(var(--secondary))" : "transparent",
    cursor: "pointer",
    fontSize: 11,
    color: "hsl(var(--foreground))",
  };

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        style={btnStyle}
        onClick={() => setOpen(v => !v)}
        disabled={notes.length === 0}
        title={notes.length === 0 ? "No notes to export" : "Export notes"}
      >
        <Download size={12} />
        {busy ? "Exporting…" : "Export"}
        <ChevronDown size={10} style={{ marginLeft: 1, opacity: 0.6 }} />
      </button>

      {open && (
        <div style={{
          position: "absolute",
          top: "calc(100% + 4px)",
          right: 0,
          background: "hsl(var(--card))",
          border: "1px solid hsl(var(--border))",
          borderRadius: 8,
          boxShadow: "0 6px 20px rgba(0,0,0,0.15)",
          zIndex: 10000,
          minWidth: 190,
          overflow: "hidden",
        }}>
          {items.map(item => (
            <button
              key={item.label}
              onClick={item.fn}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                width: "100%",
                padding: "8px 12px",
                background: "none",
                border: "none",
                cursor: "pointer",
                fontSize: 12,
                color: "hsl(var(--foreground))",
                textAlign: "left",
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "hsl(var(--secondary))"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "none"; }}
            >
              <span style={{ fontSize: 14 }}>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
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
    try {
      await copyNoteToClipboard(note, index);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch (e) {
      console.error("Copy failed:", e);
      alert("Clipboard access denied. Check browser permissions.");
    }
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
        {note.imageDataUrl && <ImageIcon size={11} style={{ color: "hsl(var(--muted-foreground))", flexShrink: 0 }} />}
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

  // ── Resize state ──────────────────────────────────────────────────────────
  const MIN_W = 320;
  const MAX_W_LIMIT = Math.min(900, typeof window !== "undefined" ? window.innerWidth - 48 : 900);
  const MIN_H = 300;
  const MAX_H_LIMIT = typeof window !== "undefined" ? window.innerHeight - 120 : 800;

  const [panelW, setPanelW] = useState(430);
  const [panelH, setPanelH] = useState<number | null>(null); // null = governed by css maxHeight

  const resizeRef = useRef<{
    edge: "left" | "top" | "corner";
    startX: number; startY: number;
    startW: number; startH: number;
  } | null>(null);

  const startResize = (edge: "left" | "top" | "corner") =>
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const panel = document.getElementById("vn-panel")!;
      resizeRef.current = {
        edge,
        startX: e.clientX,
        startY: e.clientY,
        startW: panel.offsetWidth,
        startH: panel.offsetHeight,
      };
      const onMove = (ev: MouseEvent) => {
        const r = resizeRef.current;
        if (!r) return;
        const dx = r.startX - ev.clientX; // left handle: drag left = wider
        const dy = r.startY - ev.clientY; // top handle:  drag up   = taller
        if (r.edge === "left" || r.edge === "corner") {
          setPanelW(Math.min(MAX_W_LIMIT, Math.max(MIN_W, r.startW + dx)));
        }
        if (r.edge === "top" || r.edge === "corner") {
          setPanelH(Math.min(MAX_H_LIMIT, Math.max(MIN_H, r.startH + dy)));
        }
      };
      const onUp = () => {
        resizeRef.current = null;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    };

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
    document.addEventListener("paste", onPaste, true);
    return () => document.removeEventListener("paste", onPaste, true);
  }, []);

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
      alert("Clipboard access denied. Use Ctrl+V instead.");
      return;
    }
    setNotes(p => [...p, { id: uid(), imageDataUrl: null, comment: "", tag: "text_incorrect", stepRef: "", timestamp: new Date().toLocaleTimeString() }]);
    setOpen(true);
  };

  const copyAll = useCallback(async () => {
    if (!notes.length) return;

    const plain = notes.map((n, i) => noteToText(n, i)).join("\n\n---\n\n");

    const bodyHtml = notes.map((n, i) => noteToHtml(n, i)).join("\n");
    const html = `<!DOCTYPE html><html><body>
      <div style="font-family:system-ui,sans-serif;max-width:680px;padding:16px">
        <h2 style="font-size:15px;font-weight:700;color:#F5A623;margin:0 0 12px">Validation Notepad</h2>
        ${bodyHtml}
      </div>
    </body></html>`;

    try {
      await writeRichClipboard(html, plain);
      setAllCopied(true);
      setTimeout(() => setAllCopied(false), 2000);
    } catch (e) {
      console.error("Copy all failed:", e);
      alert("Clipboard access denied. Check browser permissions.");
    }
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
        #vn-panel > div[style*="ew-resize"]:hover,
        #vn-panel > div[style*="ns-resize"]:hover,
        #vn-panel > div[style*="nwse-resize"]:hover {
          background: rgba(245,166,35,0.25);
        }
      `}</style>

      {open && (
        <div id="vn-panel" style={{
          position: "fixed", bottom: 82, right: 24,
          width: panelW,
          height: panelH ?? undefined,
          maxHeight: panelH ? undefined : "76vh",
          zIndex: 9998,
          background: "hsl(var(--card))",
          border: "1px solid hsl(var(--border))",
          borderRadius: 14,
          boxShadow: "0 10px 40px rgba(0,0,0,0.2), 0 2px 8px rgba(0,0,0,0.1)",
          display: "flex", flexDirection: "column", overflow: "hidden",
          transformOrigin: "bottom right",
          animation: "notepad-pop 0.2s cubic-bezier(0.16,1,0.3,1)",
          userSelect: resizeRef.current ? "none" : undefined,
        }}>
          {/* ── Left resize handle ── */}
          <div onMouseDown={startResize("left")} style={{
            position: "absolute", left: 0, top: 12, bottom: 12, width: 6,
            cursor: "ew-resize", zIndex: 10,
            borderRadius: "4px 0 0 4px",
          }} />
          {/* ── Top resize handle ── */}
          <div onMouseDown={startResize("top")} style={{
            position: "absolute", top: 0, left: 12, right: 12, height: 6,
            cursor: "ns-resize", zIndex: 10,
            borderRadius: "4px 4px 0 0",
          }} />
          {/* ── Top-left corner handle ── */}
          <div onMouseDown={startResize("corner")} style={{
            position: "absolute", top: 0, left: 0, width: 14, height: 14,
            cursor: "nwse-resize", zIndex: 11,
            borderRadius: "4px 0 4px 0",
          }} />
          {/* ── Header ── */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "11px 14px", background: "hsl(var(--secondary))", borderBottom: "1px solid hsl(var(--border))", flexShrink: 0 }}>
            <FileText size={15} style={{ color: "#F5A623" }} />
            <span style={{ fontWeight: 700, fontSize: 13, color: "hsl(var(--foreground))", flex: 1 }}>Validation Notepad</span>
            {notes.length > 0 && (
              <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 20, background: "rgba(239,68,68,0.1)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.2)" }}>
                {notes.length}
              </span>
            )}
            {/* ── Export dropdown sits in the header ── */}
            <ExportDropdown notes={notes} scriptId={scriptId} />
            <button onClick={() => setOpen(false)} style={{ padding: 4, background: "none", border: "none", cursor: "pointer", color: "hsl(var(--muted-foreground))", display: "flex" }}>
              <Minimize2 size={14} />
            </button>
          </div>

          {/* ── Toolbar ── */}
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
                {allCopied ? "Copied!" : "Copy all as image"}
              </button>
            )}
          </div>

          {/* ── Note list ── */}
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