import { useState, useCallback } from "react";
import { Upload, X, FileText, AlertCircle } from "lucide-react";

interface FileUploadZoneProps {
  label: string;
  file: File | null;
  onFile: (f: File | null) => void;
}

export default function FileUploadZone({ label, file, onFile }: FileUploadZoneProps) {
  const [dragging, setDragging] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files[0];
      if (f && f.type === "application/pdf") onFile(f);
    },
    [onFile]
  );

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) onFile(f);
  };

  return (
    <div className="space-y-2">
      <label className="text-sm font-semibold text-foreground">{label}</label>

      {file ? (
        <div className="glass-card p-4 flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary/15 flex items-center justify-center flex-shrink-0">
            <FileText className="w-5 h-5 text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-foreground truncate">{file.name}</p>
            <p className="text-xs text-muted-foreground">
              {(file.size / 1024 / 1024).toFixed(2)} MB · PDF
            </p>
          </div>
          <button
            onClick={() => onFile(null)}
            className="text-muted-foreground hover:text-foreground transition-colors flex-shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      ) : (
        <label
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={`flex flex-col items-center justify-center gap-3 p-8 rounded-lg border-2 border-dashed cursor-pointer transition-all ${
            dragging
              ? "border-primary bg-primary/10"
              : "border-border bg-muted/40 hover:border-primary/50 hover:bg-muted/60"
          }`}
        >
          <input type="file" accept=".pdf" onChange={handleChange} className="hidden" />
          <div className="w-12 h-12 rounded-xl bg-secondary flex items-center justify-center">
            <Upload className={`w-5 h-5 ${dragging ? "text-primary" : "text-muted-foreground"}`} />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-foreground">Drag and drop file here</p>
            <p className="text-xs text-muted-foreground mt-0.5">Limit 200MB per file · PDF</p>
          </div>
          <span className="px-4 py-1.5 rounded-md bg-secondary border border-border text-sm text-foreground hover:bg-secondary/80 transition-colors">
            Browse Files
          </span>
        </label>
      )}

      {file && file.size > 200 * 1024 * 1024 && (
        <div className="flex items-center gap-2 text-xs text-red-400">
          <AlertCircle className="w-3 h-3" />
          File exceeds 200MB limit
        </div>
      )}
    </div>
  );
}
