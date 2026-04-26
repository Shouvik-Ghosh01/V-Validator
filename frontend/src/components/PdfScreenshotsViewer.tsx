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

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
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
  ptsText: string | null;
  procedure: string | null;
  expectedResults: string | null;
  actualResults: string | null;
  hasDiff: boolean;
}

// ─── Backend step data types ─────────────────────────────────────────────────

interface ExecutedStep {
  step_number: number;
  procedure: string;
  expected_results: string;
  actual_results: string;
  pass_fail: string;
}

interface PtsStep {
  step_number: number;
  procedure: string;
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

const PTS_RE  = /PTS\s+Step\s+#?(\d+)\s+Screenshot(?:\s+#?(\d+))?/i;
const EXEC_RE = /(?:^|\s)Step\s+#?(\d+)\s+Screenshot(?:\s+#?(\d+))?/i;
const TIME_RE = /Screenshot\s+Time:\s*([^\n\r]+)/i;

function detectScreenshot(
  text: string
): { type: "pts" | "execution"; stepNum: number; screenshotNum: number } | null {
  const pts = PTS_RE.exec(text);
  if (pts) return { type: "pts", stepNum: parseInt(pts[1]), screenshotNum: pts[2] ? parseInt(pts[2]) : 1 };
  if (/PTS\s+Step/i.test(text)) return null;

  const exec = EXEC_RE.exec(text);
  if (exec) return { type: "execution", stepNum: parseInt(exec[1]), screenshotNum: exec[2] ? parseInt(exec[2]) : 1 };
  return null;
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
      const ptsText: string | null        = null;
      const procedure: string | null      = null;
      const expectedResults: string | null = null;
      const actualResults: string | null  = null;

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
  btnRef: React.RefObject<HTMLButtonElement>;
  executedStep?: ExecutedStep;
  ptsStep?: PtsStep;
  onClose: () => void;
}

function StepDetailPopup({ entry, btnRef, executedStep, ptsStep, onClose }: PopupProps) {
  const popupRef = useRef<HTMLDivElement>(null);
  const isPts    = entry.type === "pts";

  const accent = isPts
    ? { text: "#F5A623", bg: "rgba(245,166,35,0.12)", border: "rgba(245,166,35,0.35)" }
    : { text: "#22c55e", bg: "rgba(34,197,94,0.12)",  border: "rgba(34,197,94,0.35)"  };

  const POPUP_W     = 340;
  const POPUP_MAX_H = 480;
  const GAP         = 8;
  const EDGE_PAD    = 8;

  // Start off-screen to avoid flash at (0,0) before position is computed
  const [pos, setPos] = useState({ top: -9999, left: -9999 });

  // Compute after mount — btnRef.current is guaranteed to be populated by then.
  // Also recompute on scroll/resize so the popup tracks correctly when the page moves.
  useLayoutEffect(() => {
    function calcPos() {
      const btn = btnRef.current;
      if (!btn) return;
      const r          = btn.getBoundingClientRect();
      const spaceBelow = window.innerHeight - r.bottom;
      const spaceAbove = r.top;

      let left = r.right - POPUP_W;
      left = Math.max(EDGE_PAD, Math.min(left, window.innerWidth - POPUP_W - EDGE_PAD));

      let top: number;
      if (spaceBelow >= POPUP_MAX_H || spaceBelow >= spaceAbove) {
        top = r.bottom + GAP;
      } else {
        top = r.top - POPUP_MAX_H - GAP;
        if (top < EDGE_PAD) top = EDGE_PAD;
      }
      setPos({ top, left });
    }

    calcPos();
    window.addEventListener("scroll", calcPos, { passive: true, capture: true });
    window.addEventListener("resize", calcPos, { passive: true });
    return () => {
      window.removeEventListener("scroll", calcPos, true);
      window.removeEventListener("resize", calcPos);
    };
  }, [btnRef]);

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
  }, [onClose, btnRef]);

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

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
      }}>
        {value ?? "Not available"}
      </div>
    </div>
  );

  // Don't render until position has been calculated (avoids flash at 0,0)
  if (pos.top === -9999) return null;

  const popupContent = (
    <div
      ref={popupRef}
      style={{
        position: "fixed",
        top: pos.top,
        left: pos.left,
        width: POPUP_W,
        zIndex: 99999,
        background: "hsl(var(--card))",
        border: `1px solid ${accent.border}`,
        borderRadius: 12,
        boxShadow: "0 8px 40px rgba(0,0,0,0.35), 0 2px 12px rgba(0,0,0,0.2)",
        display: "flex",
        flexDirection: "column",
        maxHeight: POPUP_MAX_H,
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
        flex: 1,
        minHeight: 0,
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

        {/* PTS — sourced from backend ptsStep */}
        {isPts && (
          <Field
            label="Setup Instructions"
            value={ptsStep?.procedure ?? null}
            mono
          />
        )}

        {/* Execution — sourced from backend executedStep */}
        {!isPts && (
          <>
            <Field label="Procedure"        value={executedStep?.procedure       ?? null} />
            <Field label="Expected Results" value={executedStep?.expected_results ?? null} />
            <Field label="Actual Results"   value={executedStep?.actual_results   ?? null} />

            {/* Pass / Fail status badge */}
            {executedStep?.pass_fail && (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{
                  fontSize: 10,
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  color: "hsl(var(--muted-foreground))",
                }}>
                  Result
                </span>
                <span style={{
                  fontSize: 12,
                  fontWeight: 700,
                  padding: "3px 12px",
                  borderRadius: 20,
                  background: executedStep.pass_fail.toUpperCase() === "PASS"
                    ? "rgba(34,197,94,0.12)"
                    : executedStep.pass_fail.toUpperCase() === "FAIL"
                      ? "rgba(239,68,68,0.12)"
                      : "rgba(148,163,184,0.12)",
                  color: executedStep.pass_fail.toUpperCase() === "PASS"
                    ? "#22c55e"
                    : executedStep.pass_fail.toUpperCase() === "FAIL"
                      ? "#ef4444"
                      : "hsl(var(--muted-foreground))",
                  border: `1px solid ${
                    executedStep.pass_fail.toUpperCase() === "PASS"
                      ? "rgba(34,197,94,0.3)"
                      : executedStep.pass_fail.toUpperCase() === "FAIL"
                        ? "rgba(239,68,68,0.3)"
                        : "rgba(148,163,184,0.2)"
                  }`,
                }}>
                  {executedStep.pass_fail}
                </span>
              </div>
            )}
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

  // Portal to document.body — escapes ALL scroll containers, stacking contexts,
  // overflow:hidden parents, and tab panel clipping. This is the only reliable
  // way to position a fixed popup relative to a button deep inside a scroll tree.
  return createPortal(popupContent, document.body);
}

// ─── Screenshot card ──────────────────────────────────────────────────────────

function ScreenshotCard({
  entry,
  executedStep,
  ptsStep,
}: {
  entry: ScreenshotEntry;
  executedStep?: ExecutedStep;
  ptsStep?: PtsStep;
}) {
  const [expanded,  setExpanded]  = useState(true);
  const [popupOpen, setPopupOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);

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
    <div style={{
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
          executedStep={executedStep}
          ptsStep={ptsStep}
          onClose={() => setPopupOpen(false)}
        />
      )}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface Props {
  clientPdf: File | null;
  outputPdf: File | null;
  result: ComparisonResult | null;
  /** Keyed by step_number string — from backend executed_steps */
  executedSteps?: Record<string, ExecutedStep>;
  /** Keyed by step_number string — from backend pts_steps */
  ptsSteps?: Record<string, PtsStep>;
}

export default function PdfScreenshotsViewer({ clientPdf, outputPdf, result, executedSteps = {}, ptsSteps = {} }: Props) {
  const [entries,  setEntries]  = useState<ScreenshotEntry[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [progress, setProgress] = useState({ n: 0, total: 0 });
  const [filter,   setFilter]   = useState<"all" | "pts" | "execution">("all");

  useEffect(() => {
    if (!outputPdf) return;   // guard: nothing to scan without the report PDF
    let cancelled = false;
    setEntries([]);
    setLoading(true);

    extractScreenshots(outputPdf!, result, (n, total) => {
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
        position: "sticky",
        top: 0,
        zIndex: 10,
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
              executedStep={entry.type === "execution" ? executedSteps[String(entry.stepNum)] : undefined}
              ptsStep={entry.type === "pts" ? ptsSteps[String(entry.stepNum)] : undefined}
            />
          ))
        )}
      </div>
    </div>
  );
}