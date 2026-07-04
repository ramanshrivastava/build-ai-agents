import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";
import type { ChatMessage } from "@/types";

const base: ChatMessage = {
  id: "m1",
  role: "assistant",
  content: "Hello doctor.",
  status: "done",
};

describe("MessageBubble", () => {
  it("renders plain message content", () => {
    render(<MessageBubble message={base} />);
    expect(screen.getByText("Hello doctor.")).toBeInTheDocument();
  });

  it("renders an active tool-call pill while the tool runs", () => {
    render(
      <MessageBubble
        message={{
          ...base,
          status: "streaming",
          parts: [
            {
              type: "tool_use",
              id: "t1",
              tool: "search_clinical_guidelines",
              input: { query: "metformin renal dosing" },
              result: null,
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("Searching clinical guidelines…")).toBeInTheDocument();
    expect(screen.getByText("metformin renal dosing")).toBeInTheDocument();
  });

  it("expands a completed tool call to show input and result", () => {
    render(
      <MessageBubble
        message={{
          ...base,
          parts: [
            {
              type: "tool_use",
              id: "t1",
              tool: "search_clinical_guidelines",
              input: { query: "q" },
              result: { is_error: false, content: "guideline excerpt" },
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("Searched clinical guidelines")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/guideline excerpt/)).toBeInTheDocument();
    expect(screen.getByText("Input")).toBeInTheDocument();
  });

  it("renders Bash tool calls as web research with the command preview", () => {
    render(
      <MessageBubble
        message={{
          ...base,
          status: "streaming",
          parts: [
            {
              type: "tool_use",
              id: "t1",
              tool: "Bash",
              input: {
                command: 'firecrawl search "metformin recall" --limit 5',
                description: "Search the web for metformin recalls",
              },
              result: null,
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("Researching the web…")).toBeInTheDocument();
    expect(
      screen.getByText("Search the web for metformin recalls"),
    ).toBeInTheDocument();
  });

  it("renders a collapsed thought process for finished thinking parts", () => {
    render(
      <MessageBubble
        message={{
          ...base,
          parts: [
            { type: "thinking", text: "Reviewing labs.", streaming: false },
            { type: "text", text: "Here is my answer." },
          ],
        }}
      />,
    );
    expect(screen.getByText("Thought process")).toBeInTheDocument();
    // Collapsed by default; expands on click.
    expect(screen.queryByText("Reviewing labs.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Thought process"));
    expect(screen.getByText("Reviewing labs.")).toBeInTheDocument();
    expect(screen.getByText("Here is my answer.")).toBeInTheDocument();
  });

  it("shows a thinking indicator while streaming with no parts yet", () => {
    render(
      <MessageBubble message={{ ...base, content: "", status: "streaming" }} />,
    );
    expect(screen.getByText("Thinking…")).toBeInTheDocument();
  });

  it("renders error content", () => {
    render(
      <MessageBubble
        message={{
          ...base,
          status: "error",
          content: "Something went wrong (AGENT_ERROR): boom",
        }}
      />,
    );
    expect(screen.getByText(/AGENT_ERROR/)).toBeInTheDocument();
  });
});
