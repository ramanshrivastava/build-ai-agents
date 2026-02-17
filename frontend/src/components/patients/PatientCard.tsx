import { m } from "motion/react";
import type { Patient } from "@/types";
import { calculateAge, cn } from "@/lib/utils";
import { spring } from "@/lib/animation";

interface PatientCardProps {
  patient: Patient;
  isSelected: boolean;
  onSelect: (id: number) => void;
}

export function PatientCard({ patient, isSelected, onSelect }: PatientCardProps) {
  const age = calculateAge(patient.date_of_birth);
  const genderShort = patient.gender.charAt(0).toUpperCase();

  return (
    <m.button
      onClick={() => onSelect(patient.id)}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      transition={spring.snappy}
      className={cn(
        "w-full rounded-lg border p-3 text-left transition-colors",
        "hover:bg-sidebar-accent focus:outline-none focus:ring-2 focus:ring-ring",
        isSelected && "border-primary/50 bg-sidebar-accent hover:bg-sidebar-accent",
      )}
    >
      <span className="font-medium">
        {patient.name}, {age}
        {genderShort}
      </span>
    </m.button>
  );
}
