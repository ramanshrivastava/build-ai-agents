import { cn } from "@/lib/utils";
import { ChatMarkdown } from "./ChatMarkdown";
import { ReasoningBlock } from "./ReasoningBlock";
import { ToolCallBadge } from "./ToolCallBadge";
import type { ChatMessage } from "@/types";

interface MessageBubbleProps {
  message: ChatMessage;
}

/**
 * User turns render as tinted right-aligned bubbles; assistant turns render
 * document-like on the left, replaying the agent's ordered parts — reasoning
 * blocks, tool-call pills, and text — exactly as they streamed.
 */
export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isError = message.status === "error";
  const isStreaming = message.status === "streaming";
  const parts = message.parts ?? [];
  const hasParts = parts.length > 0;
  const isThinkingIdle = isStreaming && !hasParts && !message.content;

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3 py-2 text-sm text-primary-foreground">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div
        className={cn(
          "max-w-[92%] text-sm",
          isError &&
            "rounded-lg border border-destructive/50 bg-destructive/10 px-3 py-2 text-destructive",
        )}
      >
        {isThinkingIdle && (
          <span
            className="animate-pulse text-xs text-muted-foreground"
            style={{ animationDuration: "1.6s" }}
          >
            Thinking…
          </span>
        )}

        {hasParts && !isError
          ? parts.map((part, index) =>
              part.type === "thinking" ? (
                <ReasoningBlock
                  key={index}
                  text={part.text}
                  streaming={part.streaming === true}
                />
              ) : part.type === "tool_use" ? (
                <ToolCallBadge
                  key={index}
                  part={part}
                  messageStreaming={isStreaming}
                />
              ) : (
                <ChatMarkdown key={index} text={part.text} />
              ),
            )
          : message.content &&
            (isError ? (
              <p className="whitespace-pre-wrap leading-relaxed">
                {message.content}
              </p>
            ) : (
              <ChatMarkdown text={message.content} />
            ))}
      </div>
    </div>
  );
}
