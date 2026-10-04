import { useState } from "react";
import { ChevronDown, ChevronRight, MapPin } from "lucide-react";
import type { SetupDifference } from "@/types/comparison";
import { DiffText } from "@/components/DiffText";

interface SetupStepCardProps {
  stepNum: string;
  diffs: SetupDifference[];
}

function CodeComparison({
  clientText,
  executedText,
}: {
  clientText: string;
  executedText: string;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div className="space-y-1.5">
        <p className="text-xs font-semibold text-muted-foreground">
          Client Procedure
        </p>
        <pre className="code-block whitespace-pre-wrap">
          <DiffText
            expected={clientText}
            actual={executedText}
            side="left"
          />
        </pre>
      </div>

      <div className="space-y-1.5">
        <p className="text-xs font-semibold text-muted-foreground">
          Executed Procedure
        </p>
        <pre className="code-block whitespace-pre-wrap">
          <DiffText
            expected={clientText}
            actual={executedText}
            side="right"
          />
        </pre>
      </div>
    </div>
  );
}

export default function SetupStepCard({
  stepNum,
  diffs,
}: SetupStepCardProps) {
  const [open, setOpen] = useState(true);

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

        <span className="text-sm font-medium text-foreground">
          Setup Step {stepNum}
        </span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-border">
          {diffs.map((d, i) => (
            <div key={i} className="pt-4 space-y-3">

              {/* SUCCESS CASE */}
              {d.type === "ensure_accounts_with_dynamic_data" && (
                <div className="space-y-2">
                  <div className="diff-green rounded-md px-4 py-2.5 text-sm font-semibold text-green-300">
                    ✓ Account validated with runtime-generated data
                  </div>

                  {d.accounts &&
                    Object.entries(d.accounts).map(([role, email]) => (
                      <pre key={role} className="code-block">
                        {`${role} → ${email}`}
                      </pre>
                    ))}
                </div>
              )}

              {/* MISSING STEP */}
              {d.type === "missing" && (
                <div className="diff-red rounded-md px-4 py-2.5 text-sm text-red-300">
                  ✗ {d.message}
                </div>
              )}

              {/* ACCOUNT MISSING */}
              {d.type === "account_missing" && (
                <div className="space-y-3">
                  <div className="diff-red rounded-md px-4 py-2 text-sm font-semibold text-red-300">
                    Account Missing
                  </div>
              
                  {d.missing_accounts &&
                    d.missing_accounts.length > 0 && (
                      <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3">
                        <p className="text-sm font-medium text-red-300 mb-2">
                          Missing Accounts
                        </p>
                    
                        <ul className="list-disc ml-5 text-sm text-red-200 space-y-1">
                          {d.missing_accounts.map((role, idx) => (
                            <li key={idx}>{role}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                  <CodeComparison
                    clientText={d.client ?? ""}
                    executedText={d.executed ?? ""}
                  />
                </div>
              )}

              {/* ACCOUNT DEFINITION MISMATCH */}
              {d.type === "account_definition_mismatch" && (
                <div className="space-y-3">
                  <div className="diff-amber rounded-md px-4 py-2 text-sm font-semibold text-amber-300">
                    Account Definition Mismatch
                  </div>
              
                  <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3">
                    <p className="text-sm text-amber-200">
                      Account exists in both documents, but the account details,
                      formatting, roles, permissions, or spacing differ from the template.
                    </p>
                  </div>
              
                  <CodeComparison
                    clientText={d.client ?? ""}
                    executedText={d.executed ?? ""}
                  />
                </div>
              )}

              {/* PROCEDURE MISMATCH */}
              {d.type === "procedure_mismatch" && (
                <div className="space-y-3">
                  <div className="diff-blue rounded-md px-4 py-2 text-sm font-semibold text-sky-300">
                    Procedure Mismatch
                  </div>

                  <CodeComparison
                    clientText={d.client ?? ""}
                    executedText={d.executed ?? ""}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}