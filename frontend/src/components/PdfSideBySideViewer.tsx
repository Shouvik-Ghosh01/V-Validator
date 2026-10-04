/**
 * PdfSideBySideViewer.tsx
 *
 */

import React, { useEffect, useLayoutEffect, useRef, useState, useCallback, useMemo } from "react";
import type { ComparisonResult } from "@/types/comparison";
import * as pdfjsLib from "pdfjs-dist";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import {
  Maximize2, Minimize2, Link, Unlink,
  FileText, Layers, ChevronRight,
} from "lucide-react";

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.mjs",
  import.meta.url
).toString();

// Colours reused across views 
const COLOR_REMOVED = "rgba(239,68,68,0.45)";
const COLOR_ADDED = "rgba(34,197,94,0.42)";
const COLOR_REMOVED_SOLID = "#ef4444";
const COLOR_ADDED_SOLID = "#22c55e";


function normalize(w: string): string {
  return w.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
}

const STATUS_WORDS = new Set([
  "pass", "fail", "passed", "failed", "passfail", "na", "skip", "skipped", "blocked",
]);
const MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec";

function isIgnorable(raw: string): boolean {
  const t = raw.trim();
  if (!t) return true;
  if (/^\d{1,4}[-/.]\d{1,2}([-/.]\d{1,4})?$/.test(t)) return true;
  if (/^\d{1,2}:\d{2}(:\d{2})?\s?(am|pm)?$/i.test(t)) return true;
  if (new RegExp(`^\\d{0,2}[-\\s]?(${MONTHS})[a-z]*[-\\s]?\\d{0,4}$`, "i").test(t)) return true;
  if (STATUS_WORDS.has(normalize(t))) return true;
  return false;
}


type DiffOp = { type: "eq" | "del" | "ins"; a?: number; b?: number };

function myersDiff(a: string[], b: string[]): DiffOp[] {
  const N = a.length;
  const M = b.length;
  if (N === 0 && M === 0) return [];
  if (N === 0) return b.map((_, i) => ({ type: "ins", b: i } as DiffOp));
  if (M === 0) return a.map((_, i) => ({ type: "del", a: i } as DiffOp));

  const MAX = N + M;
  const v: Record<number, number> = { 1: 0 };
  const trace: Record<number, number>[] = [];
  let reached = -1;

  for (let d = 0; d <= MAX; d++) {
    trace.push({ ...v });
    for (let k = -d; k <= d; k += 2) {
      let x: number;
      if (k === -d || (k !== d && (v[k - 1] ?? -1) < (v[k + 1] ?? -1))) {
        x = v[k + 1] ?? 0;
      } else {
        x = (v[k - 1] ?? 0) + 1;
      }
      let y = x - k;
      while (x < N && y < M && a[x] === b[y]) { x++; y++; }
      v[k] = x;
      if (x >= N && y >= M) { reached = d; break; }
    }
    if (reached !== -1) break;
  }

  const ops: DiffOp[] = [];
  let x = N;
  let y = M;
  for (let d = reached; d > 0; d--) {
    const vPrev = trace[d];
    const k = x - y;
    let prevK: number;
    if (k === -d || (k !== d && (vPrev[k - 1] ?? -1) < (vPrev[k + 1] ?? -1))) {
      prevK = k + 1;
    } else {
      prevK = k - 1;
    }
    const prevX = vPrev[prevK] ?? 0;
    const prevY = prevX - prevK;
    while (x > prevX && y > prevY) { ops.push({ type: "eq", a: x - 1, b: y - 1 }); x--; y--; }
    if (x === prevX) { ops.push({ type: "ins", b: y - 1 }); y--; }
    else { ops.push({ type: "del", a: x - 1 }); x--; }
  }
  while (x > 0 && y > 0) { ops.push({ type: "eq", a: x - 1, b: y - 1 }); x--; y--; }
  while (x > 0) { ops.push({ type: "del", a: x - 1 }); x--; }
  while (y > 0) { ops.push({ type: "ins", b: y - 1 }); y--; }
  return ops.reverse();
}


interface Line { norm: string; raw: string; page: number; items: number[]; }
interface Frag { idx: number; str: string; x: number; y: number; w: number; h: number; }

