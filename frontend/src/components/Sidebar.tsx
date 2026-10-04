import { FileText, Brain, ChevronRight } from "lucide-react";

type Mode = "knowledge" | "pdf";

interface SidebarProps {
  mode: Mode;
  onModeChange: (m: Mode) => void;
}

export default function Sidebar({ mode, onModeChange }: SidebarProps) {
  const items = [
    { id: "pdf" as Mode, label: "PDF Validation", icon: FileText, desc: "Client vs V-Assure" },
    { id: "knowledge" as Mode, label: "Knowledge Assistant", icon: Brain, desc: "RAG Q&A" },
  ];

  return (
    <aside className="w-64 min-h-screen bg-sidebar border-r border-sidebar-border flex flex-col">
      {/* Brand */}
      <div className="px-5 py-5 border-b border-sidebar-border">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center">
            <FileText className="w-4 h-4 text-primary" />
          </div>
          <div>
            <p className="text-xs font-bold text-foreground leading-tight">Spotline</p>
            <p className="text-xs text-muted-foreground leading-tight">Internal Platform</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        <p className="px-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
          Modules
        </p>
        {items.map(({ id, label, icon: Icon, desc }) => {
          const active = mode === id;
          return (
            <button
              key={id}
              onClick={() => onModeChange(id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all group ${
                active
                  ? "bg-primary/15 text-foreground border border-primary/25"
                  : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              }`}
            >
              <Icon className={`w-4 h-4 flex-shrink-0 ${active ? "text-primary" : ""}`} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{label}</p>
                <p className={`text-xs truncate ${active ? "text-muted-foreground" : "text-muted-foreground/70"}`}>
                  {desc}
                </p>
              </div>
              {active && <ChevronRight className="w-3 h-3 text-primary flex-shrink-0" />}
            </button>
          );
        })}
      </nav>

      <div className="px-5 py-4 border-t border-sidebar-border">
        <p className="text-xs text-muted-foreground">v1.0.0 · Confidential</p>
      </div>
    </aside>
  );
}
