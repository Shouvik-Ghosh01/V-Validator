import { LogOut } from "lucide-react";
import PdfValidationPanel from "@/components/PdfValidationPanel";

interface DashboardProps {
  onLogout: () => void;
}

export default function Dashboard({ onLogout }: DashboardProps) {
  return (
    <div className="flex flex-col min-h-screen bg-background">
      <header className="h-14 border-b border-border flex items-center justify-between px-6 bg-card flex-shrink-0">
        <h1 className="text-sm font-semibold text-foreground">
          Spotline Internal Platform
        </h1>
        <button
          onClick={onLogout}
          className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <LogOut className="w-3.5 h-3.5" />
          Sign out
        </button>
      </header>
      <main className="flex-1 overflow-auto p-6">
        <PdfValidationPanel />
      </main>
    </div>
  );
}