async function extractLines(pages: PDFPageProxy[]): Promise<Line[]> {
  const lines: Line[] = [];

  for (let p = 0; p < pages.length; p++) {
    const page = pages[p];
    const pageWidth = page.getViewport({ scale: 1 }).width;
    const content = await page.getTextContent();

    const frags: Frag[] = content.items
      .map((it: any, idx: number) => ({
        idx,
        str: (it.str ?? "") as string,
        x: it.transform[4] as number,
        y: it.transform[5] as number,
        w: (it.width ?? 0) as number,
        h: (it.height ?? Math.hypot(it.transform[2], it.transform[3]) ?? 10) as number,
      }))
      .filter((f) => f.str.trim().length > 0);

    frags.sort((a, b) => b.y - a.y || a.x - b.x);

    const pushSegment = (seg: Frag[]) => {
      const raw = seg.map((s) => s.str).join(" ").replace(/\s+/g, " ").trim();
      const norm = seg.map((s) => normalize(s.str)).filter(Boolean).join(" ");
      if (!norm) return;
      lines.push({ norm, raw, page: p, items: seg.map((s) => s.idx) });
    };

    const flushRow = (row: Frag[]) => {
      if (!row.length) return;
      row.sort((a, b) => a.x - b.x);
      const gapThreshold = Math.max(pageWidth * 0.025, (row[0].h || 10) * 1.5);
      let seg: Frag[] = [row[0]];
      for (let i = 1; i < row.length; i++) {
        const prev = seg[seg.length - 1];
        const gap = row[i].x - (prev.x + prev.w);
        if (gap > gapThreshold) { pushSegment(seg); seg = [row[i]]; }
        else seg.push(row[i]);
      }
      pushSegment(seg);
    };

    let row: Frag[] = [];
    let rowY: number | null = null;
    for (const f of frags) {
      if (rowY === null || Math.abs(f.y - rowY) <= (f.h || 10) * 0.6) {
        row.push(f);
        if (rowY === null) rowY = f.y;
      } else {
        flushRow(row);
        row = [f];
        rowY = f.y;
      }
    }
    flushRow(row);
  }

  return lines;
}


type ChangedMap = Map<number, Set<number>>;

interface ChangeEntry {
  id: number;
  kind: "removed" | "added" | "changed";
  clientPage: number | null;
  executedPage: number | null;
  removedText: string;
  addedText: string;
}

interface DiffResult {
  changedClient: ChangedMap;
  changedExecuted: ChangedMap;
  changes: ChangeEntry[];
  truncated: boolean;
}

const MAX_LINES = 12000;

function mark(map: ChangedMap, page: number, items: number[]) {
  let s = map.get(page);
  if (!s) { s = new Set(); map.set(page, s); }
  for (const it of items) s.add(it);
}

function runDiff(clientLines: Line[], executedLines: Line[]): DiffResult {
  const changedClient: ChangedMap = new Map();
  const changedExecuted: ChangedMap = new Map();
  const changes: ChangeEntry[] = [];

  const truncated = clientLines.length > MAX_LINES || executedLines.length > MAX_LINES;
  const a = truncated ? clientLines.slice(0, MAX_LINES) : clientLines;
  const b = truncated ? executedLines.slice(0, MAX_LINES) : executedLines;

  const ops = myersDiff(a.map((l) => l.norm), b.map((l) => l.norm));

  let id = 0, i = 0;
  let pendingDel: string[] = [], pendingIns: string[] = [];
  let delPage: number | null = null, insPage: number | null = null;

  const flush = () => {
    if (!pendingDel.length && !pendingIns.length) return;
    const allNoise = [...pendingDel, ...pendingIns]
      .join(" ").split(/\s+/).filter(Boolean).every((w) => isIgnorable(w));
    if (allNoise) { pendingDel = []; pendingIns = []; delPage = null; insPage = null; return; }
    let kind: ChangeEntry["kind"];
    if (pendingDel.length && pendingIns.length) kind = "changed";
    else if (pendingDel.length) kind = "removed";
    else kind = "added";
    changes.push({ id: id++, kind, clientPage: delPage, executedPage: insPage,
      removedText: pendingDel.join(" ").slice(0, 160),
      addedText: pendingIns.join(" ").slice(0, 160) });
    pendingDel = []; pendingIns = []; delPage = null; insPage = null;
  };

  while (i < ops.length) {
    const op = ops[i];
    if (op.type === "eq") { flush(); i++; continue; }
    if (op.type === "del") {
      const l = a[op.a!];
      mark(changedClient, l.page, l.items);
      pendingDel.push(l.raw);
      if (delPage == null) delPage = l.page;
    } else {
      const l = b[op.b!];
      mark(changedExecuted, l.page, l.items);
      pendingIns.push(l.raw);
      if (insPage == null) insPage = l.page;
    }
    i++;
  }
  flush();

  return { changedClient, changedExecuted, changes, truncated };
}

// ─── PDF loading hook ─────────────────────────────────────────────────────────

function usePdfPages(file: File) {
  const [pages, setPages] = useState<PDFPageProxy[]>([]);
  const [numPages, setNumPages] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setPages([]);
    const url = URL.createObjectURL(file);
    pdfjsLib.getDocument(url).promise.then(async (pdf: PDFDocumentProxy) => {
      if (cancelled) return;
      setNumPages(pdf.numPages);
      const ps = await Promise.all(
        Array.from({ length: pdf.numPages }, (_, i) => pdf.getPage(i + 1))
      );
      if (cancelled) return;
      setPages(ps);
      setLoading(false);
    });
    return () => { cancelled = true; URL.revokeObjectURL(url); };
  }, [file]);

  return { pages, numPages, loading };
}

