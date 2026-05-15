import { useState } from "react";
import { CheckCircle2, AlertCircle, BookOpen } from "lucide-react";
import type { ComparisonResult, GrammarError } from "@/types/comparison";

const ERROR_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  spelling:            { label: "Spelling",            color: "#f97316", bg: "rgba(249,115,22,0.12)"  },
  duplicate_word:      { label: "Duplicate Word",      color: "#eab308", bg: "rgba(234,179,8,0.12)"   },
  punctuation:         { label: "Punctuation",         color: "#a855f7", bg: "rgba(168,85,247,0.12)"  },
  tense_inconsistency: { label: "Tense Inconsistency", color: "#06b6d4", bg: "rgba(6,182,212,0.12)"  },
  sentence_fragment:   { label: "Sentence Fragment",   color: "#ec4899", bg: "rgba(236,72,153,0.12)" },
};

const SOURCE_CONFIG = {
  client:   { label: "Client Script",   dot: "#ef4444" },
  executed: { label: "V-Assure Output", dot: "#22c55e" },
};

interface Props {
  result: ComparisonResult;
}

export default function GrammarCheckerPanel({ result }: Props) {
  const [filterType, setFilterType]     = useState<string>("all");
  const [filterSource, setFilterSource] = useState<string>("all");

  const allErrors: GrammarError[] = [
    ...(result.grammar_errors?.client   ?? []),
    ...(result.grammar_errors?.executed ?? []),
  ];

  const countByType = allErrors.reduce<Record<string, number>>((acc, e) => {
    acc[e.error_type] = (acc[e.error_type] ?? 0) + 1;
    return acc;
  }, {});

  const activeTypes = Object.keys(ERROR_CONFIG).filter((t) => countByType[t]);

  const filtered = allErrors.filter((e) => {
    if (filterType   !== "all" && e.error_type !== filterType)  return false;
    if (filterSource !== "all" && e.source     !== filterSource) return false;
    return true;
  });

  // ── Empty state ──────────────────────────────────────────────────────────────
  if (allErrors.length === 0) {
    return (
      <div className="diff-green rounded-lg px-5 py-4 flex items-center gap-3">
        <CheckCircle2 className="w-5 h-5 text-green-400 flex-shrink-0" />
        <p className="text-sm font-semibold text-green-300">No grammar errors detected.</p>
      </div>
    );
  }

  // ── Pill button helper ───────────────────────────────────────────────────────
  const pill = (active: boolean) =>
    `px-3 py-1 rounded-full text-xs font-medium border transition-all ${
      active
        ? "bg-primary/20 border-primary text-primary"
        : "border-border text-muted-foreground hover:border-primary/50"
    }`;

  return (
    <div className="space-y-4">
      {/* Summary card */}
      <div className="glass-card p-4 space-y-3">
        <div className="flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-semibold text-foreground">
            {allErrors.length} grammar issue{allErrors.length !== 1 ? "s" : ""} detected
          </span>
        </div>

        <div className="flex flex-wrap gap-2">
          {activeTypes.map((type) => {
            const cfg = ERROR_CONFIG[type];
            return (
              <span
                key={type}
                style={{ background: cfg.bg, color: cfg.color, borderColor: cfg.color + "44" }}
                className="px-2.5 py-1 rounded-full text-xs font-semibold border"
              >
                {cfg.label}: {countByType[type]}
              </span>
            );
          })}
        </div>

        {/* Grid of source counts */}
        <div className="grid grid-cols-2 gap-3 pt-1">
          {(["client", "executed"] as const).map((src) => {
            const count = allErrors.filter((e) => e.source === src).length;
            const cfg   = SOURCE_CONFIG[src];
            return (
              <div key={src} className="glass-card p-3 flex items-center gap-2">
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: cfg.dot, flexShrink: 0 }} />
                <div>
                  <p className="text-xs text-muted-foreground">{cfg.label}</p>
                  <p className="text-lg font-bold text-foreground">{count}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-xs text-muted-foreground mr-1">Type:</span>
        <button className={pill(filterType === "all")} onClick={() => setFilterType("all")}>All</button>
        {activeTypes.map((t) => (
          <button key={t} className={pill(filterType === t)} onClick={() => setFilterType(t)}>
            {ERROR_CONFIG[t].label}
          </button>
        ))}

        <span className="w-px h-4 bg-border mx-1" />

        <span className="text-xs text-muted-foreground mr-1">Source:</span>
        {(["all", "client", "executed"] as const).map((s) => (
          <button key={s} className={pill(filterSource === s)} onClick={() => setFilterSource(s)}>
            {s === "all" ? "Both" : SOURCE_CONFIG[s].label}
          </button>
        ))}
      </div>

      {/* Error list */}
      <div className="space-y-2">
        {filtered.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">
            No errors match the selected filters.
          </p>
        ) : (
          filtered.map((err, i) => {
            const cfg    = ERROR_CONFIG[err.error_type] ?? { label: err.error_type, color: "#888", bg: "rgba(128,128,128,0.12)" };
            const srcCfg = SOURCE_CONFIG[err.source as keyof typeof SOURCE_CONFIG];

            return (
              <div key={i} className="glass-card p-4 space-y-2">
                {/* Badges row */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    style={{ background: cfg.bg, color: cfg.color, borderColor: cfg.color + "44" }}
                    className="px-2 py-0.5 rounded text-xs font-semibold border"
                  >
                    {cfg.label}
                  </span>
                  <span className="text-xs text-muted-foreground flex items-center gap-1">
                    <span
                      style={{ width: 6, height: 6, borderRadius: "50%", background: srcCfg?.dot, display: "inline-block" }}
                    />
                    {srcCfg?.label}
                    {err.step_number != null && ` · Step ${err.step_number}`}
                    {err.step_type && ` (${err.step_type})`}
                  </span>
                </div>

                {/* Message */}
                <p className="text-sm text-foreground">{err.message}</p>

                {/* Context snippet */}
                {err.context && (
                  <div className="bg-muted/30 border border-border rounded px-3 py-2 text-xs font-mono text-muted-foreground leading-relaxed">
                    {err.context}
                  </div>
                )}

                {/* Suggestion */}
                {err.suggestion && (
                  <p className="text-xs" style={{ color: "#60a5fa" }}>
                    <BookOpen className="w-3 h-3 inline mr-1 mb-0.5" />
                    {err.suggestion}
                  </p>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
