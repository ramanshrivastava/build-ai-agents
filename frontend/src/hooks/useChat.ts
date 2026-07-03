import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/api";
import type { ChatEvent, ChatMessage, PatientBriefing } from "@/types";

/** Human-readable activity line for a tool_use event. */
function activityLabel(tool: string): string {
  switch (tool) {
    case "search_clinical_guidelines":
      return "Searching clinical guidelines…";
    case "publish_briefing":
      return "Publishing briefing…";
    case "Skill":
      return "Running briefing skill…";
    default:
      return `Running ${tool}…`;
  }
}

/**
 * Chat state machine for one patient.
 *
 * Server state (persisted history + latest briefing) comes from react-query;
 * the in-flight turn lives in local state and is folded into `messages` until
 * the post-turn refetch takes over as the source of truth.
 */
export function useChat(patientId: number | undefined) {
  const queryClient = useQueryClient();
  const historyQuery = useQuery({
    queryKey: ["chat", patientId],
    queryFn: () => api.getChat(patientId!),
    enabled: patientId != null,
  });

  const [liveMessages, setLiveMessages] = useState<ChatMessage[]>([]);
  const [liveBriefing, setLiveBriefing] = useState<PatientBriefing | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Switching patients: drop in-flight turn state and cancel the stream.
  useEffect(() => {
    abortRef.current?.abort();
    setLiveMessages([]);
    setLiveBriefing(null);
    setIsStreaming(false);
  }, [patientId]);

  const historyMessages: ChatMessage[] = (historyQuery.data?.messages ?? []).map(
    (message, index) => ({
      id: `history-${index}`,
      role: message.role,
      content: message.content,
      status: "done",
    }),
  );
  const messages = [...historyMessages, ...liveMessages];
  const briefing = liveBriefing ?? historyQuery.data?.latest_briefing ?? null;

  const send = useCallback(
    async (text: string) => {
      if (patientId == null || isStreaming || !text.trim()) return;

      const stamp = Date.now();
      const assistantId = `live-${stamp}-assistant`;
      setLiveMessages((prev) => [
        ...prev,
        { id: `live-${stamp}-user`, role: "user", content: text, status: "done" },
        { id: assistantId, role: "assistant", content: "", status: "streaming" },
      ]);
      setIsStreaming(true);

      const patchAssistant = (patch: Partial<ChatMessage>) =>
        setLiveMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, ...patch } : m)),
        );

      const handleEvent = (event: ChatEvent) => {
        switch (event.kind) {
          case "text":
            setLiveMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: m.content ? `${m.content}\n\n${event.text}` : event.text,
                      activity: null,
                    }
                  : m,
              ),
            );
            break;
          case "tool_use":
            patchAssistant({ activity: activityLabel(event.tool) });
            break;
          case "tool_result":
            patchAssistant({ activity: null });
            break;
          case "briefing_published":
            setLiveBriefing(event.briefing);
            break;
          case "done":
            patchAssistant({ status: "done", activity: null });
            break;
          case "error":
            patchAssistant({
              status: "error",
              activity: null,
              content: `Something went wrong (${event.code}): ${event.message}`,
            });
            break;
        }
      };

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        await api.streamChat(patientId, text, handleEvent, controller.signal);
        // Let the persisted history become the source of truth, then drop the
        // live copies so messages don't render twice.
        await queryClient.invalidateQueries({ queryKey: ["chat", patientId] });
        setLiveMessages([]);
      } catch (error) {
        if (!controller.signal.aborted) {
          patchAssistant({
            status: "error",
            activity: null,
            content: error instanceof Error ? error.message : "Request failed",
          });
        }
      } finally {
        setIsStreaming(false);
      }
    },
    [patientId, isStreaming, queryClient],
  );

  const reset = useCallback(async () => {
    if (patientId == null) return;
    abortRef.current?.abort();
    await api.resetChat(patientId);
    setLiveMessages([]);
    setLiveBriefing(null);
    await queryClient.invalidateQueries({ queryKey: ["chat", patientId] });
  }, [patientId, queryClient]);

  return {
    messages,
    briefing,
    isStreaming,
    isLoading: historyQuery.isLoading,
    send,
    reset,
  };
}
