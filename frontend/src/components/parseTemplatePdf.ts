/**
 * parseTemplatePdf.ts
 *
 * Robust client-side parser for Veeva Basics template PDFs.
 *
 * Key fixes vs previous version:
 *
 * PTS steps:
 *   PDF.js joins all cell text into a flat string with no line breaks.
 *   We split on the pattern /(?=\d+\.\s)/ to find each numbered item
 *   rather than trying to split by "\n".
 *
 * Execution steps:
 *   Y-position grouping alone merges all columns. We instead:
 *     1. Find the header row items and record X positions of
 *        "Procedure" and "Expected Results" column headers.
 *     2. For each data row, assign text items to columns by X range.
 *     3. Build separate procedure and expected-results strings per step.
 */

import * as pdfjsLib from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";

export interface ParsedSetupStep {
  stepNumber: number;
  procedure: string;
}

export interface ParsedExecutionStep {
  stepNumber: number;
  procedure: string;
  expectedResults: string;
}

export interface ParsedTemplate {
  scriptId: string;
  title: string;
  setupSteps: ParsedSetupStep[];
  executionSteps: ParsedExecutionStep[];
}

// ─── Utilities ────────────────────────────────────────────────────────────────

function clean(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

interface TItem {
  x: number;
  y: number;
  text: string;
}

/** Group text items into rows by Y proximity (tolerance = 4 pts) */
function groupByRow(items: TItem[]): TItem[][] {
  const sorted = [...items].sort((a, b) => b.y - a.y); // top → bottom
  const rows: TItem[][] = [];
  let current: TItem[] = [];
  let lastY: number | null = null;

  for (const item of sorted) {
    if (lastY === null || Math.abs(item.y - lastY) <= 4) {
      current.push(item);
    } else {
      if (current.length) rows.push(current.sort((a, b) => a.x - b.x));
      current = [item];
    }
    lastY = item.y;
  }
  if (current.length) rows.push(current.sort((a, b) => a.x - b.x));
  return rows;
}

// ─── PTS parser ───────────────────────────────────────────────────────────────

/**
 * Parse numbered PTS items from a flat concatenated string.
 * Works even when all text is on one "line" by splitting on /(?=\d+\. )/
 */
function parsePtsFromText(rawText: string): ParsedSetupStep[] {
  // Isolate the PTS section: everything after "Pre-Test Setup" label
  const ptsStart = rawText.search(/pre.?test\s+setup/i);
  if (ptsStart === -1) return [];

  let ptsText = rawText.slice(ptsStart);

  // Stop at execution table header or footer markers
  const stopMatch = ptsText.search(
    /\b(Step\s*#\s*Procedure|Procedure\s+Expected|pre.?approved\s+test\s+script|veeva\s+systems\s+confidential)/i
  );
  if (stopMatch !== -1) ptsText = ptsText.slice(0, stopMatch);

  // Split on numbered item boundaries: "1. " "2. " "3. "
  // Use a lookahead so we keep the number with its text
  const parts = ptsText.split(/(?=\b\d+\.\s)/);
  const steps: ParsedSetupStep[] = [];

  for (const part of parts) {
    const m = part.match(/^(\d+)\.\s+(.+)/s);
    if (!m) continue;
    const num = parseInt(m[1]);
    const proc = clean(m[2]);
    if (proc.length > 5) {
      steps.push({ stepNumber: num, procedure: proc });
    }
  }

  return steps;
}

// ─── Execution table parser ───────────────────────────────────────────────────

const STOP_WORDS = new Set([
  "pass", "fail", "n/a", "yes", "no", "✓", "x",
  "pass / fail / n/a", "actual results", "actual result",
]);

interface ColumnBounds {
  stepMaxX: number;        // right edge of step # column
  procMaxX: number;        // right edge of procedure column
  // everything past procMaxX and before ~actualX is expected results
  expectedMinX: number;
  expectedMaxX: number;
}

/**
 * Detect column boundaries from the header row items.
 * Returns null if this doesn't look like an execution table header.
 */
function detectColumns(headerRow: TItem[]): ColumnBounds | null {
  const headerText = headerRow.map((i) => i.text).join(" ").toLowerCase();
  if (!headerText.includes("procedure") || !headerText.includes("expected")) {
    return null;
  }

  let stepX = -1, procX = -1, expectedX = -1, actualX = 9999;

  for (const item of headerRow) {
    const t = item.text.toLowerCase().trim();
    if ((t === "step" || t === "step #" || t === "#") && stepX === -1) stepX = item.x;
    if (t.includes("procedure") && procX === -1) procX = item.x;
    if (t.includes("expected") && expectedX === -1) expectedX = item.x;
    if (t.includes("actual") && actualX === 9999) actualX = item.x;
  }

  if (procX === -1 || expectedX === -1) return null;

  // Derive boundaries with some padding
  const stepMaxX = procX - 2;
  const procMaxX = expectedX - 2;
  const expectedMaxX = actualX < 9999 ? actualX - 2 : 9999;

  return { stepMaxX, procMaxX, expectedMinX: expectedX - 5, expectedMaxX };
}

/**
 * Parse execution steps from all text items on a page using column bounds.
 */
function parseExecutionRows(
  items: TItem[],
  bounds: ColumnBounds
): Map<number, ParsedExecutionStep> {
  const result = new Map<number, ParsedExecutionStep>();
  const rows = groupByRow(items);

  for (const row of rows) {
    const rowText = row.map((i) => i.text).join(" ").toLowerCase();
    // Skip header / footer rows
    if (
      rowText.includes("procedure") ||
      rowText.includes("expected results") ||
      /veeva systems|pre-approved|script id|page \d+/i.test(rowText)
    ) continue;

    // Find step number: a standalone digit cell in the step column
    let stepNum: number | null = null;
    const procItems: TItem[] = [];
    const expItems: TItem[] = [];

    for (const item of row) {
      const t = item.text.trim();
      const x = item.x;

      if (x <= bounds.stepMaxX) {
        // Step # column
        if (/^\d+$/.test(t) && stepNum === null) {
          stepNum = parseInt(t);
        }
      } else if (x <= bounds.procMaxX) {
        // Procedure column
        if (t && !STOP_WORDS.has(t.toLowerCase())) procItems.push(item);
      } else if (x >= bounds.expectedMinX && x <= bounds.expectedMaxX) {
        // Expected results column
        if (t && !STOP_WORDS.has(t.toLowerCase())) expItems.push(item);
      }
      // Ignore actual results and pass/fail columns
    }

    if (stepNum === null || procItems.length === 0) continue;

    const procedure = clean(procItems.map((i) => i.text).join(" "));
    const expectedResults = clean(expItems.map((i) => i.text).join(" "));

    if (!result.has(stepNum)) {
      result.set(stepNum, { stepNumber: stepNum, procedure, expectedResults });
    } else {
      // Append continuation text (step spans multiple PDF rows)
      const existing = result.get(stepNum)!;
      if (procedure && !existing.procedure.includes(procedure.slice(0, 20))) {
        existing.procedure = clean(existing.procedure + " " + procedure);
      }
      if (expectedResults && !existing.expectedResults.includes(expectedResults.slice(0, 20))) {
        existing.expectedResults = clean(existing.expectedResults + " " + expectedResults);
      }
    }
  }

  return result;
}

// ─── Main export ──────────────────────────────────────────────────────────────

export async function parseTemplatePdf(file: File): Promise<ParsedTemplate> {
  const url = URL.createObjectURL(file);

  try {
    const pdf: PDFDocumentProxy = await pdfjsLib.getDocument(url).promise;

    let scriptId = "";
    let title = "";
    let setupSteps: ParsedSetupStep[] = [];
    const executionStepsMap = new Map<number, ParsedExecutionStep>();

    // Collect column bounds once we find the first execution table header
    let colBounds: ColumnBounds | null = null;

    for (let pi = 0; pi < pdf.numPages; pi++) {
      const page = await pdf.getPage(pi + 1);
      const content = await page.getTextContent();

      // All text items with positions for this page
      const allItems: TItem[] = [];
      for (const it of content.items as any[]) {
        if (!it.str?.trim()) continue;
        allItems.push({ x: it.transform[4], y: it.transform[5], text: it.str });
      }

      // Flat raw text (joined in PDF order, which is usually reading order)
      const rawText = allItems.map((i) => i.text).join(" ");

      // ── Metadata (pages 0-2) ──────────────────────────────────────
      if (pi < 3) {
        if (!scriptId) {
          const m =
            rawText.match(/Test Script ID\s+([A-Z0-9][A-Z0-9\-]+)/i) ||
            rawText.match(/(BASICS-[A-Z0-9\-]+)/);
          if (m) scriptId = m[1].trim();
        }
        if (!title) {
          const m = rawText.match(/Title\s+(.+?)(?:Build Number|Description|Vault Name)/i);
          if (m) title = clean(m[1]);
        }
      }

      // ── PTS (pages 0-2 only, search raw text) ────────────────────
      if (pi <= 2 && setupSteps.length === 0) {
        const parsed = parsePtsFromText(rawText);
        if (parsed.length > 0) setupSteps = parsed;
      }

      // ── Execution table ───────────────────────────────────────────
      // Detect column bounds from any page that has the header row
      if (colBounds === null) {
        const rows = groupByRow(allItems);
        for (const row of rows) {
          const bounds = detectColumns(row);
          if (bounds) { colBounds = bounds; break; }
        }
      }

      // Parse execution rows using detected column bounds
      if (colBounds !== null) {
        const pageSteps = parseExecutionRows(allItems, colBounds);
        pageSteps.forEach((step, num) => {
          if (!executionStepsMap.has(num)) {
            executionStepsMap.set(num, step);
          } else {
            // Continuation from previous page
            const existing = executionStepsMap.get(num)!;
            if (step.procedure && !existing.procedure.includes(step.procedure.slice(0, 15))) {
              existing.procedure = clean(existing.procedure + " " + step.procedure);
            }
            if (step.expectedResults && !existing.expectedResults.includes(step.expectedResults.slice(0, 15))) {
              existing.expectedResults = clean(existing.expectedResults + " " + step.expectedResults);
            }
          }
        });
      }
    }

    // Sort and deduplicate setup steps
    const seenSetup = new Set<number>();
    const uniqueSetup = setupSteps
      .filter((s) => {
        if (seenSetup.has(s.stepNumber)) return false;
        seenSetup.add(s.stepNumber);
        return true;
      })
      .sort((a, b) => a.stepNumber - b.stepNumber);

    const executionSteps = [...executionStepsMap.values()].sort(
      (a, b) => a.stepNumber - b.stepNumber
    );

    return { scriptId, title, setupSteps: uniqueSetup, executionSteps };
  } finally {
    URL.revokeObjectURL(url);
  }
}