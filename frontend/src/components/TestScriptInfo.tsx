import { Clock, Hash, FileText, CheckSquare } from "lucide-react";
import type { ClientMetadata, ExecutedMetadata, Statistics } from "@/types/comparison";

interface MetricCardProps {
  label: string;
  value: number | string;
  small?: boolean;
}

function MetricCard({ label, value, small }: MetricCardProps) {
  return (
    <div className="glass-card p-4 text-center">
      <p className={`font-bold text-foreground ${small ? "text-2xl" : "text-3xl"}`}>{value}</p>
      <p className="text-xs text-muted-foreground mt-1">{label}</p>
    </div>
  );
}

interface InfoRowProps {
  label: string;
  value: string;
  highlight?: boolean;
}

function InfoRow({ label, value, highlight }: InfoRowProps) {
  return (
    <div className="flex flex-wrap gap-1 text-sm">
      <span className="font-semibold text-foreground">{label}:</span>
      <span className={highlight ? "font-mono text-primary text-xs bg-primary/10 px-1.5 py-0.5 rounded" : "text-muted-foreground"}>
        {value}
      </span>
    </div>
  );
}

interface TestScriptInfoProps {
  clientMeta: ClientMetadata;
  executedMeta: ExecutedMetadata;
  statistics: Statistics;
}

export default function TestScriptInfo({ clientMeta, executedMeta, statistics }: TestScriptInfoProps) {
  const cs = statistics.client;
  const es = statistics.executed;

  return (
    <section className="space-y-4">
      <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
        <FileText className="w-5 h-5 text-primary" />
        Test Script Information
      </h2>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Template */}
        <div className="glass-card p-5 space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-border">
            <FileText className="w-4 h-4 text-muted-foreground" />
            <h3 className="font-semibold text-foreground">Template</h3>
          </div>
          <div className="space-y-2.5">
            <InfoRow label="Script ID" value={clientMeta.script_id || "N/A"} highlight />
            <InfoRow label="Title" value={clientMeta.title || "N/A"} />
            <InfoRow label="Description" value={clientMeta.description || "N/A"} />
            {clientMeta.run_number && (
              <InfoRow label="Run Number" value={String(clientMeta.run_number)} />
            )}
          </div>
          {cs && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Step Counts</p>
              <div className="grid grid-cols-3 gap-2">
                <MetricCard label="Total" value={cs.total_steps} />
                <MetricCard label="Setup" value={cs.setup_steps ?? 0} small />
                <MetricCard label="Execution" value={cs.execution_steps ?? 0} small />
              </div>
            </div>
          )}
        </div>

        {/* Executed Script */}
        <div className="glass-card p-5 space-y-4">
          <div className="flex items-center gap-2 pb-3 border-b border-border">
            <CheckSquare className="w-4 h-4 text-green-400" />
            <h3 className="font-semibold text-foreground">V-Assure Report</h3>
          </div>
          <div className="space-y-2.5">
            <InfoRow label="Script ID" value={executedMeta.script_id || "N/A"} highlight />
            <InfoRow label="Title" value={executedMeta.title || "N/A"} />
            <InfoRow label="Description" value={executedMeta.description || "N/A"} />
            {executedMeta.start_time && <InfoRow label="Start Time" value={executedMeta.start_time} />}
            {executedMeta.end_time && <InfoRow label="End Time" value={executedMeta.end_time} />}
            {executedMeta.script_run_time && (
              <div className="flex items-center gap-2 text-sm">
                <Clock className="w-3.5 h-3.5 text-muted-foreground" />
                <span className="font-semibold text-foreground">Run Time:</span>
                <span className="font-mono text-primary text-xs bg-primary/10 px-1.5 py-0.5 rounded">
                  {executedMeta.script_run_time}
                </span>
              </div>
            )}
          </div>
          {es && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Step Counts</p>
              <div className="grid grid-cols-3 gap-2">
                <MetricCard label="Total" value={es.total_steps} />
                <MetricCard label="Pre-Test Setup" value={es.pre_test_setup_steps ?? 0} small />
                <MetricCard label="Execution" value={es.execution_steps ?? 0} small />
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
