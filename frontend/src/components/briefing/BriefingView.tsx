import { m } from "motion/react";
import { RefreshCw } from "lucide-react";
import type { PatientBriefing } from "@/types";
import { formatRelativeTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FlagCard } from "./FlagCard";
import { stagger, spring } from "@/lib/animation";

const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: stagger.section } },
};

const sectionVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: spring.gentle },
};

const flagsContainerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: stagger.slow } },
};

const flagVariants = {
  hidden: { opacity: 0, x: -20 },
  visible: { opacity: 1, x: 0, transition: spring.gentle },
};

const badgesContainerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: stagger.fast } },
};

const badgeVariants = {
  hidden: { opacity: 0, scale: 0.8 },
  visible: { opacity: 1, scale: 1, transition: spring.snappy },
};

interface BriefingViewProps {
  briefing: PatientBriefing;
  onRegenerate: () => void;
  isRegenerating: boolean;
}

export function BriefingView({ briefing, onRegenerate, isRegenerating }: BriefingViewProps) {
  const sortedActions = [...briefing.suggested_actions].sort((a, b) => a.priority - b.priority);

  return (
    <m.div
      className="space-y-6"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {/* Header */}
      <m.div className="flex items-center justify-between" variants={sectionVariants}>
        <p className="text-sm text-muted-foreground">
          {formatRelativeTime(briefing.generated_at)}
        </p>
        <m.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
          <Button variant="outline" size="sm" onClick={onRegenerate} disabled={isRegenerating}>
            <RefreshCw className={isRegenerating ? "animate-spin" : ""} />
            Regenerate
          </Button>
        </m.div>
      </m.div>

      {/* Flags */}
      {briefing.flags.length > 0 && (
        <m.section className="space-y-2" variants={sectionVariants}>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-foreground">Flags</h3>
          <m.div className="space-y-2" variants={flagsContainerVariants}>
            {briefing.flags.map((flag, i) => (
              <m.div key={i} variants={flagVariants}>
                <FlagCard flag={flag} />
              </m.div>
            ))}
          </m.div>
        </m.section>
      )}

      {/* Summary */}
      <m.section className="space-y-3" variants={sectionVariants}>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-foreground">Summary</h3>
        <p className="text-base font-medium">{briefing.summary.one_liner}</p>
        {briefing.summary.key_conditions.length > 0 && (
          <m.div className="flex flex-wrap gap-1" variants={badgesContainerVariants}>
            {briefing.summary.key_conditions.map((condition) => (
              <m.span key={condition} variants={badgeVariants}>
                <Badge variant="secondary">{condition}</Badge>
              </m.span>
            ))}
          </m.div>
        )}
        {briefing.summary.relevant_history && (
          <p className="text-sm text-muted-foreground">{briefing.summary.relevant_history}</p>
        )}
      </m.section>

      {/* Suggested Actions */}
      {sortedActions.length > 0 && (
        <m.section className="space-y-2" variants={sectionVariants}>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-foreground">
            Suggested Actions
          </h3>
          <ol className="list-decimal space-y-2 pl-5 text-sm">
            {sortedActions.map((action, i) => (
              <li key={i}>
                <span className="font-medium">{action.action}</span>
                <span className="text-muted-foreground"> — {action.reason}</span>
              </li>
            ))}
          </ol>
        </m.section>
      )}
    </m.div>
  );
}
