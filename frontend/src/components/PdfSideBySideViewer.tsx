/**
 * PdfSideBySideViewer.tsx
 *
 * Fixes:
 * 1. Scroll is fully isolated per column — sync only activates when toggle is ON
 * 2. Smarter diff highlighting — filters stop words, short words, requires min length 4
 * 3. No screenshot step tracer (removed per requirements)
 */

import { useEffect, useRef, useState, useCallback } from "react";
import type { ComparisonResult } from "@/types/comparison";
import * as pdfjsLib from "pdfjs-dist";
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import { Maximize2, Minimize2, Link, Unlink, ZoomIn, ZoomOut } from "lucide-react";

pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.mjs",
  import.meta.url
).toString();

// ─── Stop words to exclude from diff highlighting ────────────────────────────

const STOP_WORDS = new Set([
  "the","a","an","and","or","but","in","on","at","to","for","of","with",
  "by","from","up","is","are","was","were","be","been","being","have",
  "has","had","do","does","did","will","would","could","should","may",
  "might","shall","that","this","these","those","it","its","as","if",
  "not","no","so","than","then","when","where","which","who","how",
  "all","any","both","each","few","more","most","other","some","such",
  "into","through","during","before","after","above","below","between",
  "out","off","over","under","again","further","once","click","select",
  "the","page","is","displayed","user","logged","home",
]);

function isSignificantWord(w: string): boolean {
  return w.length >= 4 && !STOP_WORDS.has(w) && !/^\d+$/.test(w);
}

// ─── Collect meaningful diff words from backend result ────────────────────────

function collectDiffWords(result: ComparisonResult | null) {
  const clientWords = new Set<string>();
  const executedWords = new Set<string>();
  if (!result) return { clientWords, executedWords };

  const tok = (s: string) =>
    s.toLowerCase().split(/\W+/).filter((w) => isSignificantWord(w));

  const process = (a?: string | null, b?: string | null) => {
    if (!a || !b) return;
    const aSet = new Set(tok(a));
    const bSet = new Set(tok(b));
    // Only flag words that are truly unique to one side AND significant
    tok(a).forEach((w) => { if (!bSet.has(w)) clientWords.add(w); });
    tok(b).forEach((w) => { if (!aSet.has(w)) executedWords.add(w); });
  };

  Object.values(result.setup_differences ?? {}).forEach((ds) =>
    ds.forEach((d) => process(d.client, d.executed))
  );
  Object.values(result.execution_differences ?? {}).forEach((ds) =>
    ds.forEach((d) => {
      process(d.client, d.executed);
      process(d.client_expected, d.executed_actual);
      process(d.expected, d.actual);
    })
  );

  return { clientWords, executedWords };
}

// ─── Single page renderer ─────────────────────────────────────────────────────

function PdfPage({
  page, scale, diffWords, highlightColor,
}: {
  page: PDFPageProxy;
  scale: number;
  diffWords: Set<string>;
  highlightColor: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const textDiv = textRef.current;
    if (!canvas || !textDiv) return;

    const dpr = window.devicePixelRatio || 1;
    const vp = page.getViewport({ scale: scale * dpr });
    const dvp = page.getViewport({ scale });

    canvas.width = vp.width;
    canvas.height = vp.height;
    canvas.style.width = `${dvp.width}px`;
    canvas.style.height = `${dvp.height}px`;

    const task = page.render({ canvasContext: canvas.getContext("2d")!, viewport: vp });

    task.promise.then(async () => {
      const content = await page.getTextContent();
      textDiv.innerHTML = "";
      textDiv.style.width = `${dvp.width}px`;
      textDiv.style.height = `${dvp.height}px`;

      content.items.forEach((item: any) => {
        if (!item.str?.trim()) return;
        const tx = pdfjsLib.Util.transform(dvp.transform, item.transform);
        const fh = Math.sqrt(tx[2] * tx[2] + tx[3] * tx[3]);

        const span = document.createElement("span");
        span.textContent = item.str;
        span.style.cssText = `
          position:absolute;
          left:${tx[4]}px;
          top:${tx[5] - fh}px;
          font-size:${fh}px;
          font-family:sans-serif;
          white-space:pre;
          color:transparent;
          user-select:text;
          line-height:1;
        `;

        // Only highlight if the span contains a significant diff word
        const spanWords = item.str.toLowerCase().split(/\W+/).filter(isSignificantWord);
        if (spanWords.length > 0 && spanWords.some((w: string) => diffWords.has(w))) {
          span.style.backgroundColor = highlightColor;
          span.style.borderRadius = "2px";
        }

        textDiv.appendChild(span);
      });
    });

    return () => { task.cancel?.(); };
  }, [page, scale, diffWords, highlightColor]);

  return (
    <div style={{
      position: "relative", display: "block", marginBottom: 10, lineHeight: 0,
      boxShadow: "0 2px 8px rgba(0,0,0,0.4)", borderRadius: 2,
    }}>
      <canvas ref={canvasRef} style={{ display: "block" }} />
      <div ref={textRef} style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none", overflow: "hidden" }} />
    </div>
  );
}

