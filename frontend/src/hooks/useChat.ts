import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/services/api";
import type { ChatEvent, ChatMessage, PatientBriefing, TracePart } from "@/types";

/**
 * Chat state machine for one patient.
 *
 * Server state (persisted history + latest briefing) comes from react-query;
 * the in-flight turn lives in local state and is folded into `messages` until
 * the post-turn refetch takes over as the source of truth.
 *
 * Assistant turns are a list of ordered `parts` (thinking, tool calls, text)
 * mirroring the backend's SSE events; the same shape comes back persisted as
 * `trace` on history messages, so live and replayed turns render identically.
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
      parts: message.trace ?? undefined,
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
        {
          id: assistantId,
          role: "assistant",
          content: "",
          status: "streaming",
          parts: [],
        },
      ]);
      setIsStreaming(true);

      // Every event mutates only the placeholder assistant message.
      const patchAssistant = (fn: (message: ChatMessage) => ChatMessage) =>
        setLiveMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? fn(m) : m)),
        );

      const appendPart = (part: TracePart) =>
        patchAssistant((m) => ({
          ...m,
          // A new part means the previous thinking part finished streaming.
          parts: [
            ...(m.parts ?? []).map((p) =>
              p.type === "thinking" ? { ...p, streaming: false } : p,
            ),
            part,
          ],
        }));

      const handleEvent = (event: ChatEvent) => {
        switch (event.kind) {
          case "thinking":
            appendPart({ type: "thinking", text: event.text, streaming: true });
            break;
          case "text":
            appendPart({ type: "text", text: event.text });
            patchAssistant((m) => ({
              ...m,
              content: m.content ? `${m.content}\n\n${event.text}` : event.text,
            }));
            break;
          case "tool_use":
            appendPart({
              type: "tool_use",
              id: event.id,
              tool: event.tool,
              input: event.input,
              result: null,
            });
            break;
          case "tool_result":
            patchAssistant((m) => ({
              ...m,
              parts: (m.parts ?? []).map((p) =>
                p.type === "tool_use" && p.id === event.tool_use_id
                  ? {
                      ...p,
                      result: { is_error: event.is_error, content: event.content },
                    }
                  : p,
              ),
            }));
            break;
          case "briefing_published":
            setLiveBriefing(event.briefing);
            break;
          case "done":
            patchAssistant((m) => ({
              ...m,
              status: "done",
              parts: (m.parts ?? []).map((p) =>
                p.type === "thinking" ? { ...p, streaming: false } : p,
              ),
            }));
            break;
          case "error":
            patchAssistant((m) => ({
              ...m,
              status: "error",
              content: `Something went wrong (${event.code}): ${event.message}`,
            }));
            break;
        }
      };

      const controller = new AbortController();
      abortRef.current = controller;
      // A patient switch or reset replaces abortRef; once that happens this
      // stream is stale and must not touch state that now belongs elsewhere.
      const isCurrentStream = () => abortRef.current === controller;
      try {
        await api.streamChat(patientId, text, handleEvent, controller.signal);
        // Let the persisted history become the source of truth, then drop the
        // live copies so messages don't render twice.
        if (isCurrentStream()) {
          await queryClient.invalidateQueries({ queryKey: ["chat", patientId] });
          if (isCurrentStream()) setLiveMessages([]);
        }
      } catch (error) {
        if (!controller.signal.aborted && isCurrentStream()) {
          patchAssistant((m) => ({
            ...m,
            status: "error",
            content: error instanceof Error ? error.message : "Request failed",
          }));
        }
      } finally {
        if (isCurrentStream()) setIsStreaming(false);
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
