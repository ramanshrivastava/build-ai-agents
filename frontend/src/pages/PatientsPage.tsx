import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { m } from "motion/react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { GripHorizontal } from "lucide-react";
import { MainArea } from "@/components/layout/MainArea";
import { PatientList } from "@/components/patients/PatientList";
import { PatientDetails } from "@/components/patients/PatientDetails";
import { GenerateButton } from "@/components/patients/GenerateButton";
import { BriefingView } from "@/components/briefing/BriefingView";
import { usePatient } from "@/hooks/usePatients";
import { useBriefing } from "@/hooks/useBriefing";
import { Skeleton } from "@/components/ui/skeleton";

export function PatientsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const patientId = id ? Number(id) : undefined;

  const { data: patient, isLoading: isLoadingPatient } = usePatient(patientId);
  const briefing = useBriefing();

  // Clear briefing when switching patients
  useEffect(() => {
    briefing.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId]);

  const handleSelectPatient = (selectedId: number) => {
    navigate(`/patients/${selectedId}`);
  };

  const sidebar = (
    <PatientList selectedPatientId={patientId} onSelectPatient={handleSelectPatient} />
  );

  if (!patientId) {
    return (
      <MainArea sidebar={sidebar}>
        <div className="flex h-full items-center justify-center p-4">
          <p className="text-muted-foreground">Select a patient to view their details</p>
        </div>
      </MainArea>
    );
  }

  if (isLoadingPatient) {
    return (
      <MainArea sidebar={sidebar}>
        <div className="space-y-4 p-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-40 w-full" />
        </div>
      </MainArea>
    );
  }

  if (!patient) {
    return (
      <MainArea sidebar={sidebar}>
        <div className="flex h-full items-center justify-center p-4">
          <p className="text-muted-foreground">Patient not found</p>
        </div>
      </MainArea>
    );
  }

  if (briefing.data) {
    return (
      <MainArea sidebar={sidebar}>
        <Group orientation="vertical" className="h-full">
          <Panel defaultSize={55} minSize={30}>
            <m.div layoutScroll className="h-full overflow-y-auto p-4">
              <BriefingView
                key={patientId}
                briefing={briefing.data}
                onRegenerate={() => briefing.mutate(patient.id)}
                isRegenerating={briefing.isPending}
              />
            </m.div>
          </Panel>
          <Separator className="flex h-2 items-center justify-center">
            <GripHorizontal className="size-4 text-muted-foreground transition-colors hover:text-foreground" />
          </Separator>
          <Panel defaultSize={45} minSize={25}>
            <div className="h-full overflow-y-auto">
              <PatientDetails patient={patient} />
            </div>
          </Panel>
        </Group>
      </MainArea>
    );
  }

  return (
    <MainArea sidebar={sidebar}>
      <div className="h-full overflow-y-auto">
        <GenerateButton
          onGenerate={() => briefing.mutate(patient.id)}
          isLoading={briefing.isPending}
          error={briefing.error}
          onCancel={() => briefing.reset()}
        />
        <PatientDetails patient={patient} />
      </div>
    </MainArea>
  );
}
