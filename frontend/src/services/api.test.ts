import { describe, expect, it } from "vitest";
import { parseSSEChunk } from "./api";

describe("parseSSEChunk", () => {
  it("parses complete frames of each event kind", () => {
    const chunk =
      'event: thinking\ndata: {"text": "hmm"}\n\n' +
      'event: text\ndata: {"text": "hello"}\n\n' +
      'event: tool_use\ndata: {"id": "t1", "tool": "search_clinical_guidelines", "input": {"query": "q"}}\n\n' +
      'event: tool_result\ndata: {"tool_use_id": "t1", "is_error": false, "content": "excerpt"}\n\n' +
      'event: done\ndata: {"session_id": "s-1"}\n\n';

    const { events, rest } = parseSSEChunk("", chunk);

    expect(rest).toBe("");
    expect(events).toEqual([
      { kind: "thinking", text: "hmm" },
      { kind: "text", text: "hello" },
      {
        kind: "tool_use",
        id: "t1",
        tool: "search_clinical_guidelines",
        input: { query: "q" },
      },
      { kind: "tool_result", tool_use_id: "t1", is_error: false, content: "excerpt" },
      { kind: "done", session_id: "s-1" },
    ]);
  });

  it("keeps a partial frame in rest and completes it with the next chunk", () => {
    // Split mid-line, in the middle of the JSON payload.
    const first = parseSSEChunk("", 'event: text\ndata: {"te');
    expect(first.events).toEqual([]);
    expect(first.rest).toBe('event: text\ndata: {"te');

    const second = parseSSEChunk(first.rest, 'xt": "split across chunks"}\n\n');
    expect(second.events).toEqual([
      { kind: "text", text: "split across chunks" },
    ]);
    expect(second.rest).toBe("");
  });

  it("maps briefing_published data payload to the briefing field", () => {
    const briefing = {
      flags: [],
      summary: { one_liner: "ok", key_conditions: [], relevant_history: "" },
      suggested_actions: [],
      generated_at: "2026-07-04T00:00:00Z",
      id: 7,
    };
    const chunk = `event: briefing_published\ndata: ${JSON.stringify(briefing)}\n\n`;

    const { events } = parseSSEChunk("", chunk);

    expect(events).toEqual([{ kind: "briefing_published", briefing }]);
  });

  it("parses error events", () => {
    const { events } = parseSSEChunk(
      "",
      'event: error\ndata: {"code": "AGENT_ERROR", "message": "boom"}\n\n',
    );
    expect(events).toEqual([
      { kind: "error", code: "AGENT_ERROR", message: "boom" },
    ]);
  });

  it("ignores unknown event names and frames without an event line", () => {
    const chunk =
      'event: mystery\ndata: {"x": 1}\n\n' + 'data: {"orphan": true}\n\n';
    const { events, rest } = parseSSEChunk("", chunk);
    expect(events).toEqual([]);
    expect(rest).toBe("");
  });
});
