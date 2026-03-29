import { useState } from "react";
import { ChevronDown, ChevronRight, MapPin } from "lucide-react";
import type { ExecutionDifference } from "@/types/comparison";

interface ExecutionStepCardProps {
  stepNum: string;
  diffs: ExecutionDifference[];
}

function CodeComparison({
  leftLabel,
  leftText,
  rightLabel,
  rightText,
}: {
  leftLabel: string;
  leftText: string;
  rightLabel: string;
  rightText: string;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div className="space-y-1.5">
        <p className="text-xs font-semibold text-muted-foreground">{leftLabel}</p>
        <pre className="code-block">{leftText}</pre>
      </div>
      <div className="space-y-1.5">
        <p className="text-xs font-semibold text-muted-foreground">{rightLabel}</p>
        <pre className="code-block">{rightText}</pre>
      </div>
    </div>
  );
}

export default function ExecutionStepCard({ stepNum, diffs }: ExecutionStepCardProps) {
  const [open, setOpen] = useState(true);

  const realIssues = diffs.filter((d) => d.type !== "expected_with_dynamic_data");
  const runtimeDiffs = diffs.filter((d) => d.type === "expected_with_dynamic_data");

  if (!realIssues.length && !runtimeDiffs.length) return null;

  const title =
    realIssues.length > 0
      ? `Execution Step ${stepNum} — ${realIssues.length} issue(s)`
      : `Execution Step ${stepNum} — validated with runtime data`;

  return (
    <div className="glass-card overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted/30 transition-colors"
      >
        {open ? (
          <ChevronDown className="w-4 h-4 text-muted-foreground flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-muted-foreground flex-shrink-0" />
        )}
        <MapPin className="w-3.5 h-3.5 text-pink-400 flex-shrink-0" />
        <span className="text-sm font-medium text-foreground">{title}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-border">
          {/* Real issues */}
          {realIssues.map((diff, i) => (
            <div key={i} className="pt-4 space-y-3">
              {diff.type === "missing" && (
                <div className="diff-red rounded-md px-4 py-2.5 text-sm text-red-300">
                  ⚠ {diff.message}
                </div>
              )}

              {diff.type === "procedure_mismatch" && (
                <div className="space-y-3">
                  <div className="diff-red rounded-md px-4 py-2 text-sm font-semibold text-red-300">
                    ✗ Procedure Mismatch
                  </div>
                  <CodeComparison
                    leftLabel="Client Procedure"
                    leftText={diff.client ?? ""}
                    rightLabel="Executed Procedure"
                    rightText={diff.executed ?? ""}
                  />
                </div>
              )}

              {diff.type === "expected_mismatch" && (
                <div className="space-y-3">
                  <div className="diff-yellow rounded-md px-4 py-2 text-sm font-semibold text-yellow-300">
                    ⚠ Expected Results Mismatch
                  </div>
                  <CodeComparison
                    leftLabel="Client Expected"
                    leftText={diff.client ?? ""}
                    rightLabel="Executed Expected"
                    rightText={diff.executed ?? ""}
                  />
                </div>
              )}

              {diff.type === "expected_vs_actual_mismatch" && (
                <div className="space-y-3">
                  <div className="diff-red rounded-md px-4 py-2 text-sm font-semibold text-red-300">
                    ✗ Expected vs Actual Mismatch
                  </div>
                  <CodeComparison
                    leftLabel="Client Expected"
                    leftText={diff.client_expected ?? ""}
                    rightLabel="Executed Actual"
                    rightText={diff.executed_actual ?? ""}
                  />
                </div>
              )}

              {i < realIssues.length - 1 && <div className="border-t border-border" />}
            </div>
          ))}

          {/* Runtime diffs */}
          {runtimeDiffs.map((diff, i) => (
            <div key={i} className="pt-4 space-y-3">
              <div className="diff-green rounded-md px-4 py-2.5 text-sm font-semibold text-green-300">
                ✓ Expected result met with runtime-generated data
              </div>
              <CodeComparison
                leftLabel="Client Expected"
                leftText={diff.expected ?? ""}
                rightLabel="Executed Actual"
                rightText={diff.actual ?? ""}
              />
              {diff.dynamic_data && Object.keys(diff.dynamic_data).length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold text-muted-foreground">📌 Generated Values</p>
                  {Object.entries(diff.dynamic_data).map(([k, v]) => (
                    <pre key={k} className="code-block">{`${k}: ${v}`}</pre>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