// ─── Single page renderer ─────

const PdfPage = React.memo(function PdfPage({
  page, pageIndex, scale, changedItems, highlightColor,
}: {
  page: PDFPageProxy;
  pageIndex: number;
  scale: number;
  changedItems: Set<number> | undefined;
  highlightColor: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const textDiv = textRef.current;
    if (!canvas || !textDiv) return;

    const renderDpr = Math.max(window.devicePixelRatio || 1, 2); // ≥2× for crisp screenshots
    const vp  = page.getViewport({ scale: scale * renderDpr });
    const dvp = page.getViewport({ scale });

    canvas.width  = vp.width;
    canvas.height = vp.height;
    canvas.style.width  = `${dvp.width}px`;
    canvas.style.height = `${dvp.height}px`;

    const task = page.render({ canvasContext: canvas.getContext("2d")!, viewport: vp });

    task.promise.then(async () => {
      const content = await page.getTextContent();
      textDiv.innerHTML = "";
      textDiv.style.width  = `${dvp.width}px`;
      textDiv.style.height = `${dvp.height}px`;

      content.items.forEach((item: any, itemIdx: number) => {
        if (!item.str?.trim()) return;
        const tx = pdfjsLib.Util.transform(dvp.transform, item.transform);
        const fh = Math.sqrt(tx[2] * tx[2] + tx[3] * tx[3]);

        const span = document.createElement("span");
        span.textContent = item.str;
        span.style.cssText = `
          position:absolute;left:${tx[4]}px;top:${tx[5] - fh}px;
          font-size:${fh}px;font-family:sans-serif;white-space:pre;
          color:transparent;user-select:text;line-height:1;
        `;
        if (changedItems?.has(itemIdx)) {
          span.style.backgroundColor = highlightColor;
          span.style.borderRadius = "2px";
        }
        textDiv.appendChild(span);
      });
    });

    return () => { task.cancel?.(); };
  }, [page, scale, changedItems, highlightColor]);

  return (
    <div
      data-page={pageIndex}
      style={{
        position: "relative", display: "block", marginBottom: 10, lineHeight: 0,
        boxShadow: "0 2px 8px rgba(0,0,0,0.4)", borderRadius: 2,
      }}
    >
      <canvas ref={canvasRef} style={{ display: "block" }} />
      <div ref={textRef} style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none", overflow: "hidden" }} />
    </div>
  );
});


function FloatingZoomControl({
  scale,
  onScaleChange,
}: {
  scale: number;
  onScaleChange: (updater: (s: number) => number) => void;
}) {
  const glassBtn: React.CSSProperties = {
    width: 30, height: 30,
    display: "flex", alignItems: "center", justifyContent: "center",
    background: "rgba(255,255,255,0.1)",
    border: "1px solid rgba(255,255,255,0.18)",
    borderRadius: 8,
    color: "rgba(255,255,255,0.88)",
    cursor: "pointer",
    fontSize: 18, fontWeight: 300, lineHeight: 1,
    padding: 0, flexShrink: 0, userSelect: "none",
  };

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 6, padding: "6px 10px",
      backdropFilter: "blur(18px) saturate(180%)",
      WebkitBackdropFilter: "blur(18px) saturate(180%)",
      background: "rgba(12, 12, 22, 0.62)",
      border: "1px solid rgba(255,255,255,0.1)",
      borderRadius: 16,
      boxShadow: "0 8px 32px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.07)",
    }}>
      <button style={glassBtn}
        onClick={() => onScaleChange((s) => Math.max(0.5, parseFloat((s - 0.1).toFixed(1))))}
        title="Zoom out">−
      </button>
      <button
        style={{ ...glassBtn, width: 54, fontSize: 11, fontWeight: 700,
          color: "#F5A623", letterSpacing: 0.6,
          background: "rgba(245,166,35,0.12)", borderColor: "rgba(245,166,35,0.25)" }}
        onClick={() => onScaleChange(() => 1.0)}
        title="Reset to original size (100%)">
        {Math.round(scale * 100)}%
      </button>
      <button style={glassBtn}
        onClick={() => onScaleChange((s) => Math.min(3.5, parseFloat((s + 0.1).toFixed(1))))}
        title="Zoom in">+
      </button>
    </div>
  );
}


