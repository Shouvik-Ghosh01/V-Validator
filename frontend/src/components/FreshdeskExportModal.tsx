import { useState } from "react";
import { X, Search, Send, CheckCircle, AlertCircle, Loader2, Ticket } from "lucide-react";
import { getStoredToken } from "./AuthContext";

type NoteTag = "text_incorrect" | "screenshot_incorrect" | "step_incorrect" | "other";

interface NoteEntry {
  id: string;
  imageDataUrl: string | null;
  comment: string;
  tag: NoteTag;
  stepRef: string;
  timestamp: string;
}

interface TicketResult {
  ticket_id: number;
  subject: string;
  assignee_name: string | null;
  total_results: number;
}

type Phase = "input" | "found" | "sending" | "done" | "error";

interface Props {
  notes: NoteEntry[];
  scriptId: string;
  onClose: () => void;
}

const OVERLAY: React.CSSProperties = {
  position: "fixed", inset: 0, zIndex: 99999,
  background: "rgba(0,0,0,0.55)", backdropFilter: "blur(2px)",
  display: "flex", alignItems: "center", justifyContent: "center",
};

const MODAL: React.CSSProperties = {
  background: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: 14,
  boxShadow: "0 20px 60px rgba(0,0,0,0.3)",
  width: "min(480px, 96vw)",
  display: "flex", flexDirection: "column",
  animation: "fd-pop 0.2s cubic-bezier(0.16,1,0.3,1)",
};

const INPUT_STYLE: React.CSSProperties = {
  width: "100%", padding: "8px 10px", borderRadius: 6,
  border: "1px solid hsl(var(--border))",
  background: "hsl(var(--muted))",
  color: "hsl(var(--foreground))",
  fontSize: 13, boxSizing: "border-box",
};

