/**
 * PdfScreenshotsViewer.tsx
 *
 * Reads ALL data (screenshot label, procedure, expected results, PTS text)
 * directly from the executed/report PDF — no template parsing required.
 *
 * PTS steps: line breaks preserved exactly as they appear in the PDF.
 * Execution steps: procedure + expected results extracted from the same page text.
 */

import { useEffect, useState } from "react";
import type { ComparisonResult } from "@/types/comparison";
import * as pdfjsLib from "pdfjs-dist";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import { ChevronDown, ChevronRight, Clock, Layers } from "lucide-react";

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.mjs",
  import.meta.url
).toString();

// ─── Types ────────────────────────────────────────────────────────────────────

interface ScreenshotEntry {
  type: "pts" | "execution";
  stepNum: number;
  screenshotNum: number;
  pageIndex: number;
  imageUrl: string;
  screenshotTime: string | null;
  /** For PTS: the full multi-line text with line breaks preserved */
  ptsText: string | null;
  /** For execution: procedure from the page text */
  procedure: string | null;
  /** For execution: expected results from the page text */
  expectedResults: string | null;
  hasDiff: boolean;
}

// ─── Text extraction helpers ──────────────────────────────────────────────────

interface TItem { x: number; y: number; text: string; }

/** Group text items into visual rows by Y proximity */
function groupRows(items: TItem[], tolerance = 4): TItem[][] {
  const sorted = [...items].sort((a, b) => b.y - a.y);
  const rows: TItem[][] = [];
  let cur: TItem[] = [];
  let lastY: number | null = null;
  for (const it of sorted) {
    if (lastY === null || Math.abs(it.y - lastY) <= tolerance) {
      cur.push(it);
    } else {
      if (cur.length) rows.push(cur.sort((a, b) => a.x - b.x));
      cur = [it];
    }
    lastY = it.y;
  }
  if (cur.length) rows.push(cur.sort((a, b) => a.x - b.x));
  return rows;
}

/** Extract text items from a PDF page with positions */
async function getPageItems(page: PDFPageProxy): Promise<TItem[]> {
  const content = await page.getTextContent();
  return (content.items as any[])
    .filter(it => it.str?.trim())
    .map(it => ({ x: it.transform[4], y: it.transform[5], text: it.str }));
}

/** Flat text from items (joins all text with spaces) */
function flatText(items: TItem[]): string {
  return items.map(i => i.text).join(" ");
}

/**
 * Build a line-by-line text representation preserving visual rows.
 * Used for PTS display to keep multi-line structure intact.
 */
function rowsToLines(rows: TItem[][]): string {
  return rows.map(row => row.map(i => i.text).join(" ").trim()).filter(Boolean).join("\n");
}

// ─── Screenshot detection ─────────────────────────────────────────────────────

const PTS_RE = /PTS\s+Step\s+#?(\d+)\s+Screenshot\s+#?(\d+)/i;
const EXEC_RE = /Step\s+#?(\d+)\s+Screenshot(?:\s+#?(\d+))?/i;
const TIME_RE = /Screenshot\s+Time:\s*([^\n\r]+)/i;

function detectScreenshot(text: string): { type: "pts" | "execution"; stepNum: number; screenshotNum: number } | null {
  const pts = PTS_RE.exec(text);
  if (pts) return { type: "pts", stepNum: parseInt(pts[1]), screenshotNum: parseInt(pts[2]) };
  const exec = EXEC_RE.exec(text);
  if (exec) return { type: "execution", stepNum: parseInt(exec[1]), screenshotNum: exec[2] ? parseInt(exec[2]) : 1 };
  return null;
}

// ─── Content extractors from page items ───────────────────────────────────────

/**
 * Extract the PTS step text from a page.
 * The PTS pages show the full numbered list; we capture everything
 * after the header row and before the footer, preserving line structure.
 */
function extractPtsText(rows: TItem[][], stepNum: number): string {
  // Find all rows that are part of the data area (below header, above footer)
  const dataRows: TItem[][] = [];
  let inData = false;

  for (const row of rows) {
    const t = row.map(i => i.text).join(" ");
    // Skip the header row (contains "PTS Step #N Screenshot")
    if (PTS_RE.test(t) || /screenshot\s+time/i.test(t)) { inData = true; continue; }
    // Stop at footer
    if (/veeva systems confidential|page \d+ of \d+|script id/i.test(t)) break;
    if (inData && t.trim()) dataRows.push(row);
  }

  if (!dataRows.length) return "";
  return rowsToLines(dataRows);
}