function SemanticColumn({
  label, dotColor, file, data, changed, color,
  scrollRef, scale, onScaleChange,
}: {
  label: string;
  dotColor: string;
  file: File;
  data: ReturnType<typeof usePdfPages>;
  changed: ChangedMap | undefined;
  color: string;
  scrollRef: React.RefObject<HTMLDivElement>;
  scale: number;
  onScaleChange: (updater: (s: number) => number) => void;
}) {
  const pagesRef   = useRef<HTMLDivElement>(null);
  const scaleRef   = useRef(scale);          // always-current pdfjs render scale
  const targetRef  = useRef(scale);          // always-current visual target
  const commitRef  = useRef<ReturnType<typeof setTimeout>>();
  const labelTsRef = useRef(0);              // throttle timestamp for label updates

  const [visualScale, setVisualScale] = useState(scale);

  scaleRef.current = scale;

  useLayoutEffect(() => {
    targetRef.current = scale;
    setVisualScale(scale);
    if (pagesRef.current) {
      pagesRef.current.style.transition = "zoom 0.15s ease-out";
      pagesRef.current.style.zoom = "1";
    }
  }, [scale]);

  // Wheel zoom: CSS zoom updates instantly; pdfjs re-render is debounced.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const handleWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();

      const sensitivity = e.deltaMode === 1 ? 0.05 : 0.0008;
      const factor = Math.exp(-e.deltaY * sensitivity);
      const newTarget = Math.min(3.5, Math.max(0.5,
        parseFloat((targetRef.current * factor).toFixed(3))
      ));
      targetRef.current = newTarget;

      // Instant CSS zoom (no React, no pdfjs).
      if (pagesRef.current) {
        pagesRef.current.style.transition = "none";
        pagesRef.current.style.zoom = String(Math.max(0.1, newTarget / scaleRef.current));
      }

      const now = performance.now();
      if (now - labelTsRef.current > 50) {
        labelTsRef.current = now;
        setVisualScale(newTarget);
      }

      // Debounced pdfjs re-render (250 ms after last tick).
      clearTimeout(commitRef.current);
      commitRef.current = setTimeout(() => {
        onScaleChange(() => targetRef.current);
      }, 250);
    };

    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", handleWheel);
      clearTimeout(commitRef.current);
    };
  }, [scrollRef, onScaleChange]);

  // Button clicks: commit immediately (no debounce) and update label too.
  const handleButtonScale = useCallback((updater: (s: number) => number) => {
    const next = updater(targetRef.current);
    targetRef.current = next;
    setVisualScale(next);
    onScaleChange(() => next);
  }, [onScaleChange]);

  return (
    <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
      {/* Column header */}
      <div style={{
        padding: "8px 14px", borderBottom: "1px solid hsl(var(--border))",
        background: "hsl(var(--card))", display: "flex", alignItems: "center",
        gap: 8, flexShrink: 0,
      }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: dotColor }} />
        <span style={{ fontSize: 12, fontWeight: 500, color: "hsl(var(--foreground))" }}>{label}</span>
        {!data.loading && (
          <span style={{ fontSize: 11, color: "hsl(var(--muted-foreground))" }}>{data.numPages} pages</span>
        )}
        <span style={{
          marginLeft: "auto", fontSize: 11, color: "hsl(var(--muted-foreground))",
          maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {file.name}
        </span>
      </div>

      {/* Scroll area */}
      <div style={{ flex: 1, position: "relative", minHeight: 0 }}>
        <div
          ref={scrollRef}
          style={{
            position: "absolute", inset: 0,
            overflowY: "auto", overflowX: "auto",
            background: "#111",
          }}
        >
          {/* pagesRef receives CSS zoom — affects layout so scroll range stays correct */}
          <div ref={pagesRef} style={{ padding: "14px 18px" }}>
            {data.loading ? (
              <div style={{ color: "#666", fontSize: 13, padding: "3rem", textAlign: "center" }}>Loading PDF…</div>
            ) : (
              data.pages.map((p, i) => (
                <PdfPage
                  key={i}
                  page={p}
                  pageIndex={i}
                  scale={scale}
                  changedItems={changed?.get(i)}
                  highlightColor={color}
                />
              ))
            )}
          </div>
        </div>

        {/* Floating glassmorphic zoom control */}
        <div style={{
          position: "absolute", bottom: 18,
          left: "50%", transform: "translateX(-50%)",
          zIndex: 10, pointerEvents: "auto",
        }}>
          <FloatingZoomControl scale={visualScale} onScaleChange={handleButtonScale} />
        </div>
      </div>
    </div>
  );
}


interface SemanticProps {
  clientPdf: File;
  outputPdf: File;
  leftScale: number;
  rightScale: number;
  onLeftScaleChange: (updater: (s: number) => number) => void;
  onRightScaleChange: (updater: (s: number) => number) => void;
  syncScroll: boolean;
  onDiff: (d: DiffResult | null) => void;
  jumpTarget: { clientPage: number | null; executedPage: number | null } | null;
}

