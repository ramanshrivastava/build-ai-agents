import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";
import type { ChatMessage } from "@/types";

const base: ChatMessage = {
  id: "m1",
  role: "assistant",
  content: "Hello doctor.",
  status: "done",
};

describe("MessageBubble", () => {
  it("renders message content", () => {
    render(<MessageBubble message={base} />);
    expect(screen.getByText("Hello doctor.")).toBeInTheDocument();
  });

  it("shows the live tool activity line", () => {
    render(
      <MessageBubble
        message={{ ...base, status: "streaming", activity: "Searching clinical guidelines…" }}
      />,
    );
    expect(screen.getByText("Searching clinical guidelines…")).toBeInTheDocument();
  });

  it("shows a thinking indicator while streaming with no content yet", () => {
    render(
      <MessageBubble
        message={{ ...base, content: "", status: "streaming", activity: null }}
      />,
    );
    expect(screen.getByText("Thinking…")).toBeInTheDocument();
  });

  it("renders error content", () => {
    render(
      <MessageBubble
        message={{ ...base, status: "error", content: "Something went wrong (AGENT_ERROR): boom" }}
      />,
    );
    expect(screen.getByText(/AGENT_ERROR/)).toBeInTheDocument();
  });
});
