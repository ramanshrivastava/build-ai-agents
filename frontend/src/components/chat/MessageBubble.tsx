import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types";

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isError = message.status === "error";
  const isThinking = message.status === "streaming" && !message.content && !message.activity;

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-lg px-3 py-2 text-sm",
          isUser && "bg-primary text-primary-foreground",
          !isUser && !isError && "bg-muted",
          isError && "border border-destructive/50 bg-destructive/10 text-destructive",
        )}
      >
        {message.content && (
          <p className="whitespace-pre-wrap">{message.content}</p>
        )}
        {isThinking && (
          <span className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />
            Thinking…
          </span>
        )}
        {message.activity && (
          <span
            className={cn(
              "flex items-center gap-2 text-xs text-muted-foreground",
              message.content && "mt-2",
            )}
          >
            <Loader2 className="size-3.5 animate-spin" />
            {message.activity}
          </span>
        )}
      </div>
    </div>
  );
}