function SemanticView({
  clientPdf, outputPdf, leftScale, rightScale, onLeftScaleChange, onRightScaleChange,
  syncScroll, onDiff, jumpTarget,
}: SemanticProps) {
  const left  = usePdfPages(clientPdf);
  const right = usePdfPages(outputPdf);
  const [diff, setDiff] = useState<DiffResult | null>(null);

  const leftRef    = useRef<HTMLDivElement>(null);
  const rightRef   = useRef<HTMLDivElement>(null);
  const isSyncing  = useRef(false);

  // Compute diff once both docs are loaded.
  useEffect(() => {
    if (left.loading || right.loading) return;
    let cancelled = false;
    (async () => {
      const [ct, et] = await Promise.all([extractLines(left.pages), extractLines(right.pages)]);
      if (cancelled) return;
      const d = runDiff(ct, et);
      setDiff(d);
      onDiff(d);
    })();
    return () => { cancelled = true; };
  }, [left.loading, right.loading, left.pages, right.pages]);

  const syncFrom = useCallback((src: HTMLDivElement, dst: HTMLDivElement) => {
    const srcMax = src.scrollHeight - src.clientHeight;
    const dstMax = dst.scrollHeight - dst.clientHeight;
    if (srcMax > 0) {
      const srcPages = src.querySelectorAll<HTMLElement>("[data-page]");
      let anchored = false;
      for (const el of Array.from(srcPages)) {
        const top = el.offsetTop;
        const bottom = top + el.offsetHeight;
        if (bottom > src.scrollTop) {
          const idx = el.getAttribute("data-page");
          const dstEl = dst.querySelector<HTMLElement>(`[data-page="${idx}"]`);
          if (dstEl) {
            const within = (src.scrollTop - top) / Math.max(1, el.offsetHeight);
            dst.scrollTop = Math.min(dstMax, dstEl.offsetTop + within * dstEl.offsetHeight);
            anchored = true;
          }
          break;
        }
      }
      if (!anchored) dst.scrollTop = (src.scrollTop / srcMax) * dstMax;
    }
    const srcMaxX = src.scrollWidth - src.clientWidth;
    const dstMaxX = dst.scrollWidth - dst.clientWidth;
    if (srcMaxX > 0 && dstMaxX > 0) {
      dst.scrollLeft = (src.scrollLeft / srcMaxX) * dstMaxX;
    }
  }, []);

  useEffect(() => {
    const l = leftRef.current;
    const r = rightRef.current;
    if (!l || !r) return;
    const makeHandler = (src: HTMLDivElement, dst: HTMLDivElement) => () => {
      if (!syncScroll || isSyncing.current) return;
      isSyncing.current = true;
      syncFrom(src, dst);
      requestAnimationFrame(() => requestAnimationFrame(() => { isSyncing.current = false; }));
    };
    const lh = makeHandler(l, r);
    const rh = makeHandler(r, l);
    l.addEventListener("scroll", lh, { passive: true });
    r.addEventListener("scroll", rh, { passive: true });
    return () => {
      l.removeEventListener("scroll", lh);
      r.removeEventListener("scroll", rh);
    };
  }, [syncScroll, syncFrom]);

  // Jump to a change.
  useEffect(() => {
    if (!jumpTarget) return;
    const scrollToPage = (ref: React.RefObject<HTMLDivElement>, pg: number | null) => {
      if (!ref.current || pg == null) return;
      const el = ref.current.querySelector<HTMLElement>(`[data-page="${pg}"]`);
      if (el) ref.current.scrollTo({ top: el.offsetTop - 12, behavior: "smooth" });
    };
    isSyncing.current = true;
    scrollToPage(leftRef, jumpTarget.clientPage);
    scrollToPage(rightRef, jumpTarget.executedPage);
    const t = setTimeout(() => { isSyncing.current = false; }, 600);
    return () => clearTimeout(t);
  }, [jumpTarget]);

  return (
    <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
      <SemanticColumn
        label="Client Test Script" dotColor={COLOR_REMOVED_SOLID}
        file={clientPdf} data={left} changed={diff?.changedClient} color={COLOR_REMOVED}
        scrollRef={leftRef} scale={leftScale} onScaleChange={onLeftScaleChange}
      />
      <div style={{ width: 1, background: "hsl(var(--border))", flexShrink: 0 }} />
      <SemanticColumn
        label="V-Assure Output" dotColor={COLOR_ADDED_SOLID}
        file={outputPdf} data={right} changed={diff?.changedExecuted} color={COLOR_ADDED}
        scrollRef={rightRef} scale={rightScale} onScaleChange={onRightScaleChange}
      />
    </div>
  );
}


