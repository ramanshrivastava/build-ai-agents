import { useParams, useNavigate } from "react-router-dom";
import { Group, Panel, Separator } from "react-resizable-panels";
import { GripVertical } from "lucide-react";
import { MainArea } from "@/components/layout/MainArea";
import { PatientList } from "@/components/patients/PatientList";
import { PatientDetails } from "@/components/patients/PatientDetails";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { BriefingView } from "@/components/briefing/BriefingView";
import { usePatient } from "@/hooks/usePatients";
import { useChat } from "@/hooks/useChat";
import { Skeleton } from "@/components/ui/skeleton";

export function PatientsPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const patientId = id ? Number(id) : undefined;

  const { data: patient, isLoading: isLoadingPatient } = usePatient(patientId);
  const chat = useChat(patientId);

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

  const chatColumn = (
    <div className="flex h-full flex-col">
      <details className="border-b">
        <summary className="cursor-pointer px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground">
          Patient record — {patient.name}
        </summary>
        <div className="max-h-64 overflow-y-auto">
          <PatientDetails patient={patient} />
        </div>
      </details>
      <div className="min-h-0 flex-1">
        <ChatPanel
          messages={chat.messages}
          isStreaming={chat.isStreaming}
          isLoading={chat.isLoading}
          onSend={chat.send}
          onReset={chat.reset}
        />
      </div>
    </div>
  );

  // The briefing renders as a side artifact: the chat stays usable while the
  // structured briefing (published by the agent's publish_briefing tool)
  // lives in its own panel.
  if (chat.briefing) {
    return (
      <MainArea sidebar={sidebar}>
        <Group orientation="horizontal" className="h-full">
          <Panel defaultSize={50} minSize={30}>
            {chatColumn}
          </Panel>
          <Separator className="flex w-2 items-center justify-center">
            <GripVertical className="size-4 text-muted-foreground transition-colors hover:text-foreground" />
          </Separator>
          <Panel defaultSize={50} minSize={25}>
            <div className="h-full overflow-y-auto p-4">
              <BriefingView
                key={patientId}
                briefing={chat.briefing}
                runtime="sdk"
                onRegenerate={() => chat.send("/briefing")}
                isRegenerating={chat.isStreaming}
              />
            </div>
          </Panel>
        </Group>
      </MainArea>
    );
  }

  return <MainArea sidebar={sidebar}>{chatColumn}</MainArea>;
}