/**
 * Extract procedure and expected results from an execution screenshot page.
 * The executed PDF pages have a table with procedure | expected | actual columns.
 * We detect column boundaries from the header row (Step # / Procedure / Expected Results).
 */
function extractExecutionStepData(
  rows: TItem[][]
): { procedure: string; expectedResults: string } {

  // Find header row
  let procMinX = -1, procMaxX = -1, expMinX = -1, expMaxX = -1;
  let headerRowIdx = -1;

  for (let i = 0; i < rows.length; i++) {
    const t = rows[i].map(r => r.text).join(" ").toLowerCase();
    if (t.includes("procedure") && t.includes("expected")) {
      headerRowIdx = i;
      // Detect column X ranges
      for (const item of rows[i]) {
        const lc = item.text.toLowerCase().trim();
        if (lc.includes("procedure")) procMinX = item.x;
        if (lc.includes("expected")) expMinX = item.x;
        if (lc.includes("actual")) { expMaxX = item.x - 2; break; }
      }
      if (expMaxX === -1) expMaxX = 9999;
      procMaxX = expMinX - 2;
      break;
    }
  }

  if (headerRowIdx === -1 || procMinX === -1) {
    // Fallback: no header found, return empty
    return { procedure: "", expectedResults: "" };
  }

  const procLines: string[] = [];
  const expLines: string[] = [];

  // Collect data rows below header
  for (let i = headerRowIdx + 1; i < rows.length; i++) {
    const rowText = rows[i].map(r => r.text).join(" ");
    if (/veeva systems confidential|page \d+ of \d+|script id/i.test(rowText)) break;

    for (const item of rows[i]) {
      const t = item.text.trim();
      if (!t) continue;
      const skip = /^(pass|fail|n\/a|yes|no|pass \/ fail|actual results?)$/i.test(t);
      if (skip) continue;

      if (item.x >= procMinX && item.x < procMaxX) {
        procLines.push(t);
      } else if (item.x >= expMinX && item.x < expMaxX) {
        expLines.push(t);
      }
    }
  }

  return {
    procedure: procLines.join(" ").replace(/\s+/g, " ").trim(),
    expectedResults: expLines.join(" ").replace(/\s+/g, " ").trim(),
  };
}

// ─── Page renderer (3× + devicePixelRatio, PNG lossless) ─────────────────────

async function renderPageHQ(page: PDFPageProxy): Promise<string> {
  const SCALE = 3.0;
  const dpr = Math.max(window.devicePixelRatio || 1, 1);
  const vp = page.getViewport({ scale: SCALE * dpr });
  const canvas = document.createElement("canvas");
  canvas.width = vp.width;
  canvas.height = vp.height;
  const ctx = canvas.getContext("2d", { alpha: false })!;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  await page.render({ canvasContext: ctx, viewport: vp }).promise;
  return canvas.toDataURL("image/png");
}

// ─── Main extractor ───────────────────────────────────────────────────────────

async function extractScreenshots(
  file: File,
  result: ComparisonResult | null,
  onProgress: (n: number, total: number) => void
): Promise<ScreenshotEntry[]> {
  const url = URL.createObjectURL(file);
  try {
    const pdf: PDFDocumentProxy = await pdfjsLib.getDocument(url).promise;
    const entries: ScreenshotEntry[] = [];
    const ssCount: Record<string, number> = {};

    for (let i = 0; i < pdf.numPages; i++) {
      onProgress(i + 1, pdf.numPages);
      const page = await pdf.getPage(i + 1);
      const items = await getPageItems(page);
      const flat = flatText(items);

      const detected = detectScreenshot(flat);
      if (!detected) continue;

      const key = `${detected.type}-${detected.stepNum}`;
      ssCount[key] = (ssCount[key] || 0) + 1;
      const ssNum = detected.screenshotNum || ssCount[key];

      const timeMatch = TIME_RE.exec(flat);
      const screenshotTime = timeMatch ? timeMatch[1].trim() : null;

      // Render high-quality
      const imageUrl = await renderPageHQ(page);

      // Extract content from page
      const rows = groupRows(items);
      let ptsText: string | null = null;
      let procedure: string | null = null;
      let expectedResults: string | null = null;

      if (detected.type === "pts") {
        ptsText = extractPtsText(rows, detected.stepNum);
        if (!ptsText) ptsText = null;
      } else {
        const data = extractExecutionStepData(rows);
        procedure = data.procedure || null;
        expectedResults = data.expectedResults || null;
      }

      const hasDiff =
        detected.type === "execution"
          ? !!(result?.execution_differences?.[detected.stepNum.toString()]?.length)
          : !!(result?.setup_differences?.[detected.stepNum.toString()]?.length);

      entries.push({
        type: detected.type,
        stepNum: detected.stepNum,
        screenshotNum: ssNum,
        pageIndex: i,
        imageUrl,
        screenshotTime,
        ptsText,
        procedure,
        expectedResults,
        hasDiff,
      });
    }

    return entries;
  } finally {
    URL.revokeObjectURL(url);
  }
}

