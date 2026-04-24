import { useState } from "react";
import { Loader2, AlertCircle, CheckCircle2, Zap, Wrench, Search, FileText, Camera } from "lucide-react";
import FileUploadZone from "./FileUploadZone";
import TestScriptInfo from "./TestScriptInfo";
import SetupStepCard from "./SetupStepCard";
import ExecutionStepCard from "./ExecutionStepCard";
import PdfSideBySideViewer from "./PdfSideBySideViewer";
import PdfScreenshotsViewer from "./PdfScreenshotsViewer";
import ValidationNotepad from "./ValidationNotepad";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { getStoredToken } from "./AuthContext";
import type { ComparisonResult } from "@/types/comparison";

const API_BASE = "";

export default function PdfValidationPanel() {
  const [clientPdf, setClientPdf] = useState<File | null>(null);
  const [outputPdf, setOutputPdf] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ComparisonResult | null>(null);

  const handleCompare = async () => {
    if (!clientPdf || !outputPdf) { setError("Please upload both PDF files before comparing."); return; }
    setError(null); setResult(null); setLoading(true);
    try {
      const form = new FormData();
      form.append("client_pdf", clientPdf);
      form.append("output_pdf", outputPdf);
      const token = getStoredToken();
      const res = await fetch(`${API_BASE}/compare`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      setResult(await res.json());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Comparison failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h2 className="text-xl font-bold text-foreground">PDF Validation</h2>
          <p className="text-sm text-muted-foreground mt-0.5">
            Client Test Script vs V-Assure Output — cosmetic & structural comparison
          </p>
        </div>

        {/* Upload */}
        <div className="glass-card p-6 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <FileUploadZone label="Upload Client Test Script (PDF)" file={clientPdf} onFile={setClientPdf} />
            <FileUploadZone label="Upload V-Assure Output (PDF)" file={outputPdf} onFile={setOutputPdf} />
          </div>
          {error && (
            <div className="flex items-start gap-3 diff-red rounded-md px-4 py-3 text-sm text-red-300">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />{error}
            </div>
          )}
          <button
            onClick={handleCompare}
            disabled={loading || !clientPdf || !outputPdf}
            className="flex items-center gap-2 px-6 py-2.5 bg-primary text-primary-foreground rounded-md text-sm font-semibold hover:bg-primary/90 transition-all disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]"
          >
            {loading
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Comparing…</>
              : <><Search className="w-4 h-4" /> Compare PDFs</>}
          </button>
        </div>

        {/* Results */}
        {result && (
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
            <Tabs defaultValue="analysis">
              <TabsList className="mb-4">
                <TabsTrigger value="analysis" className="flex items-center gap-2">
                  <Search className="w-3.5 h-3.5" /> Analysis
                </TabsTrigger>
                <TabsTrigger value="sidebyside" className="flex items-center gap-2">
                  <FileText className="w-3.5 h-3.5" /> Side-by-Side PDF
                </TabsTrigger>
                <TabsTrigger value="screenshots" className="flex items-center gap-2">
                  <Camera className="w-3.5 h-3.5" /> Screenshots
                </TabsTrigger>
              </TabsList>

              {/* ── Analysis ── */}
              <TabsContent value="analysis" className="space-y-6">
                <TestScriptInfo
                  clientMeta={result.client_metadata}
                  executedMeta={result.executed_metadata}
                  statistics={result.statistics}
                />
                <div className="border-t border-border" />

                <section className="space-y-4">
                  <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
                    <Search className="w-5 h-5 text-primary" /> Comparison Results
                  </h2>
                  {!result.has_differences ? (
                    <div className="diff-green rounded-lg px-5 py-4 flex items-center gap-3">
                      <CheckCircle2 className="w-5 h-5 text-green-400 flex-shrink-0" />
                      <p className="text-sm font-semibold text-green-300">No differences found. Validation passed.</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div className="diff-red rounded-lg px-5 py-4 flex items-center gap-3">
                        <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                        <p className="text-sm font-semibold text-red-300">Found {result.summary.total_issues} issue(s)</p>
                      </div>
                      <div className="grid grid-cols-3 gap-3">
                        {[
                          { label: "Total Issues", value: result.summary.total_issues },
                          { label: "Setup Steps", value: result.summary.setup_steps_with_issues },
                          { label: "Execution Steps", value: result.summary.execution_steps_with_issues },
                        ].map(({ label, value }) => (
                          <div key={label} className="glass-card p-4 text-center">
                            <p className="text-3xl font-bold text-foreground">{value}</p>
                            <p className="text-xs text-muted-foreground mt-1">{label}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </section>

                {result.setup_differences && Object.keys(result.setup_differences).length > 0 && (
                  <section className="space-y-3">
                    <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                      <Wrench className="w-4 h-4 text-primary" /> Setup Steps Differences
                    </h3>
                    {Object.keys(result.setup_differences).sort((a, b) => parseInt(a) - parseInt(b)).map(step => (
                      <SetupStepCard key={step} stepNum={step} diffs={result.setup_differences[step]} />
                    ))}
                  </section>
                )}

                {result.execution_differences && Object.keys(result.execution_differences).length > 0 && (
                  <section className="space-y-3">
                    <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                      <Zap className="w-4 h-4 text-primary" /> Execution Steps Differences
                    </h3>
                    {Object.keys(result.execution_differences).sort((a, b) => parseInt(a) - parseInt(b)).map(step => (
                      <ExecutionStepCard key={step} stepNum={step} diffs={result.execution_differences[step]} />
                    ))}
                  </section>
                )}
              </TabsContent>

              {/* ── Side-by-Side ── */}
              <TabsContent value="sidebyside">
                <div className="glass-card overflow-hidden" style={{ height: 800 }}>
                  <PdfSideBySideViewer clientPdf={clientPdf!} outputPdf={outputPdf!} result={result} />
                </div>
              </TabsContent>

              {/* ── Screenshots ── */}
              <TabsContent value="screenshots">
                <div className="glass-card overflow-hidden">
                  <PdfScreenshotsViewer
                    clientPdf={clientPdf!}
                    outputPdf={outputPdf!}
                    result={result}
                  />
                </div>
              </TabsContent>
            </Tabs>
          </div>
        )}
      </div>

      {/* Floating notepad widget — always present once files are uploaded */}
      {(clientPdf || outputPdf || result) && (
        <ValidationNotepad scriptId={result?.client_metadata?.script_id ?? "Validation"} />
      )}
    </>
  );
}