// ─── PDF column — fully isolated scroll ───────────────────────────────────────

interface ColProps {
  label: string;
  file: File;
  scale: number;
  diffWords: Set<string>;
  highlightColor: string;
  dotColor: string;
  // Sync props — only used when sync is ON
  syncEnabled: boolean;
  scrollTo?: number | null;       // external scroll position to apply
  onUserScroll?: (top: number) => void; // report user scroll to parent
}

function PdfColumn({
  label, file, scale, diffWords, highlightColor, dotColor,
  syncEnabled, scrollTo, onUserScroll,
}: ColProps) {
  const [pages, setPages] = useState<PDFPageProxy[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const isReceivingSync = useRef(false); // prevent echo when applying external scroll

  // Load PDF
  useEffect(() => {
    setLoading(true);
    setPages([]);
    const url = URL.createObjectURL(file);
    pdfjsLib.getDocument(url).promise.then((pdf: PDFDocumentProxy) => {
      setCount(pdf.numPages);
      Promise.all(Array.from({ length: pdf.numPages }, (_, i) => pdf.getPage(i + 1))).then((ps) => {
        setPages(ps);
        setLoading(false);
      });
    });
    return () => URL.revokeObjectURL(url);
  }, [file]);

  // Listen to user scroll — only report up if sync is ON
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const handler = () => {
      if (isReceivingSync.current) return; // ignore programmatic scrolls
      if (syncEnabled && onUserScroll) {
        onUserScroll(el.scrollTop);
      }
    };
    el.addEventListener("scroll", handler, { passive: true });
    return () => el.removeEventListener("scroll", handler);
  }, [syncEnabled, onUserScroll]);

  // Apply external scroll position — only when sync is ON
  useEffect(() => {
    if (!syncEnabled || scrollTo == null || !scrollRef.current) return;
    isReceivingSync.current = true;
    scrollRef.current.scrollTop = scrollTo;
    // Release flag after paint
    requestAnimationFrame(() => {
      requestAnimationFrame(() => { isReceivingSync.current = false; });
    });
  }, [syncEnabled, scrollTo]);

  return (
    <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <div style={{
        padding: "8px 14px", borderBottom: "1px solid hsl(var(--border))",
        background: "hsl(var(--card))", display: "flex", alignItems: "center",
        gap: 8, flexShrink: 0,
      }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: dotColor }} />
        <span style={{ fontSize: 12, fontWeight: 500, color: "hsl(var(--foreground))" }}>{label}</span>
        {!loading && (
          <span style={{ fontSize: 11, color: "hsl(var(--muted-foreground))" }}>{count} pages</span>
        )}
        <span style={{
          marginLeft: "auto", fontSize: 11, color: "hsl(var(--muted-foreground))",
          maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {file.name}
        </span>
      </div>

      {/* Pages — each column scrolls independently */}
      <div
        ref={scrollRef}
        style={{ flex: 1, overflowY: "auto", overflowX: "auto", padding: "14px 18px", background: "#111" }}
      >
        {loading ? (
          <div style={{ color: "#666", fontSize: 13, padding: "3rem", textAlign: "center" }}>Loading PDF…</div>
        ) : (
          pages.map((p, i) => (
            <PdfPage
              key={i}
              page={p}
              scale={scale}
              diffWords={diffWords}
              highlightColor={highlightColor}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface Props {
  clientPdf: File;
  outputPdf: File;
  result: ComparisonResult | null;
}

export default function PdfSideBySideViewer({ clientPdf, outputPdf, result }: Props) {
  const [scale, setScale] = useState(1.4);
  const [syncScroll, setSyncScroll] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Sync state: which side last scrolled, and to what position
  const [leftScrollPos, setLeftScrollPos] = useState<number | null>(null);
  const [rightScrollPos, setRightScrollPos] = useState<number | null>(null);
  // Track who drove the last sync to avoid echo
  const lastDriver = useRef<"left" | "right" | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const { clientWords, executedWords } = collectDiffWords(result);

  const handleLeftScroll = useCallback((top: number) => {
    lastDriver.current = "left";
    setRightScrollPos(top);
  }, []);

  const handleRightScroll = useCallback((top: number) => {
    lastDriver.current = "right";
    setLeftScrollPos(top);
  }, []);

  // Fullscreen
  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) containerRef.current?.requestFullscreen();
    else document.exitFullscreen();
  }, []);

  useEffect(() => {
    const h = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", h);
    return () => document.removeEventListener("fullscreenchange", h);
  }, []);

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
        minHeight: 600,
        background: "hsl(var(--background))",
      }}
    >
      {/* Toolbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "8px 14px", borderBottom: "1px solid hsl(var(--border))",
        background: "hsl(var(--card))", flexShrink: 0, flexWrap: "wrap", rowGap: 6,
      }}>
        {/* Zoom */}
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <button
            onClick={() => setScale((s) => Math.max(0.5, +(s - 0.1).toFixed(1)))}
            style={btn()}
          >
            <ZoomOut size={13} />
          </button>
          <span style={{ fontSize: 12, fontWeight: 600, minWidth: 38, textAlign: "center", color: "#F5A623" }}>
            {Math.round(scale * 100)}%
          </span>
          <button
            onClick={() => setScale((s) => Math.min(3.5, +(s + 0.1).toFixed(1)))}
            style={btn()}
          >
            <ZoomIn size={13} />
          </button>
          <input
            type="range" min={0.5} max={3.5} step={0.1} value={scale}
            onChange={(e) => setScale(parseFloat(e.target.value))}
            style={{ width: 80 }}
          />
        </div>

        <div style={{ width: 1, height: 20, background: "hsl(var(--border))" }} />

        {/* Sync scroll toggle */}
        <button
          onClick={() => {
            setSyncScroll((v) => !v);
            // Reset sync positions when toggling
            setLeftScrollPos(null);
            setRightScrollPos(null);
          }}
          style={btn(syncScroll)}
          title="Sync scroll: enable only when both PDFs have the same number of pages"
        >
          {syncScroll ? <Link size={13} /> : <Unlink size={13} />}
          Sync scroll: {syncScroll ? "ON" : "OFF"}
        </button>

        {/* Legend */}
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginLeft: "auto" }}>
          {[
            ["rgba(239,68,68,0.55)", "Removed (client)"],
            ["rgba(34,197,94,0.45)", "Added (executed)"],
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

      {/* Columns */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <PdfColumn
          label="Client Test Script"
          file={clientPdf}
          scale={scale}
          diffWords={clientWords}
          highlightColor="rgba(239,68,68,0.5)"
          dotColor="#ef4444"
          syncEnabled={syncScroll}
          scrollTo={syncScroll && lastDriver.current === "right" ? leftScrollPos : null}
          onUserScroll={handleLeftScroll}
        />
        <div style={{ width: 1, background: "hsl(var(--border))", flexShrink: 0 }} />
        <PdfColumn
          label="V-Assure Output"
          file={outputPdf}
          scale={scale}
          diffWords={executedWords}
          highlightColor="rgba(34,197,94,0.45)"
          dotColor="#22c55e"
          syncEnabled={syncScroll}
          scrollTo={syncScroll && lastDriver.current === "left" ? rightScrollPos : null}
          onUserScroll={handleRightScroll}
        />
      </div>
    </div>
  );
}
