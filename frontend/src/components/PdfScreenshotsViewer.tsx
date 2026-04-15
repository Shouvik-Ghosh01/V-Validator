/**
 * PdfScreenshotsViewer.tsx
 *
 * Reads ALL data (screenshot label, procedure, expected results, PTS text)
 * directly from the executed/report PDF — no template parsing required.
 *
 * UI: Each card header has an ⓘ button at the top-right corner.
 * Clicking it opens a floating popup box anchored below that button,
 * showing step details for that specific card. Clicking outside or
 * pressing Escape closes it.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { ComparisonResult } from "@/types/comparison";
import * as pdfjsLib from "pdfjs-dist";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import { ChevronDown, ChevronRight, Clock, Info, Layers, X } from "lucide-react";

pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js`;

// ─── Types ────────────────────────────────────────────────────────────────────

interface ScreenshotEntry {
  type: "pts" | "execution";
  stepNum: number;
  screenshotNum: number;
  pageIndex: number;
  imageUrl: string;
  screenshotTime: string | null;
  /** PTS: full multi-line setup text with preserved line breaks */
  ptsText: string | null;
  /** Execution only */
  procedure: string | null;
  expectedResults: string | null;
  actualResults: string | null;
  hasDiff: boolean;
}

// ─── Text extraction helpers ──────────────────────────────────────────────────

interface TItem { x: number; y: number; text: string; }

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

async function getPageItems(page: PDFPageProxy): Promise<TItem[]> {
  const content = await page.getTextContent();
  return (content.items as any[])
    .filter(it => it.str?.trim())
    .map(it => ({ x: it.transform[4], y: it.transform[5], text: it.str }));
}

function flatText(items: TItem[]): string {
  return items.map(i => i.text).join(" ");
}

function rowsToLines(rows: TItem[][]): string {
  return rows
    .map(row => row.map(i => i.text).join(" ").trim())
    .filter(Boolean)
    .join("\n");
}

// ─── Screenshot detection ─────────────────────────────────────────────────────

const PTS_RE  = /PTS\s+Step\s+#?(\d+)\s+Screenshot\s+#?(\d+)/i;
const EXEC_RE = /Step\s+#?(\d+)\s+Screenshot(?:\s+#?(\d+))?/i;
const TIME_RE = /Screenshot\s+Time:\s*([^\n\r]+)/i;

function detectScreenshot(
  text: string
): { type: "pts" | "execution"; stepNum: number; screenshotNum: number } | null {
  const pts = PTS_RE.exec(text);
  if (pts) return { type: "pts", stepNum: parseInt(pts[1]), screenshotNum: parseInt(pts[2]) };
  const exec = EXEC_RE.exec(text);
  if (exec) return { type: "execution", stepNum: parseInt(exec[1]), screenshotNum: exec[2] ? parseInt(exec[2]) : 1 };
  return null;
}

// ─── Content extractors ───────────────────────────────────────────────────────

function extractPtsText(rows: TItem[][], _stepNum: number): string {
  const dataRows: TItem[][] = [];
  let inData = false;
  for (const row of rows) {
    const t = row.map(i => i.text).join(" ");
    if (PTS_RE.test(t) || /screenshot\s+time/i.test(t)) { inData = true; continue; }
    if (/veeva systems confidential|page \d+ of \d+|script id/i.test(t)) break;
    if (inData && t.trim()) dataRows.push(row);
  }
  return rowsToLines(dataRows);
}

