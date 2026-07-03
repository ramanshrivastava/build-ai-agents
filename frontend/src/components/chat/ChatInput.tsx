import { useState } from "react";
import { RotateCcw, Send, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ChatInputProps {
  onSend: (text: string) => void;
  onReset: () => void;
  disabled: boolean;
}

export function ChatInput({ onSend, onReset, disabled }: ChatInputProps) {
  const [text, setText] = useState("");

  const submit = () => {
    if (disabled || !text.trim()) return;
    onSend(text.trim());
    setText("");
  };

  return (
    <div className="space-y-2 border-t bg-background p-3">
      <div className="flex gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Ask about this patient… (Enter to send)"
          rows={2}
          aria-label="Chat message"
          className="flex-1 resize-none rounded-md border bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50"
          disabled={disabled}
        />
        <Button
          size="icon"
          onClick={submit}
          disabled={disabled || !text.trim()}
          aria-label="Send message"
        >
          <Send />
        </Button>
      </div>
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onSend("/briefing")}
          disabled={disabled}
        >
          <Sparkles />
          Generate briefing
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onReset}
          disabled={disabled}
          aria-label="Start a new chat"
        >
          <RotateCcw />
          New chat
        </Button>
      </div>
    </div>
  );
}
