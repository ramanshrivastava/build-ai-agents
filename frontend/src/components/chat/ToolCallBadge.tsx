import { useState } from "react";
import {
  AlertCircle,
  BookOpenText,
  Check,
  ChevronDown,
  ChevronRight,
  FileCheck2,
  Globe,
  Terminal,
  Wand2,
  type LucideIcon,
} from "lucide-react";
import type { TracePart } from "@/types";

type ToolPart = Extract<TracePart, { type: "tool_use" }>;

interface ToolConfig {
  icon: LucideIcon;
  name: string;
  gerund: string;
  past: string;
  /** Short mono chip previewing the input (e.g. the search query). */
  inputPreview?: (input: Record<string, unknown>) => string | null;
}

const TOOL_CONFIG: Record<string, ToolConfig> = {
  search_clinical_guidelines: {
    icon: BookOpenText,
    name: "search_guidelines",
    gerund: "Searching clinical guidelines",
    past: "Searched clinical guidelines",
    inputPreview: (input) => (typeof input.query === "string" ? input.query : null),
  },
  publish_briefing: {
    icon: FileCheck2,
    name: "publish_briefing",
    gerund: "Publishing briefing",
    past: "Published briefing",
  },
  Skill: {
    icon: Wand2,
    name: "skill",
    gerund: "Running briefing skill",
    past: "Ran briefing skill",
    inputPreview: (input) =>
      typeof input.command === "string" ? input.command : null,
  },
  // Bash is only reachable through the web-research skill (firecrawl CLI),
  // so the web label is honest.
  Bash: {
    icon: Globe,
    name: "web_research",
    gerund: "Researching the web",
    past: "Researched the web",
    inputPreview: (input) =>
      typeof input.description === "string" && input.description
        ? input.description
        : typeof input.command === "string"
          ? input.command
          : null,
  },
};

const FALLBACK: ToolConfig = {
  icon: Terminal,
  name: "tool",
  gerund: "Calling",
  past: "Called",
};

interface ToolCallBadgeProps {
  part: ToolPart;
  /** True while the surrounding assistant turn is still streaming. */
  messageStreaming: boolean;
}

/**
 * A tool call as a status pill: amber throb while running, checkmark when
 * done, red on failure. Click to expand the full input and result preview.
 */
export function ToolCallBadge({ part, messageStreaming }: ToolCallBadgeProps) {
  const [expanded, setExpanded] = useState(false);

  const config = TOOL_CONFIG[part.tool] ?? { ...FALLBACK, name: part.tool };
  const Icon = config.icon;
  const hasError = part.result?.is_error === true;
  const isComplete = part.result != null && !hasError;
  const active = part.result == null && messageStreaming;

  const label = hasError
    ? `${config.name} failed`
    : isComplete
      ? config.past
      : active
        ? `${config.gerund}…`
        : config.past;
  const preview = config.inputPreview?.(part.input) ?? null;
  const hasDetails =
    Object.keys(part.input).length > 0 || Boolean(part.result?.content);

  return (
    <div className="my-2">
      <button
        type="button"
        onClick={() => hasDetails && setExpanded((v) => !v)}
        className={`inline-flex max-w-full items-center gap-2 rounded-full border px-3 py-1.5 text-left transition-colors ${
          hasError
            ? "border-destructive/30 bg-destructive/[0.04]"
            : isComplete
              ? "border-amber-500/20 bg-amber-500/[0.03]"
              : active
                ? "border-amber-500/30 bg-gradient-to-r from-amber-500/[0.06] to-transparent"
                : "border-border/60 bg-background/40"
        } ${hasDetails ? "cursor-pointer hover:bg-foreground/[0.02]" : "cursor-default"}`}
      >
        <span
          className={`flex size-4 shrink-0 items-center justify-center ${active ? "animate-pulse" : ""}`}
          style={active ? { animationDuration: "1.6s" } : undefined}
        >
          {hasError ? (
            <AlertCircle className="size-3.5 text-destructive" />
          ) : isComplete ? (
            <Check className="size-3.5 text-amber-500" />
          ) : (
            <Icon
              className={`size-3.5 ${active ? "text-amber-500" : "text-muted-foreground"}`}
            />
          )}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-wider text-amber-500">
          {config.name}
        </span>
        <span className="text-muted-foreground/50">·</span>
        <span
          className={`truncate text-xs text-foreground/80 ${active ? "animate-pulse" : ""}`}
          style={active ? { animationDuration: "1.6s" } : undefined}
        >
          {label}
        </span>
        {preview && (
          <span className="ml-1 max-w-[220px] truncate rounded bg-foreground/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            {preview}
          </span>
        )}
        {hasDetails && (
          <span className="text-muted-foreground">
            {expanded ? (
              <ChevronDown className="size-3" />
            ) : (
              <ChevronRight className="size-3" />
            )}
          </span>
        )}
      </button>

      {expanded && hasDetails && (
        <div className="mt-1 overflow-hidden rounded-md border border-border/60">
          {Object.keys(part.input).length > 0 && (
            <div className="bg-background/60 px-3 py-2">
              <p className="mb-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                Input
              </p>
              <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-foreground/70">
                {JSON.stringify(part.input, null, 2)}
              </pre>
            </div>
          )}
          {part.result?.content && (
            <div
              className={`border-t border-border/40 px-3 py-2 ${
                hasError ? "bg-destructive/5" : "bg-amber-500/5"
              }`}
            >
              <p className="mb-1 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                <Terminal className="size-3" />
                {hasError ? "Error" : "Result"}
              </p>
              <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-muted-foreground">
                {part.result.content}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
