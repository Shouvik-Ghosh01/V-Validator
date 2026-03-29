import { MessageSquare } from "lucide-react";

export default function KnowledgeAssistantPanel() {
  return (
    <div className="flex flex-col items-center justify-center h-full py-24 space-y-4">
      <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center">
        <MessageSquare className="w-8 h-8 text-primary" />
      </div>
      <h2 className="text-xl font-bold text-foreground">Knowledge Assistant</h2>
      <p className="text-sm text-muted-foreground text-center max-w-sm">
        The Knowledge Assistant (RAG) module is coming soon. Use PDF Validation mode to get started.
      </p>
    </div>
  );
}