// ─── Screenshot card ──────────────────────────────────────────────────────────

function ScreenshotCard({ entry }: { entry: ScreenshotEntry }) {
  const [expanded, setExpanded] = useState(true);
  const isPts = entry.type === "pts";
  const accent = isPts
    ? { text: "#F5A623", bg: "rgba(245,166,35,0.1)", border: "rgba(245,166,35,0.3)" }
    : { text: "#22c55e", bg: "rgba(34,197,94,0.1)", border: "rgba(34,197,94,0.3)" };

  const stepLabel = isPts
    ? `PTS Step #${entry.stepNum} — Screenshot #${entry.screenshotNum}`
    : `Step #${entry.stepNum} — Screenshot #${entry.screenshotNum}`;

  return (
    <div style={{ border: "1px solid hsl(var(--border))", borderRadius: 10, overflow: "hidden", background: "hsl(var(--card))" }}>
      {/* Header */}
      <div
        onClick={() => setExpanded(v => !v)}
        style={{
          display: "flex", alignItems: "center", gap: 10, padding: "10px 14px",
          cursor: "pointer",
          background: isPts ? "rgba(245,166,35,0.04)" : "hsl(var(--secondary))",
          borderBottom: expanded ? "1px solid hsl(var(--border))" : "none",
        }}
      >
        <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 20, background: accent.bg, color: accent.text, border: `1px solid ${accent.border}`, textTransform: "uppercase", letterSpacing: "0.05em", flexShrink: 0 }}>
          {isPts ? "PTS" : "Exec"}
        </span>
        <span style={{ fontSize: 13, fontWeight: 600, color: "hsl(var(--foreground))" }}>{stepLabel}</span>
        {entry.screenshotTime && (
          <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "hsl(var(--muted-foreground))" }}>
            <Clock size={11} /> {entry.screenshotTime}
          </span>
        )}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          {entry.hasDiff && (
            <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 20, background: "rgba(239,68,68,0.1)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.25)" }}>
              DIFF
            </span>
          )}
          {expanded
            ? <ChevronDown size={14} style={{ color: "hsl(var(--muted-foreground))" }} />
            : <ChevronRight size={14} style={{ color: "hsl(var(--muted-foreground))" }} />}
        </div>
      </div>

      {/* Body */}
      {expanded && (
        <div style={{ display: "flex" }}>
          {/* Screenshot image */}
          <div style={{ flex: "0 0 65%", padding: "14px 16px", borderRight: "1px solid hsl(var(--border))", background: "#0d0d0d", display: "flex", alignItems: "flex-start" }}>
            <img src={entry.imageUrl} alt={stepLabel} style={{ width: "100%", display: "block", borderRadius: 4, imageRendering: "high-quality" }} />
          </div>

          {/* Step info panel */}
          <div style={{ flex: 1, padding: "16px 14px", display: "flex", flexDirection: "column", gap: 14, overflowY: "auto", maxHeight: 640 }}>
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: accent.text, marginBottom: 3 }}>
                {isPts ? "Pre-Test Setup" : "Execution Step"}
              </div>
              <div style={{ fontSize: 22, fontWeight: 700, color: "hsl(var(--foreground))" }}>
                Step #{entry.stepNum}
              </div>
            </div>

            {/* PTS: full text with preserved line breaks */}
            {isPts && (
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "hsl(var(--muted-foreground))", marginBottom: 6 }}>
                  Setup Instructions
                </div>
                <div style={{
                  fontSize: 12, lineHeight: 1.75,
                  color: "hsl(var(--foreground))",
                  background: "hsl(var(--muted))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: 6, padding: "10px 12px",
                  whiteSpace: "pre-wrap",   /* ← preserves line breaks */
                  wordBreak: "break-word",
                }}>
                  {entry.ptsText ?? (
                    <span style={{ color: "hsl(var(--muted-foreground))", fontStyle: "italic" }}>
                      Step {entry.stepNum} — no text extracted
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Execution: procedure */}
            {!isPts && (
              <>
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "hsl(var(--muted-foreground))", marginBottom: 6 }}>
                    Procedure
                  </div>
                  <div style={{ fontSize: 12, lineHeight: 1.7, color: "hsl(var(--foreground))", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))", borderRadius: 6, padding: "9px 11px" }}>
                    {entry.procedure ?? <span style={{ color: "hsl(var(--muted-foreground))", fontStyle: "italic" }}>Not extracted</span>}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "hsl(var(--muted-foreground))", marginBottom: 6 }}>
                    Expected Results
                  </div>
                  <div style={{ fontSize: 12, lineHeight: 1.7, color: "hsl(var(--foreground))", background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))", borderRadius: 6, padding: "9px 11px" }}>
                    {entry.expectedResults ?? <span style={{ color: "hsl(var(--muted-foreground))", fontStyle: "italic" }}>Not available</span>}
                  </div>
                </div>
              </>
            )}

            {entry.hasDiff && (
              <div style={{ fontSize: 11, padding: "9px 11px", borderRadius: 6, background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.2)", color: "#ef4444" }}>
                ⚠ A difference was detected for this step in the analysis.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface Props {
  clientPdf: File;
  outputPdf: File;
  result: ComparisonResult | null;
}

export default function PdfScreenshotsViewer({ clientPdf, outputPdf, result }: Props) {
  const [entries, setEntries] = useState<ScreenshotEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState({ n: 0, total: 0 });
  const [filter, setFilter] = useState<"all" | "pts" | "execution">("all");

  useEffect(() => {
    let cancelled = false;
    setEntries([]);
    setLoading(true);

    extractScreenshots(outputPdf, result, (n, total) => {
      if (!cancelled) setProgress({ n, total });
    }).then(es => {
      if (!cancelled) { setEntries(es); setLoading(false); }
    }).catch(e => {
      console.error("Screenshot scan failed:", e);
      if (!cancelled) setLoading(false);
    });

    return () => { cancelled = true; };
  }, [outputPdf, result]);

  const pts = entries.filter(e => e.type === "pts");
  const exec = entries.filter(e => e.type === "execution");
  const filtered = filter === "all" ? entries : filter === "pts" ? pts : exec;

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      {/* Toolbar */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", rowGap: 6, padding: "10px 16px", borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--card))" }}>
        <Layers size={14} style={{ color: "#F5A623" }} />
        <span style={{ fontWeight: 600, fontSize: 13, color: "hsl(var(--foreground))" }}>Screenshots</span>

        {!loading && (
          <div style={{ display: "flex", gap: 6, marginLeft: 8 }}>
            {(["all", "pts", "execution"] as const).map(f => {
              const count = f === "all" ? entries.length : f === "pts" ? pts.length : exec.length;
              const active = filter === f;
              return (
                <button key={f} onClick={() => setFilter(f)} style={{
                  fontSize: 11, fontWeight: 500, padding: "3px 10px", borderRadius: 20, cursor: "pointer",
                  border: `1px solid ${active ? "#F5A623" : "hsl(var(--border))"}`,
                  background: active ? "rgba(245,166,35,0.1)" : "transparent",
                  color: active ? "#F5A623" : "hsl(var(--muted-foreground))",
                }}>
                  {f === "all" ? "All" : f === "pts" ? "PTS" : "Execution"} ({count})
                </button>
              );
            })}
          </div>
        )}

        {loading && (
          <span style={{ fontSize: 12, color: "hsl(var(--muted-foreground))" }}>
            🔍 Scanning page {progress.n} of {progress.total}…
          </span>
        )}
      </div>

      {/* Progress bar */}
      {loading && progress.total > 0 && (
        <div style={{ height: 3, background: "hsl(var(--muted))" }}>
          <div style={{ height: "100%", background: "#F5A623", borderRadius: 99, width: `${Math.max(5, (progress.n / progress.total) * 100)}%`, transition: "width 0.25s" }} />
        </div>
      )}

      {/* Content */}
      <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: 14 }}>
        {loading ? (
          <div style={{ textAlign: "center", padding: "4rem", color: "hsl(var(--muted-foreground))", fontSize: 13 }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>🔍</div>
            Scanning report PDF for screenshot pages at maximum quality…
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ textAlign: "center", padding: "3rem", color: "hsl(var(--muted-foreground))", fontSize: 13, border: "1px dashed hsl(var(--border))", borderRadius: 8 }}>
            <div style={{ fontSize: 28, marginBottom: 8 }}>📄</div>
            No screenshots detected in this PDF.
            <div style={{ fontSize: 11, marginTop: 6 }}>Expected: "PTS Step #3 Screenshot #1" or "Step #1 Screenshot #1"</div>
          </div>
        ) : (
          filtered.map((entry, i) => (
            <ScreenshotCard key={`${entry.type}-${entry.stepNum}-${entry.screenshotNum}-${i}`} entry={entry} />
          ))
        )}
      </div>
    </div>
  );
}
