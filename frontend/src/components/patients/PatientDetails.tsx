import type { ReactNode } from "react";
import { m } from "motion/react";
import { Activity, Pill, TestTube2, ShieldAlert, CalendarDays } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { Patient } from "@/types";
import { calculateAge, formatLabDate, isLabOutOfRange, cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { stagger, spring } from "@/lib/animation";

const gridVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: stagger.normal } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: spring.gentle },
};

function SectionCard({
  icon: Icon,
  title,
  children,
  className,
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("border-border/50 bg-card/50 py-0 backdrop-blur-sm", className)}>
      <CardContent className="p-3">
        <div className="mb-2 flex items-center gap-2">
          <Icon className="size-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold uppercase tracking-wider text-foreground">
            {title}
          </h3>
        </div>
        {children}
      </CardContent>
    </Card>
  );
}

interface PatientDetailsProps {
  patient: Patient;
}

export function PatientDetails({ patient }: PatientDetailsProps) {
  const age = calculateAge(patient.date_of_birth);
  const genderShort = patient.gender.charAt(0).toUpperCase();

  return (
    <div className="space-y-4 p-4">
      <h2 className="text-xl font-semibold tracking-tight">
        {patient.name}, {age}
        {genderShort}
      </h2>

      <m.div
        className="grid grid-cols-1 gap-3 lg:grid-cols-2"
        variants={gridVariants}
        initial="hidden"
        animate="visible"
      >
        <m.div variants={cardVariants}>
          <SectionCard icon={Activity} title="Conditions">
            {patient.conditions.length === 0 ? (
              <p className="text-sm text-muted-foreground">No conditions on file</p>
            ) : (
              <ul className="list-disc pl-4 text-sm">
                {patient.conditions.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            )}
          </SectionCard>
        </m.div>

        <m.div variants={cardVariants}>
          <SectionCard icon={Pill} title="Medications">
            {patient.medications.length === 0 ? (
              <p className="text-sm text-muted-foreground">No medications on file</p>
            ) : (
              <ul className="list-disc pl-4 text-sm">
                {patient.medications.map((med) => (
                  <li key={med.name}>
                    {med.name} {med.dosage} &middot; {med.frequency}
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>
        </m.div>

        <m.div variants={cardVariants} className="lg:col-span-2">
          <SectionCard icon={TestTube2} title="Labs">
            {patient.labs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No lab results on file</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {patient.labs.map((lab) => {
                  const outOfRange = isLabOutOfRange(lab.value, lab.reference_range);
                  return (
                    <li key={`${lab.name}-${lab.date}`}>
                      <span className={cn(outOfRange && "text-lab-out-of-range font-medium")}>
                        {lab.name}: {lab.value}
                        {lab.unit}
                      </span>
                      <span className="text-muted-foreground">
                        {" "}
                        ({lab.reference_range.min}&ndash;{lab.reference_range.max}) &middot;{" "}
                        {formatLabDate(lab.date)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </SectionCard>
        </m.div>

        <m.div variants={cardVariants}>
          <SectionCard icon={ShieldAlert} title="Allergies">
            {patient.allergies.length === 0 ? (
              <p className="text-sm text-muted-foreground">No allergies on file</p>
            ) : (
              <ul className="list-disc pl-4 text-sm">
                {patient.allergies.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            )}
          </SectionCard>
        </m.div>

        <m.div variants={cardVariants}>
          <SectionCard icon={CalendarDays} title="Visits">
            {patient.visits.length === 0 ? (
              <p className="text-sm text-muted-foreground">No visits on file</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {patient.visits.map((v) => (
                  <li key={`${v.date}-${v.reason}`}>
                    {formatLabDate(v.date)} &middot; {v.reason}
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>
        </m.div>
      </m.div>
    </div>
  );
}
