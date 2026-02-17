import { useState, useRef, useCallback, useEffect } from "react";
import { m, AnimatePresence } from "motion/react";
import { TestTube2, Pill, ClipboardCheck, Lightbulb, ChevronDown } from "lucide-react";
import type { Flag } from "@/types";
import { cn } from "@/lib/utils";
import { spring } from "@/lib/animation";

const severityStyles = {
  critical: "bg-flag-critical-bg border-flag-critical-border text-flag-critical",
  warning: "bg-flag-warning-bg border-flag-warning-border text-flag-warning",
  info: "bg-flag-info-bg border-flag-info-border text-flag-info",
} as const;

const categoryIcons = {
  labs: TestTube2,
  medications: Pill,
  screenings: ClipboardCheck,
  ai_insight: Lightbulb,
} as const;

interface FlagCardProps {
  flag: Flag;
}

export function FlagCard({ flag }: FlagCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const Icon = categoryIcons[flag.category];

  const toggle = useCallback(() => setIsExpanded((prev) => !prev), []);

  const handleHoverStart = useCallback(() => {
    hoverTimeoutRef.current = setTimeout(() => setIsExpanded(true), 300);
  }, []);

  const handleHoverEnd = useCallback(() => {
    if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    setIsExpanded(false);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggle();
      }
    },
    [toggle],
  );

  useEffect(() => {
    return () => {
      if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    };
  }, []);

  return (
    <m.div
      layout="position"
      role="button"
      tabIndex={0}
      aria-expanded={isExpanded}
      onClick={toggle}
      onHoverStart={handleHoverStart}
      onHoverEnd={handleHoverEnd}
      onFocus={() => setIsExpanded(true)}
      onBlur={() => setIsExpanded(false)}
      onKeyDown={handleKeyDown}
      className={cn(
        "cursor-pointer rounded-lg border p-3",
        severityStyles[flag.severity],
      )}
    >
      <div className="flex items-center gap-2">
        <Icon className="size-4 shrink-0" />
        <p className="flex-1 text-sm font-semibold uppercase">
          {flag.severity}: {flag.title}
        </p>
        <m.div
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={spring.snappy}
        >
          <ChevronDown className="size-4" />
        </m.div>
      </div>

      <AnimatePresence initial={false}>
        {isExpanded && (
          <m.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={spring.snappy}
            className="overflow-hidden"
          >
            <div className="mt-2 space-y-1">
              <p className="text-sm opacity-90">{flag.description}</p>
              {flag.suggested_action && (
                <p className="text-sm font-medium opacity-80">
                  Action: {flag.suggested_action}
                </p>
              )}
              <span className="inline-block rounded-full bg-white/10 px-2 py-0.5 text-xs uppercase">
                {flag.category.replace("_", " ")}
              </span>
            </div>
          </m.div>
        )}
      </AnimatePresence>
    </m.div>
  );
}