function OverlayPage({ clientPage, executedPage, scale }: {
  clientPage: PDFPageProxy | undefined;
  executedPage: PDFPageProxy | undefined;
  scale: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const out = canvasRef.current;
    if (!out) return;
    let cancelled = false;

    const renderTo = async (page: PDFPageProxy, w: number, h: number) => {
      const renderDpr = Math.max(window.devicePixelRatio || 1, 2);
      const c = document.createElement("canvas");
      c.width = w * renderDpr; c.height = h * renderDpr;
      const ctx = c.getContext("2d", { willReadFrequently: true })!;
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, c.width, c.height);
      const baseVp = page.getViewport({ scale });
      const sx = (w * renderDpr) / baseVp.width;
      const vp = page.getViewport({ scale: scale * sx });
      await page.render({ canvasContext: ctx, viewport: vp }).promise;
      return ctx.getImageData(0, 0, c.width, c.height);
    };

    (async () => {
      const ref = clientPage ?? executedPage;
      if (!ref) return;
      const renderDpr = Math.max(window.devicePixelRatio || 1, 2);
      const vp = ref.getViewport({ scale });
      const w = Math.floor(vp.width);
      const h = Math.floor(vp.height);

      out.width = w; out.height = h;
      out.style.width = `${w}px`; out.style.height = `${h}px`;

      const blankW = w * renderDpr, blankH = h * renderDpr;
      const blank = new ImageData(blankW, blankH);
      for (let i = 0; i < blank.data.length; i += 4) {
        blank.data[i] = blank.data[i + 1] = blank.data[i + 2] = 255;
        blank.data[i + 3] = 255;
      }
      const ca = clientPage   ? await renderTo(clientPage, w, h)   : blank;
      const ea = executedPage ? await renderTo(executedPage, w, h) : blank;
      if (cancelled) return;

      const hiW = blankW, hiH = blankH;
      const hiCanvas = document.createElement("canvas");
      hiCanvas.width = hiW; hiCanvas.height = hiH;
      const hiCtx = hiCanvas.getContext("2d")!;
      const res = hiCtx.createImageData(hiW, hiH);
      const INK = 160;
      for (let j = 0; j < ca.data.length; j += 4) {
        const lc = 0.299 * ca.data[j] + 0.587 * ca.data[j + 1] + 0.114 * ca.data[j + 2];
        const le = 0.299 * ea.data[j] + 0.587 * ea.data[j + 1] + 0.114 * ea.data[j + 2];
        const ci = lc < INK, ei = le < INK;
        let r = 255, g = 255, b = 255;
        if (ci && ei)        { r = g = b = 205; }
        else if (ci && !ei)  { r = 239; g = 68;  b = 68; }
        else if (!ci && ei)  { r = 34;  g = 197; b = 94; }
        res.data[j] = r; res.data[j + 1] = g; res.data[j + 2] = b; res.data[j + 3] = 255;
      }
      hiCtx.putImageData(res, 0, 0);

      const outCtx = out.getContext("2d")!;
      outCtx.drawImage(hiCanvas, 0, 0, w, h);
    })();

    return () => { cancelled = true; };
  }, [clientPage, executedPage, scale]);

  return (
    <div style={{
      marginBottom: 10, lineHeight: 0, boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
      borderRadius: 2, background: "#fff",
    }}>
      <canvas ref={canvasRef} style={{ display: "block" }} />
    </div>
  );
}

