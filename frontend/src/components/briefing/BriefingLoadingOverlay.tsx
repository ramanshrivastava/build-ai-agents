import { useState, useEffect } from "react";
import { m, AnimatePresence } from "motion/react";
import { Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

const STATUS_MESSAGES = [
  "Reviewing patient record...",
  "Analyzing medical history...",
  "Cross-referencing medications...",
  "Evaluating lab results...",
  "Checking drug interactions...",
  "Reviewing screening schedules...",
  "Identifying risk factors...",
  "Generating clinical flags...",
  "Prioritizing suggested actions...",
  "Composing summary...",
  "Finalizing briefing...",
] as const;

const MESSAGE_INTERVAL_MS = 3500;
const TICK_MS = 100;
const MAX_INDEX = STATUS_MESSAGES.length - 1;

interface BriefingLoadingOverlayProps {
  onCancel: () => void;
}

export function BriefingLoadingOverlay({ onCancel }: BriefingLoadingOverlayProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setElapsed((prev) => prev + TICK_MS), TICK_MS);
    return () => clearInterval(id);
  }, []);

  const messageIndex = Math.min(Math.floor(elapsed / MESSAGE_INTERVAL_MS), MAX_INDEX);
  const step = messageIndex + 1;

  return (
    <div className="flex flex-col items-center gap-6 py-12">
      <m.div
        animate={{ scale: [1, 1.15, 1] }}
        transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
      >
        <Sparkles className="size-8 text-primary" />
      </m.div>

      <div className="flex min-h-[3rem] flex-col items-center gap-2">
        <AnimatePresence mode="wait">
          <m.p
            key={messageIndex}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3 }}
            className="text-sm font-medium text-foreground"
          >
            {STATUS_MESSAGES[messageIndex]}
          </m.p>
        </AnimatePresence>
        <p className="text-xs text-muted-foreground">
          Step {step} of {STATUS_MESSAGES.length}
        </p>
      </div>

      <div className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <m.span
            key={i}
            className="size-1.5 rounded-full bg-primary"
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
          />
        ))}
      </div>

      <Button variant="ghost" size="sm" onClick={onCancel}>
        Cancel
      </Button>
    </div>
  );
}
