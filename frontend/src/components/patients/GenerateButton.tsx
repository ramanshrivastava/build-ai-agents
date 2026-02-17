import { m } from "motion/react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BriefingLoadingOverlay } from "@/components/briefing/BriefingLoadingOverlay";

interface GenerateButtonProps {
  onGenerate: () => void;
  isLoading: boolean;
  error: Error | null;
  onCancel: () => void;
}

export function GenerateButton({ onGenerate, isLoading, error, onCancel }: GenerateButtonProps) {
  if (isLoading) {
    return <BriefingLoadingOverlay onCancel={onCancel} />;
  }

  return (
    <div className="flex flex-col items-center gap-3 py-8">
      <m.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
        <Button onClick={onGenerate} className="shadow-lg shadow-primary/20">
          <Sparkles />
          {error ? "Retry" : "Generate Briefing"}
        </Button>
      </m.div>
      {error && (
        <p className="text-sm text-destructive">
          {error.name === "AbortError"
            ? "Request timed out. The AI may need more time — please retry."
            : error.message || "Failed to generate briefing"}
        </p>
      )}
    </div>
  );
}