function OverlayView({ clientPdf, outputPdf }: { clientPdf: File; outputPdf: File }) {
  const [renderScale, setRenderScale] = useState(1.4);
  const [visualScale, setVisualScale] = useState(1.4);

  const left     = usePdfPages(clientPdf);
  const right    = usePdfPages(outputPdf);
  const loading  = left.loading || right.loading;
  const count    = Math.max(left.numPages, right.numPages);

  const containerRef = useRef<HTMLDivElement>(null);
  const pagesRef     = useRef<HTMLDivElement>(null);
  const scaleRef     = useRef(1.4);
  const targetRef    = useRef(1.4);
  const commitRef    = useRef<ReturnType<typeof setTimeout>>();
  const labelTsRef   = useRef(0);

  scaleRef.current = renderScale;

  useLayoutEffect(() => {
    targetRef.current = renderScale;
    setVisualScale(renderScale);
    if (pagesRef.current) {
      pagesRef.current.style.transition = "zoom 0.15s ease-out";
      pagesRef.current.style.zoom = "1";
    }
  }, [renderScale]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handleWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      const sensitivity = e.deltaMode === 1 ? 0.05 : 0.0008;
      const factor = Math.exp(-e.deltaY * sensitivity);
      const newTarget = Math.min(3.5, Math.max(0.5,
        parseFloat((targetRef.current * factor).toFixed(3))
      ));
      targetRef.current = newTarget;
      if (pagesRef.current) {
        pagesRef.current.style.transition = "none";
        pagesRef.current.style.zoom = String(Math.max(0.1, newTarget / scaleRef.current));
      }
      const now = performance.now();
      if (now - labelTsRef.current > 50) {
        labelTsRef.current = now;
        setVisualScale(newTarget);
      }
      clearTimeout(commitRef.current);
      commitRef.current = setTimeout(() => { setRenderScale(targetRef.current); }, 250);
    };
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", handleWheel);
      clearTimeout(commitRef.current);
    };
  }, []);

  const handleButtonScale = useCallback((updater: (s: number) => number) => {
    const next = updater(targetRef.current);
    targetRef.current = next;
    setVisualScale(next);
    setRenderScale(next);
  }, []);

  return (
    <div style={{ flex: 1, position: "relative", minHeight: 0 }}>
      <div ref={containerRef} style={{ position: "absolute", inset: 0, overflow: "auto", background: "#111" }}>
        <div ref={pagesRef} style={{ padding: "14px 18px" }}>
          {loading ? (
            <div style={{ color: "#666", fontSize: 13, padding: "3rem", textAlign: "center" }}>Loading PDFs…</div>
          ) : (
            <div style={{ maxWidth: 900, margin: "0 auto" }}>
              {Array.from({ length: count }, (_, i) => (
                <OverlayPage
                  key={i}
                  clientPage={left.pages[i]}
                  executedPage={right.pages[i]}
                  scale={renderScale}
                />
              ))}
            </div>
          )}
        </div>
      </div>
      <div style={{
        position: "absolute", bottom: 18,
        left: "50%", transform: "translateX(-50%)",
        zIndex: 10,
      }}>
        <FloatingZoomControl scale={visualScale} onScaleChange={handleButtonScale} />
      </div>
    </div>
  );
}


