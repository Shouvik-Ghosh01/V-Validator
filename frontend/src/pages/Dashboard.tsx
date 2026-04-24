import { useTheme } from "@/components/ThemeProvider";
import { Sun, Moon, LogOut } from "lucide-react";
import PdfValidationPanel from "@/components/PdfValidationPanel";
import { VAssureLogo } from "@/components/VAssureLogo";

interface DashboardProps {
  onLogout: () => void;
}

export default function Dashboard({ onLogout }: DashboardProps) {
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="flex flex-col min-h-screen bg-background text-foreground">

      {/* Header */}
      <header className="h-14 border-b border-border flex items-center justify-between px-6 bg-card">

        {/* LEFT: Branding */}
        <div className="flex items-center gap-2">
          <VAssureLogo size={28} />
          <span className="text-sm font-semibold tracking-tight">
            V-Assure Validator
          </span>
        </div>

        {/* RIGHT: Controls */}
        <div className="flex items-center gap-2">

          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            className="w-9 h-9 flex items-center justify-center rounded-full 
              bg-muted border border-border hover:bg-accent transition-colors"
          >
            {theme === "dark" ? (
              <Sun className="w-4 h-4" />
            ) : (
              <Moon className="w-4 h-4" />
            )}
          </button>

          {/* Logout */}
          <button
            onClick={onLogout}
            className="w-9 h-9 flex items-center justify-center rounded-full 
              bg-muted border border-border hover:bg-accent transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>

        </div>
      </header>

      {/* Main */}
      <main className="flex-1 overflow-auto p-6">

        {/* Section Title */}
        <div className="mb-6">
          <h2 className="text-base font-semibold">PDF Comparison</h2>
          <p className="text-xs text-muted-foreground">
            Upload client and executed PDFs to validate and compare steps.
          </p>
        </div>

        {/* Card */}
        <div className="bg-card border border-border rounded-lg shadow-sm p-6">
          <PdfValidationPanel />
        </div>

      </main>
    </div>
  );
}