import { useEffect, useRef } from "react";
import { MessageBubble } from "./MessageBubble";
import { ChatInput } from "./ChatInput";
import { Skeleton } from "@/components/ui/skeleton";
import type { ChatMessage } from "@/types";

interface ChatPanelProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  isLoading: boolean;
  onSend: (text: string) => void;
  onReset: () => void;
}

export function ChatPanel({
  messages,
  isStreaming,
  isLoading,
  onSend,
  onReset,
}: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Keep the newest message in view as the stream appends content.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-3">
        {isLoading && (
          <div className="space-y-3">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="ml-auto h-10 w-1/2" />
          </div>
        )}
        {!isLoading && messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-center">
            <p className="text-sm font-medium">Chat about this patient</p>
            <p className="text-sm text-muted-foreground">
              Ask anything, or use <span className="font-mono">/briefing</span> (or the
              button below) to generate the pre-consultation briefing.
            </p>
          </div>
        )}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
      </div>
      <ChatInput onSend={onSend} onReset={onReset} disabled={isStreaming} />
    </div>
  );
}