function ChangeList({ diff, onJump }: {
  diff: DiffResult | null;
  onJump: (clientPage: number | null, executedPage: number | null) => void;
}) {
  if (!diff) return (
    <div style={{ padding: 16, fontSize: 12, color: "hsl(var(--muted-foreground))" }}>Analysing…</div>
  );
  if (diff.changes.length === 0) return (
    <div style={{ padding: 16, fontSize: 12, color: "hsl(var(--muted-foreground))" }}>No textual differences found.</div>
  );

  return (
    <div style={{ overflowY: "auto", flex: 1 }}>
      {diff.truncated && (
        <div style={{ padding: "8px 12px", fontSize: 11, color: "#F5A623" }}>
          Large document — diff limited to the first {MAX_LINES.toLocaleString()} lines.
        </div>
      )}
      {diff.changes.map((c) => {
        const color =
          c.kind === "removed" ? COLOR_REMOVED_SOLID :
          c.kind === "added" ? COLOR_ADDED_SOLID : "#F5A623";
        const page = (c.clientPage ?? c.executedPage ?? 0) + 1;
        return (
          <button
            key={c.id}
            onClick={() => onJump(c.clientPage, c.executedPage)}
            style={{
              display: "flex", alignItems: "flex-start", gap: 8, width: "100%",
              textAlign: "left", padding: "8px 12px", cursor: "pointer",
              background: "transparent", border: "none",
              borderBottom: "1px solid hsl(var(--border))",
            }}
          >
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: color, marginTop: 5, flexShrink: 0 }} />
            <span style={{ flex: 1, minWidth: 0 }}>
              <span style={{ fontSize: 11, color: "hsl(var(--muted-foreground))" }}>{c.kind} · p.{page}</span>
              {c.removedText && (
                <span style={{ display: "block", fontSize: 12, color: "#fca5a5", textDecoration: "line-through", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {c.removedText}
                </span>
              )}
              {c.addedText && (
                <span style={{ display: "block", fontSize: 12, color: "#86efac", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {c.addedText}
                </span>
              )}
            </span>
            <ChevronRight size={14} style={{ color: "hsl(var(--muted-foreground))", flexShrink: 0, marginTop: 2 }} />
          </button>
        );
      })}
    </div>
  );
}


interface Props {
  clientPdf: File;
  outputPdf: File;
  result?: ComparisonResult | null;
}

type Mode = "semantic" | "overlay";

const NewBadge = () => (
  <span style={{
    fontSize: 8, fontWeight: 700, letterSpacing: 0.3, padding: "1px 4px",
    borderRadius: 4, marginLeft: 2, background: "#b3f523", color: "#1a1a1a",
    lineHeight: 1.4, textTransform: "uppercase",
  }}>
    New
  </span>
);

const WipBadge = () => (
  <span style={{
    fontSize: 8, fontWeight: 700, letterSpacing: 0.3, padding: "1px 4px",
    borderRadius: 4, marginLeft: 2, background: "#F5A623", color: "#1a1a1a",
    lineHeight: 1.4, textTransform: "uppercase",
  }}>
    WIP
  </span>
);

export default function PdfSideBySideViewer({ clientPdf, outputPdf }: Props) {
  const [leftScale, setLeftScale]   = useState(1.4);
  const [rightScale, setRightScale] = useState(1.4);
  const [syncScroll, setSyncScroll] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [mode, setMode]             = useState<Mode>("semantic");
  const [showChanges, setShowChanges] = useState(true);
  const [diff, setDiff]             = useState<DiffResult | null>(null);
  const [jumpTarget, setJumpTarget] =
    useState<{ clientPage: number | null; executedPage: number | null } | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) containerRef.current?.requestFullscreen();
    else document.exitFullscreen();
  }, []);

  useEffect(() => {
    const h = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", h);
    return () => document.removeEventListener("fullscreenchange", h);
  }, []);

  const changeCount = useMemo(() => diff?.changes.length ?? 0, [diff]);

  const btn = (active = false): React.CSSProperties => ({
    display: "flex", alignItems: "center", gap: 5,
    padding: "5px 10px", borderRadius: 8, cursor: "pointer",
    fontSize: 12, fontWeight: 500, transition: "all 0.15s",
    border: `1px solid ${active ? "#F5A623" : "hsl(var(--border))"}`,
    background: active ? "rgba(245,166,35,0.1)" : "transparent",
    color: active ? "#F5A623" : "hsl(var(--muted-foreground))",
  });

  return (
    <div
      ref={containerRef}
      style={{
        display: "flex", flexDirection: "column",
        height: isFullscreen ? "100vh" : "100%",
        minHeight: 600, background: "hsl(var(--background))",
      }}
    >
      {/* Toolbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "8px 14px", borderBottom: "1px solid hsl(var(--border))",
        background: "hsl(var(--card))", flexShrink: 0, flexWrap: "wrap", rowGap: 6,
      }}>
        <div style={{ display: "flex", gap: 5 }}>
          <button onClick={() => setMode("semantic")} style={btn(mode === "semantic")}>
            <FileText size={13} /> Semantic Text
          </button>
          <button onClick={() => setMode("overlay")} style={btn(mode === "overlay")}>
            <Layers size={13} /> Content Overlay <WipBadge />
          </button>
        </div>

        {mode === "semantic" && (
          <>
            <div style={{ width: 1, height: 20, background: "hsl(var(--border))" }} />
            <button onClick={() => setSyncScroll((v) => !v)} style={btn(syncScroll)}
              title="Sync scroll keeps both panes aligned by position">
              {syncScroll ? <Link size={13} /> : <Unlink size={13} />}
              Sync scroll: {syncScroll ? "ON" : "OFF"}
            </button>
            <button onClick={() => setShowChanges((v) => !v)} style={btn(showChanges)}>
              Change report ({changeCount}) <NewBadge />
            </button>
          </>
        )}

        <div style={{ display: "flex", gap: 12, alignItems: "center", marginLeft: "auto" }}>
          {[
            [COLOR_REMOVED, "Removed (client)"],
            [COLOR_ADDED,   "Added (executed)"],
          ].map(([c, l]) => (
            <span key={l} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "hsl(var(--muted-foreground))" }}>
              <span style={{ width: 11, height: 11, borderRadius: 2, background: c }} />
              {l}
            </span>
          ))}
          <button onClick={toggleFullscreen} style={btn(isFullscreen)}>
            {isFullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
            {isFullscreen ? "Exit" : "Fullscreen"}
          </button>
        </div>
      </div>

      {/* Body */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {mode === "semantic" ? (
          <SemanticView
            clientPdf={clientPdf} outputPdf={outputPdf}
            leftScale={leftScale} rightScale={rightScale}
            onLeftScaleChange={setLeftScale} onRightScaleChange={setRightScale}
            syncScroll={syncScroll} onDiff={setDiff} jumpTarget={jumpTarget}
          />
        ) : (
          <OverlayView clientPdf={clientPdf} outputPdf={outputPdf} />
        )}

        {mode === "semantic" && showChanges && (
          <>
            <div style={{ width: 1, background: "hsl(var(--border))", flexShrink: 0 }} />
            <div style={{
              width: 280, flexShrink: 0, display: "flex", flexDirection: "column",
              background: "hsl(var(--card))",
            }}>
              <div style={{
                padding: "8px 12px", borderBottom: "1px solid hsl(var(--border))",
                fontSize: 12, fontWeight: 600, color: "hsl(var(--foreground))",
              }}>
                Changes ({changeCount})
              </div>
              <ChangeList
                diff={diff}
                onJump={(cp, ep) => setJumpTarget({ clientPage: cp, executedPage: ep })}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