function Btn({
  children, onClick, disabled, variant = "default", style,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "default" | "primary" | "ghost";
  style?: React.CSSProperties;
}) {
  const base: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: 6,
    padding: "8px 16px", borderRadius: 7, border: "none",
    cursor: disabled ? "not-allowed" : "pointer",
    fontSize: 13, fontWeight: 600, transition: "opacity 0.15s",
    opacity: disabled ? 0.5 : 1,
  };
  const variants = {
    default: { background: "hsl(var(--secondary))", color: "hsl(var(--foreground))" },
    primary: { background: "#F5A623", color: "#fff" },
    ghost:   { background: "transparent", color: "hsl(var(--muted-foreground))", border: "1px solid hsl(var(--border))" },
  };
  return (
    <button style={{ ...base, ...variants[variant], ...style }} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

export default function FreshdeskExportModal({ notes, scriptId, onClose }: Props) {
  // Pre-fill script ID from prop; user supplies the release number
  const [release, setRelease] = useState("");
  const [scriptIdInput, setScriptIdInput] = useState(scriptId !== "Validation" ? scriptId : "");
  const [phase, setPhase] = useState<Phase>("input");
  const [ticket, setTicket] = useState<TicketResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const withScreenshots = notes.filter(n => n.imageDataUrl).length;

  async function findTicket() {
    if (!release.trim() || !scriptIdInput.trim()) return;
    setPhase("input"); // keep form visible while searching
    setErrorMsg(null);
    setTicket(null);

    try {
      const token = getStoredToken();
      const params = new URLSearchParams({ release: release.trim(), script_id: scriptIdInput.trim() });
      const res = await fetch(`/freshdesk/search?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail ?? "Search failed");
      setTicket(json as TicketResult);
      setPhase("found");
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : String(e));
      setPhase("error");
    }
  }

  async function sendToFreshdesk() {
    if (!ticket) return;
    setPhase("sending");
    try {
      const token = getStoredToken();
      const res = await fetch("/freshdesk/post-reply", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          ticket_id: ticket.ticket_id,
          notes,
          script_id: scriptIdInput.trim(),
          release: release.trim(),
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.detail ?? "Post failed");
      setPhase("done");
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : String(e));
      setPhase("error");
    }
  }

  return (
    <>
      <style>{`
        @keyframes fd-pop {
          from { opacity: 0; transform: scale(0.92) translateY(10px); }
          to   { opacity: 1; transform: scale(1) translateY(0); }
        }
      `}</style>

      <div style={OVERLAY} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
        <div style={MODAL}>

          {/* Header */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 18px", borderBottom: "1px solid hsl(var(--border))", flexShrink: 0 }}>
            <Ticket size={16} style={{ color: "#F5A623" }} />
            <span style={{ fontWeight: 700, fontSize: 14, flex: 1, color: "hsl(var(--foreground))" }}>
              Export to Freshdesk
            </span>
            <button onClick={onClose} style={{ padding: 4, background: "none", border: "none", cursor: "pointer", color: "hsl(var(--muted-foreground))", display: "flex" }}>
              <X size={16} />
            </button>
          </div>

          {/* Body */}
          <div style={{ padding: "18px 18px 14px", display: "flex", flexDirection: "column", gap: 16 }}>

            {/* ── Phase: input / error / found ── */}
            {(phase === "input" || phase === "error" || phase === "found") && (
              <>
                {/* Notes summary pill */}
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 20, background: "rgba(245,166,35,0.12)", color: "#F5A623", border: "1px solid rgba(245,166,35,0.3)" }}>
                    {notes.length} note{notes.length !== 1 ? "s" : ""}
                  </span>
                  {withScreenshots > 0 && (
                    <span style={{ fontSize: 11, fontWeight: 600, padding: "3px 10px", borderRadius: 20, background: "rgba(99,102,241,0.1)", color: "#818cf8", border: "1px solid rgba(99,102,241,0.25)" }}>
                      {withScreenshots} screenshot{withScreenshots !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>

                {/* Step 1: ticket lookup */}
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <label style={{ fontSize: 11, fontWeight: 600, color: "hsl(var(--muted-foreground))", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    Step 1 — Find Ticket
                  </label>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 8 }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <span style={{ fontSize: 11, color: "hsl(var(--muted-foreground))" }}>Release</span>
                      <input
                        style={INPUT_STYLE}
                        placeholder="e.g. 26R1"
                        value={release}
                        onChange={e => { setRelease(e.target.value); setPhase("input"); setTicket(null); }}
                        onKeyDown={e => e.key === "Enter" && findTicket()}
                      />
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <span style={{ fontSize: 11, color: "hsl(var(--muted-foreground))" }}>Script ID</span>
                      <input
                        style={INPUT_STYLE}
                        placeholder="e.g. BASICS-PQ-LIMS-10"
                        value={scriptIdInput}
                        onChange={e => { setScriptIdInput(e.target.value); setPhase("input"); setTicket(null); }}
                        onKeyDown={e => e.key === "Enter" && findTicket()}
                      />
                    </div>
                  </div>
                  <Btn
                    variant="default"
                    style={{ alignSelf: "flex-end", marginTop: 4 }}
                    onClick={findTicket}
                    disabled={!release.trim() || !scriptIdInput.trim()}
                  >
                    <Search size={13} /> Find Ticket
                  </Btn>
                </div>

                {/* Error banner */}
                {phase === "error" && errorMsg && (
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 8, padding: "10px 12px", borderRadius: 8, background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)", color: "#ef4444", fontSize: 12 }}>
                    <AlertCircle size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                    <span>{errorMsg}</span>
                  </div>
                )}

                {/* Ticket preview */}
                {phase === "found" && ticket && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 2, padding: "12px 14px", borderRadius: 9, background: "rgba(34,197,94,0.06)", border: "1px solid rgba(34,197,94,0.25)" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                        <CheckCircle size={14} style={{ color: "#22c55e", flexShrink: 0 }} />
                        <span style={{ fontSize: 11, fontWeight: 700, color: "#22c55e" }}>Ticket found</span>
                      </div>
                      <span style={{ fontSize: 13, fontWeight: 600, color: "hsl(var(--foreground))" }}>
                        #{ticket.ticket_id} — {ticket.subject}
                      </span>
                      {ticket.assignee_name && (
                        <span style={{ fontSize: 11, color: "hsl(var(--muted-foreground))", marginTop: 2 }}>
                          Assignee: <b>{ticket.assignee_name}</b>
                          {ticket.assignee_name && (
                            <span style={{ marginLeft: 6, fontSize: 10, color: "#F5A623" }}>← will be notified</span>
                          )}
                        </span>
                      )}
                      {ticket.total_results > 1 && (
                        <span style={{ fontSize: 10, color: "hsl(var(--muted-foreground))", marginTop: 2 }}>
                          {ticket.total_results} tickets matched — using the most recent one.
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}

            {/* ── Phase: sending ── */}
            {phase === "sending" && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: "24px 0" }}>
                <Loader2 size={28} style={{ color: "#F5A623", animation: "spin 1s linear infinite" }} />
                <span style={{ fontSize: 13, color: "hsl(var(--muted-foreground))" }}>
                  Posting {notes.length} note{notes.length !== 1 ? "s" : ""} to Freshdesk…
                </span>
                <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
              </div>
            )}

            {/* ── Phase: done ── */}
            {phase === "done" && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: "24px 0" }}>
                <CheckCircle size={36} style={{ color: "#22c55e" }} />
                <span style={{ fontSize: 14, fontWeight: 700, color: "hsl(var(--foreground))" }}>
                  Posted successfully!
                </span>
                <span style={{ fontSize: 12, color: "hsl(var(--muted-foreground))", textAlign: "center" }}>
                  {notes.length} note{notes.length !== 1 ? "s" : ""} added as a private reply on ticket #{ticket?.ticket_id}.
                  {ticket?.assignee_name && ` ${ticket.assignee_name} has been notified.`}
                </span>
              </div>
            )}
          </div>

          {/* Footer */}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, padding: "12px 18px", borderTop: "1px solid hsl(var(--border))" }}>
            {phase === "done" ? (
              <Btn variant="primary" onClick={onClose}>Close</Btn>
            ) : phase === "sending" ? null : (
              <>
                <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
                {phase === "found" && ticket && (
                  <Btn variant="primary" onClick={sendToFreshdesk}>
                    <Send size={13} /> Send to Freshdesk
                  </Btn>
                )}
              </>
            )}
          </div>

        </div>
      </div>
    </>
  );
}
