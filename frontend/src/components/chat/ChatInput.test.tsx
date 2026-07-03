import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ChatInput } from "./ChatInput";

describe("ChatInput", () => {
  it("sends trimmed text on Enter and clears the box", () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} onReset={vi.fn()} disabled={false} />);

    const box = screen.getByRole("textbox", { name: /chat message/i });
    fireEvent.change(box, { target: { value: "  why is HbA1c high?  " } });
    fireEvent.keyDown(box, { key: "Enter" });

    expect(onSend).toHaveBeenCalledWith("why is HbA1c high?");
    expect(box).toHaveValue("");
  });

  it("Shift+Enter does not send", () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} onReset={vi.fn()} disabled={false} />);

    const box = screen.getByRole("textbox", { name: /chat message/i });
    fireEvent.change(box, { target: { value: "line one" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });

    expect(onSend).not.toHaveBeenCalled();
  });

  it("the Generate briefing button sends /briefing", () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} onReset={vi.fn()} disabled={false} />);

    fireEvent.click(screen.getByRole("button", { name: /generate briefing/i }));

    expect(onSend).toHaveBeenCalledWith("/briefing");
  });

  it("disables sending while a turn is streaming", () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} onReset={vi.fn()} disabled={true} />);

    expect(screen.getByRole("button", { name: /generate briefing/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /send message/i })).toBeDisabled();
  });

  it("New chat triggers onReset", () => {
    const onReset = vi.fn();
    render(<ChatInput onSend={vi.fn()} onReset={onReset} disabled={false} />);

    fireEvent.click(screen.getByRole("button", { name: /new chat/i }));

    expect(onReset).toHaveBeenCalled();
  });
});
