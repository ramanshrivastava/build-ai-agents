import { m } from "motion/react";
import { usePatients } from "@/hooks/usePatients";
import { PatientCard } from "./PatientCard";
import { Skeleton } from "@/components/ui/skeleton";
import { stagger, spring } from "@/lib/animation";

const listVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: stagger.fast } },
};

const itemVariants = {
  hidden: { opacity: 0, x: -20 },
  visible: { opacity: 1, x: 0, transition: spring.gentle },
};

interface PatientListProps {
  selectedPatientId: number | undefined;
  onSelectPatient: (id: number) => void;
}

export function PatientList({ selectedPatientId, onSelectPatient }: PatientListProps) {
  const { data: patients, isLoading, error, refetch } = usePatients();

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2 p-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="m-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
        <p>Failed to load patients</p>
        <button
          onClick={() => refetch()}
          className="mt-2 text-destructive underline hover:no-underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!patients || patients.length === 0) {
    return (
      <p className="p-3 text-sm text-muted-foreground">No patients found</p>
    );
  }

  return (
    <m.div
      className="flex flex-col gap-1 p-3"
      variants={listVariants}
      initial="hidden"
      animate="visible"
    >
      {patients.map((patient) => (
        <m.div key={patient.id} variants={itemVariants}>
          <PatientCard
            patient={patient}
            isSelected={patient.id === selectedPatientId}
            onSelect={onSelectPatient}
          />
        </m.div>
      ))}
    </m.div>
  );
}
