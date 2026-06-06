import { m } from "motion/react";
import { Cloud, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BriefingLoadingOverlay } from "@/components/briefing/BriefingLoadingOverlay";
import type { BriefingRuntime } from "@/types";

interface GenerateButtonProps {
  onGenerate: (runtime: BriefingRuntime) => void;
  isLoading: boolean;
  pendingRuntime: BriefingRuntime | null;
  error: Error | null;
  onCancel: () => void;
}

export function GenerateButton({
  onGenerate,
  isLoading,
  pendingRuntime,
  error,
  onCancel,
}: GenerateButtonProps) {
  if (isLoading) {
    return <BriefingLoadingOverlay onCancel={onCancel} />;
  }

  return (
    <div className="flex flex-col items-center gap-3 py-8">
      <div className="flex flex-wrap items-center justify-center gap-2">
        <m.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
          <Button
            onClick={() => onGenerate("sdk")}
            className="shadow-lg shadow-primary/20"
            aria-label="Generate Briefing"
          >
            <Sparkles />
            {error && pendingRuntime === "sdk" ? "Retry Agent SDK" : "Generate with Agent SDK"}
          </Button>
        </m.div>
        <m.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
          <Button variant="outline" onClick={() => onGenerate("managed")}>
            <Cloud />
            {error && pendingRuntime === "managed"
              ? "Retry Managed Agents"
              : "Generate with Managed Agents"}
          </Button>
        </m.div>
      </div>
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
