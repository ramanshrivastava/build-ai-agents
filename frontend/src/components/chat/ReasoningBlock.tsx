import { useEffect, useState } from "react";
import { Brain, ChevronDown, ChevronRight } from "lucide-react";

interface ReasoningBlockProps {
  text: string;
  streaming: boolean;
}

/**
 * Collapsible reasoning trace: auto-expands while the model is thinking,
 * auto-collapses into a quiet "Thought process" row when it moves on.
 */
export function ReasoningBlock({ text, streaming }: ReasoningBlockProps) {
  const [expanded, setExpanded] = useState(streaming);

  useEffect(() => {
    if (!streaming) setExpanded(false);
  }, [streaming]);

  return (
    <div
      className={`my-2 rounded-md border transition-colors ${
        streaming
          ? "border-amber-500/20 bg-gradient-to-r from-amber-500/[0.05] to-transparent"
          : "border-border/60 bg-background/40"
      }`}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-foreground/[0.02]"
      >
        <Brain
          className={`size-3 ${streaming ? "animate-pulse text-amber-500" : "text-muted-foreground"}`}
          style={streaming ? { animationDuration: "1.6s" } : undefined}
        />
        <span
          className={`text-[11px] font-medium uppercase tracking-wider ${
            streaming ? "animate-pulse text-amber-500" : "text-muted-foreground"
          }`}
          style={streaming ? { animationDuration: "1.6s" } : undefined}
        >
          {streaming ? "Thinking" : "Thought process"}
        </span>
        <span className="ml-auto text-muted-foreground">
          {expanded ? (
            <ChevronDown className="size-3" />
          ) : (
            <ChevronRight className="size-3" />
          )}
        </span>
      </button>
      {expanded && (
        <div className="whitespace-pre-wrap border-t border-border/40 px-3 pb-2 pt-1 text-xs italic leading-relaxed text-muted-foreground">
          {text}
          {streaming && (
            <span
              className="ml-0.5 inline-block h-3 w-[2px] animate-pulse bg-amber-500 align-middle"
              style={{ animationDuration: "1.1s" }}
            />
          )}
        </div>
      )}
    </div>
  );
}