function extractExecutionStepData(rows: TItem[][]): {
  procedure: string;
  expectedResults: string;
  actualResults: string;
} {
  let procMinX = -1, procMaxX = -1;
  let expMinX  = -1, expMaxX  = -1;
  let actMinX  = -1;
  let headerRowIdx = -1;

  for (let i = 0; i < rows.length; i++) {
    const t = rows[i].map(r => r.text).join(" ").toLowerCase();
    if (t.includes("procedure") && t.includes("expected")) {
      headerRowIdx = i;
      const sorted = [...rows[i]].sort((a, b) => a.x - b.x);
      for (const item of sorted) {
        const lc = item.text.toLowerCase().trim();
        if (lc.includes("procedure") && procMinX === -1) procMinX = item.x;
        if (lc.includes("expected")  && expMinX  === -1) expMinX  = item.x;
        if (lc.includes("actual")    && actMinX  === -1) actMinX  = item.x;
      }
      procMaxX = expMinX > -1 ? expMinX - 2 : 9999;
      expMaxX  = actMinX > -1 ? actMinX - 2 : 9999;
      break;
    }
  }

  if (headerRowIdx === -1 || procMinX === -1) {
    return { procedure: "", expectedResults: "", actualResults: "" };
  }

  const proc: string[] = [];
  const exp:  string[] = [];
  const act:  string[] = [];

  for (let i = headerRowIdx + 1; i < rows.length; i++) {
    const rowText = rows[i].map(r => r.text).join(" ");
    if (/veeva systems confidential|page \d+ of \d+|script id/i.test(rowText)) break;
    for (const item of rows[i]) {
      const t = item.text.trim();
      if (!t) continue;
      if (/^(pass|fail|n\/a|yes|no|pass \/ fail|actual results?)$/i.test(t)) continue;
      if (item.x >= procMinX && item.x < procMaxX)          proc.push(t);
      else if (item.x >= expMinX && item.x < expMaxX)       exp.push(t);
      else if (actMinX > -1 && item.x >= actMinX)           act.push(t);
    }
  }

  return {
    procedure:       proc.join(" ").replace(/\s+/g, " ").trim(),
    expectedResults: exp.join(" ").replace(/\s+/g, " ").trim(),
    actualResults:   act.join(" ").replace(/\s+/g, " ").trim(),
  };
}

// ─── Page renderer ────────────────────────────────────────────────────────────

async function renderPageHQ(page: PDFPageProxy): Promise<string> {
  const SCALE = 3.0;
  const dpr = Math.max(window.devicePixelRatio || 1, 1);
  const vp = page.getViewport({ scale: SCALE * dpr });
  const canvas = document.createElement("canvas");
  canvas.width  = vp.width;
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
      const page  = await pdf.getPage(i + 1);
      const items = await getPageItems(page);
      const flat  = flatText(items);

      const detected = detectScreenshot(flat);
      if (!detected) continue;

      const key    = `${detected.type}-${detected.stepNum}`;
      ssCount[key] = (ssCount[key] || 0) + 1;
      const ssNum  = detected.screenshotNum || ssCount[key];

      const timeMatch    = TIME_RE.exec(flat);
      const screenshotTime = timeMatch ? timeMatch[1].trim() : null;
      const imageUrl     = await renderPageHQ(page);
      const rows         = groupRows(items);

      let ptsText: string | null = null;
      let procedure: string | null = null;
      let expectedResults: string | null = null;
      let actualResults: string | null = null;

      if (detected.type === "pts") {
        const raw = extractPtsText(rows, detected.stepNum);
        ptsText = raw || null;
      } else {
        const data = extractExecutionStepData(rows);
        procedure       = data.procedure       || null;
        expectedResults = data.expectedResults || null;
        actualResults   = data.actualResults   || null;
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
        actualResults,
        hasDiff,
      });
    }

    return entries;
  } finally {
    URL.revokeObjectURL(url);
  }
}

// ─── Step Detail Popup ────────────────────────────────────────────────────────

interface PopupProps {
  entry: ScreenshotEntry;
  /** ref to the button that triggered the popup */
  btnRef: React.RefObject<HTMLButtonElement>;
  /** ref to the card container (position:relative) */
  cardRef: React.RefObject<HTMLDivElement>;
  onClose: () => void;
}

