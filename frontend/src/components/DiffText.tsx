/**
 * DiffText — word-level diff highlighting, GitHub style.
 *
 * Usage:
 *   import { DiffText } from "@/components/DiffText";
 *
 *   // In your SetupStepCard / ExecutionStepCard where you show the two procedures:
 *   <DiffText expected={clientProcedure} actual={executedProcedure} side="left" />
 *   <DiffText expected={clientProcedure} actual={executedProcedure} side="right" />
 */

interface Token {
  text: string;
  type: "equal" | "removed" | "added";
}

/** Longest-common-subsequence on word arrays */
function lcs(a: string[], b: string[]): number[][] {
  const m = a.length, n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
  return dp;
}

function computeWordDiff(expected: string, actual: string): { left: Token[]; right: Token[] } {
  const wordsA = expected.split(/\s+/).filter(Boolean);
  const wordsB = actual.split(/\s+/).filter(Boolean);

  const dp = lcs(wordsA, wordsB);

  const left: Token[] = [];
  const right: Token[] = [];

  let i = wordsA.length, j = wordsB.length;
  const ops: Array<{ type: "equal" | "removed" | "added"; a?: string; b?: string }> = [];

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && wordsA[i - 1] === wordsB[j - 1]) {
      ops.unshift({ type: "equal", a: wordsA[i - 1], b: wordsB[j - 1] });
      i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.unshift({ type: "added", b: wordsB[j - 1] });
      j--;
    } else {
      ops.unshift({ type: "removed", a: wordsA[i - 1] });
      i--;
    }
  }

  for (const op of ops) {
    if (op.type === "equal") {
      left.push({ text: op.a!, type: "equal" });
      right.push({ text: op.b!, type: "equal" });
    } else if (op.type === "removed") {
      left.push({ text: op.a!, type: "removed" });
    } else {
      right.push({ text: op.b!, type: "added" });
    }
  }

  return { left, right };
}

interface DiffTextProps {
  /** The original / client / template text */
  expected: string;
  /** The executed / report text */
  actual: string;
  /** Which side to render */
  side: "left" | "right";
  className?: string;
}

export function DiffText({ expected, actual, side, className = "" }: DiffTextProps) {
  const { left, right } = computeWordDiff(expected, actual);
  const tokens = side === "left" ? left : right;

  return (
    <span className={className}>
      {tokens.map((tok, idx) => {
        if (tok.type === "equal") {
          return <span key={idx}>{tok.text} </span>;
        }
        if (tok.type === "removed") {
          return (
            <mark
              key={idx}
              style={{
                background: "rgba(239, 68, 68, 0.35)",
                color: "inherit",
                borderRadius: "2px",
                padding: "0 2px",
                textDecoration: "line-through",
                textDecorationColor: "rgba(239,68,68,0.7)",
              }}
            >
              {tok.text}{" "}
            </mark>
          );
        }
        // added
        return (
          <mark
            key={idx}
            style={{
              background: "rgba(34, 197, 94, 0.3)",
              color: "inherit",
              borderRadius: "2px",
              padding: "0 2px",
            }}
          >
            {tok.text}{" "}
          </mark>
        );
      })}
    </span>
  );
}