function StepDetailPopup({ entry, btnRef, cardRef, onClose }: PopupProps) {
  const popupRef = useRef<HTMLDivElement>(null);
  const isPts    = entry.type === "pts";

  const accent = isPts
    ? { text: "#F5A623", bg: "rgba(245,166,35,0.12)", border: "rgba(245,166,35,0.35)" }
    : { text: "#22c55e", bg: "rgba(34,197,94,0.12)",  border: "rgba(34,197,94,0.35)"  };

  // Close on outside click (delayed so the opening click doesn't immediately close)
  useEffect(() => {
    function onMouseDown(e: MouseEvent) {
      if (
        popupRef.current && !popupRef.current.contains(e.target as Node) &&
        btnRef.current   && !btnRef.current.contains(e.target as Node)
      ) {
        onClose();
      }
    }
    const t = setTimeout(() => document.addEventListener("mousedown", onMouseDown), 60);
    return () => { clearTimeout(t); document.removeEventListener("mousedown", onMouseDown); };
  }, [onClose]);

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  // ── Position: right-align to button, open upward from button so it always
  //    sits right next to the trigger. Coordinates are relative to the card
  //    (position:relative) so no scroll offset needed.
  const POPUP_W = 340;
  const GAP     = 8;

  let top  = 0;
  let right = 12; // default: flush with card's right padding

  if (btnRef.current && cardRef.current) {
    const btnR  = btnRef.current.getBoundingClientRect();
    const cardR = cardRef.current.getBoundingClientRect();

    // Button's bottom edge relative to card top
    const btnBottomInCard = btnR.bottom - cardR.top;
    // Button's top edge relative to card top
    const btnTopInCard    = btnR.top    - cardR.top;

    // Popup height is dynamic; open downward first, flip upward if it would
    // overflow the viewport bottom.
    const spaceBelow = window.innerHeight - btnR.bottom;
    const spaceAbove = btnR.top;
    const POPUP_MAX_H = 500; // matches maxHeight in the body

    if (spaceBelow >= POPUP_MAX_H || spaceBelow >= spaceAbove) {
      // Open downward from the button's bottom
      top = btnBottomInCard + GAP;
    } else {
      // Open upward — position so popup bottom aligns with button top
      top = btnTopInCard - POPUP_MAX_H - GAP;
    }

    // Horizontal: right-align popup to button's right edge within the card
    const btnRightInCard = cardR.right - btnR.right;
    right = btnRightInCard;
  }

  // ── Reusable labelled field ──
  const Field = ({
    label,
    value,
    mono = false,
  }: {
    label: string;
    value: string | null;
    mono?: boolean;
  }) => (
    <div>
      <p style={{
        margin: "0 0 5px 0",
        fontSize: 10,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: "0.08em",
        color: "hsl(var(--muted-foreground))",
      }}>
        {label}
      </p>
      <div style={{
        fontSize: 12,
        lineHeight: 1.75,
        color: value ? "hsl(var(--foreground))" : "hsl(var(--muted-foreground))",
        fontStyle: value ? "normal" : "italic",
        background: "hsl(var(--muted))",
        border: "1px solid hsl(var(--border))",
        borderRadius: 6,
        padding: "9px 11px",
        whiteSpace: mono ? "pre-wrap" : "normal",
        wordBreak: "break-word",
        maxHeight: 150,
        overflowY: "auto",
      }}>
        {value ?? "Not available"}
      </div>
    </div>
  );

  return (
    <div
      ref={popupRef}
      style={{
        position: "absolute",
        top,
        right,
        width: POPUP_W,
        zIndex: 9999,
        background: "hsl(var(--card))",
        border: `1px solid ${accent.border}`,
        borderRadius: 12,
        boxShadow: "0 8px 32px rgba(0,0,0,0.28), 0 2px 8px rgba(0,0,0,0.16)",
        overflow: "hidden",
        animation: "ssPopupIn 0.15s ease-out",
      }}
    >
      <style>{`
        @keyframes ssPopupIn {
          from { opacity: 0; transform: translateY(-6px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0)   scale(1);    }
        }
      `}</style>

      {/* Header */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "11px 14px",
        background: accent.bg,
        borderBottom: `1px solid ${accent.border}`,
      }}>
        {/* Type badge */}
        <span style={{
          fontSize: 10,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          color: accent.text,
          background: "hsl(var(--card))",
          border: `1px solid ${accent.border}`,
          borderRadius: 20,
          padding: "2px 9px",
          flexShrink: 0,
        }}>
          {isPts ? "Pre-Test Setup" : "Execution Step"}
        </span>

        {/* Step number */}
        <span style={{
          fontSize: 14,
          fontWeight: 700,
          color: "hsl(var(--foreground))",
          flex: 1,
        }}>
          {isPts ? `PTS #${entry.stepNum}` : `Step #${entry.stepNum}`}
        </span>

        {/* Diff badge */}
        {entry.hasDiff && (
          <span style={{
            fontSize: 10,
            fontWeight: 700,
            padding: "2px 8px",
            borderRadius: 20,
            background: "rgba(239,68,68,0.12)",
            color: "#ef4444",
            border: "1px solid rgba(239,68,68,0.3)",
            flexShrink: 0,
          }}>
            DIFF
          </span>
        )}


      </div>

      {/* Body */}
      <div style={{
        display: "flex",
        flexDirection: "column",
        gap: 12,
        padding: 14,
        maxHeight: 460,
        overflowY: "auto",
      }}>
        {/* Screenshot time */}
        {entry.screenshotTime && (
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: 5,
            fontSize: 11,
            color: "hsl(var(--muted-foreground))",
          }}>
            <Clock size={11} />
            {entry.screenshotTime}
          </div>
        )}

        {/* PTS */}
        {isPts && (
          <Field label="Setup Instructions" value={entry.ptsText} mono />
        )}

        {/* Execution */}
        {!isPts && (
          <>
            <Field label="Procedure"        value={entry.procedure}       />
            <Field label="Expected Results" value={entry.expectedResults} />
            <Field label="Actual Results"   value={entry.actualResults}   />
          </>
        )}

        {/* Diff warning */}
        {entry.hasDiff && (
          <div style={{
            fontSize: 11,
            padding: "8px 11px",
            borderRadius: 6,
            background: "rgba(239,68,68,0.07)",
            border: "1px solid rgba(239,68,68,0.2)",
            color: "#ef4444",
            lineHeight: 1.5,
          }}>
            ⚠ A difference was detected for this step in the analysis.
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Screenshot card ──────────────────────────────────────────────────────────

function ScreenshotCard({ entry }: { entry: ScreenshotEntry }) {
  const [expanded,  setExpanded]  = useState(true);
  const [popupOpen, setPopupOpen] = useState(false);
  const btnRef  = useRef<HTMLButtonElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  const isPts = entry.type === "pts";
  const accentText   = isPts ? "#F5A623" : "#22c55e";
  const accentBorder = isPts ? "rgba(245,166,35,0.3)" : "rgba(34,197,94,0.3)";
  const accentBg     = isPts ? "rgba(245,166,35,0.04)" : "hsl(var(--secondary))";

  const stepLabel = isPts
    ? `PTS Step #${entry.stepNum} — Screenshot #${entry.screenshotNum}`
    : `Step #${entry.stepNum} — Screenshot #${entry.screenshotNum}`;

  const handleInfoClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setPopupOpen(v => !v);
  }, []);

  return (
    // overflow: visible so the absolute-positioned popup can escape the card
    <div ref={cardRef} style={{
      position: "relative",
      border: "1px solid hsl(var(--border))",
      borderRadius: 10,
      overflow: "visible",
      background: "hsl(var(--card))",
    }}>

      {/* ── Header ── */}
      <div
        onClick={() => setExpanded(v => !v)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "10px 14px",
          cursor: "pointer",
          background: accentBg,
          borderBottom: expanded ? "1px solid hsl(var(--border))" : "none",
          borderRadius: expanded ? "10px 10px 0 0" : 10,
        }}
      >
        {/* Type badge */}
        <span style={{
          fontSize: 12,
          fontWeight: 700,
          padding: "2px 8px",
          borderRadius: 20,
          background: isPts ? "rgba(245,166,35,0.1)" : "rgba(34,197,94,0.1)",
          color: accentText,
          border: `1px solid ${accentBorder}`,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          flexShrink: 0,
        }}>
          {isPts ? "PTS" : "Exec"}
        </span>

        {/* Step label */}
        <span style={{
          fontSize: 13,
          fontWeight: 600,
          color: "hsl(var(--foreground))",
          flex: 1,
        }}>
          {stepLabel}
        </span>

        {/* Screenshot time */}
        {entry.screenshotTime && (
          <span style={{
            display: "flex",
            alignItems: "center",
            gap: 4,
            fontSize: 11,
            color: "hsl(var(--muted-foreground))",
            flexShrink: 0,
          }}>
            <Clock size={11} /> {entry.screenshotTime}
          </span>
        )}

        {/* Right controls */}
        <div style={{
          display: "flex",
          gap: 6,
          alignItems: "center",
          marginLeft: "auto",
          flexShrink: 0,
        }}>
          {/* Diff badge */}
          {entry.hasDiff && (
            <span style={{
              fontSize: 12,
              fontWeight: 700,
              padding: "2px 8px",
              borderRadius: 20,
              background: "rgba(239,68,68,0.1)",
              color: "#ef4444",
              border: "1px solid rgba(239,68,68,0.25)",
            }}>
              DIFF
            </span>
          )}

          {/* Expand / collapse chevron */}
          {expanded
            ? <ChevronDown  size={20} style={{ color: "hsl(var(--muted-foreground))" }} />
            : <ChevronRight size={20} style={{ color: "hsl(var(--muted-foreground))" }} />}
        </div>
      </div>

      {/* ── Screenshot image + overlay ⓘ button ── */}
      {expanded && (
        <div style={{
          position: "relative",   /* anchor for the overlay button */
          padding: "24px 26px",
          background: "#0d0d0d",
          borderRadius: "0 0 10px 10px",
        }}>
          <img
            src={entry.imageUrl}
            alt={stepLabel}
            style={{ width: "100%", display: "block", borderRadius: 4 }}
          />

          {/* Overlay button — shows Details when closed, X when open */}
          <button
            ref={btnRef}
            onClick={handleInfoClick}
            title={popupOpen ? "Close details" : "View step details"}
            style={{
              position: "absolute",
              top: 12,
              right: 12,
              display: "flex",
              alignItems: "center",
              gap: 5,
              padding: "6px 10px",
              borderRadius: 8,
              border: `1px solid ${popupOpen ? accentBorder : "rgba(255,255,255,0.25)"}`,
              background: popupOpen
                ? (isPts ? "rgba(245,166,35,0.9)" : "rgba(34,197,94,0.9)")
                : "rgba(0,0,0,0.55)",
              color: popupOpen ? "#000" : "#fff",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
              backdropFilter: "blur(6px)",
              WebkitBackdropFilter: "blur(6px)",
              boxShadow: "0 2px 8px rgba(0,0,0,0.35)",
              transition: "all 0.15s",
              zIndex: 10,
            }}
          >
            {popupOpen ? <X size={13} /> : <><Info size={13} />Details</>}
          </button>
        </div>
      )}

      {/* ── Floating popup ── */}
      {popupOpen && (
        <StepDetailPopup
          entry={entry}
          btnRef={btnRef}
          cardRef={cardRef}
          onClose={() => setPopupOpen(false)}
        />
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
  const [entries,  setEntries]  = useState<ScreenshotEntry[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [progress, setProgress] = useState({ n: 0, total: 0 });
  const [filter,   setFilter]   = useState<"all" | "pts" | "execution">("all");

  useEffect(() => {
    let cancelled = false;
    setEntries([]);
    setLoading(true);

    extractScreenshots(outputPdf, result, (n, total) => {
      if (!cancelled) setProgress({ n, total });
    })
      .then(es  => { if (!cancelled) { setEntries(es); setLoading(false); } })
      .catch(err => { console.error("Screenshot scan failed:", err); if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [outputPdf, result]);

  const pts      = entries.filter(e => e.type === "pts");
  const exec     = entries.filter(e => e.type === "execution");
  const filtered = filter === "all" ? entries : filter === "pts" ? pts : exec;

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>

      {/* ── Toolbar ── */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        flexWrap: "wrap",
        rowGap: 6,
        padding: "10px 16px",
        borderBottom: "1px solid hsl(var(--border))",
        background: "hsl(var(--card))",
      }}>
        <Layers size={14} style={{ color: "#F5A623" }} />
        <span style={{ fontWeight: 600, fontSize: 13, color: "hsl(var(--foreground))" }}>
          Screenshots
        </span>

        {!loading && (
          <div style={{ display: "flex", gap: 6, marginLeft: 8 }}>
            {(["all", "pts", "execution"] as const).map(f => {
              const count  = f === "all" ? entries.length : f === "pts" ? pts.length : exec.length;
              const active = filter === f;
              return (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  style={{
                    fontSize: 11,
                    fontWeight: 500,
                    padding: "3px 10px",
                    borderRadius: 20,
                    cursor: "pointer",
                    border: `1px solid ${active ? "#F5A623" : "hsl(var(--border))"}`,
                    background: active ? "rgba(245,166,35,0.1)" : "transparent",
                    color: active ? "#F5A623" : "hsl(var(--muted-foreground))",
                  }}
                >
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

      {/* ── Progress bar ── */}
      {loading && progress.total > 0 && (
        <div style={{ height: 3, background: "hsl(var(--muted))" }}>
          <div style={{
            height: "100%",
            background: "#F5A623",
            borderRadius: 99,
            width: `${Math.max(5, (progress.n / progress.total) * 100)}%`,
            transition: "width 0.25s",
          }} />
        </div>
      )}

      {/* ── Content ── */}
      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        {loading ? (
          <div style={{
            textAlign: "center",
            padding: "4rem",
            color: "hsl(var(--muted-foreground))",
            fontSize: 13,
          }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>🔍</div>
            Scanning report PDF for screenshot pages at maximum quality…
          </div>
        ) : filtered.length === 0 ? (
          <div style={{
            textAlign: "center",
            padding: "3rem",
            color: "hsl(var(--muted-foreground))",
            fontSize: 13,
            border: "1px dashed hsl(var(--border))",
            borderRadius: 8,
          }}>
            <div style={{ fontSize: 28, marginBottom: 8 }}>📄</div>
            No screenshots detected in this PDF.
            <div style={{ fontSize: 11, marginTop: 6 }}>
              Expected: "PTS Step #3 Screenshot #1" or "Step #1 Screenshot #1"
            </div>
          </div>
        ) : (
          filtered.map((entry, i) => (
            <ScreenshotCard
              key={`${entry.type}-${entry.stepNum}-${entry.screenshotNum}-${i}`}
              entry={entry}
            />
          ))
        )}
      </div>
    </div>
  );
}