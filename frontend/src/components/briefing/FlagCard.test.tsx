import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { FlagCard } from "./FlagCard";
import type { Flag } from "@/types";

// Mock motion/react — replace m.div with plain <div>, AnimatePresence as passthrough
vi.mock("motion/react", () => ({
  m: {
    div: ({
      children,
      className,
      role,
      tabIndex,
      onClick,
      onKeyDown,
      onFocus,
      onBlur,
      "aria-expanded": ariaExpanded,
    }: {
      children: React.ReactNode;
      className?: string;
      role?: string;
      tabIndex?: number;
      onClick?: () => void;
      onKeyDown?: (e: React.KeyboardEvent) => void;
      onFocus?: () => void;
      onBlur?: () => void;
      "aria-expanded"?: boolean;
    }) => (
      <div
        className={className}
        role={role}
        tabIndex={tabIndex}
        onClick={onClick}
        onKeyDown={onKeyDown}
        onFocus={onFocus}
        onBlur={onBlur}
        aria-expanded={ariaExpanded}
      >
        {children}
      </div>
    ),
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/lib/animation", () => ({
  spring: { snappy: {} },
}));

const criticalFlag: Flag = {
  category: "labs",
  severity: "critical",
  title: "Elevated potassium",
  description: "Serum potassium is 6.1 mEq/L, above the normal range.",
  source: "ai",
  suggested_action: "Order repeat BMP and ECG",
};

const infoFlag: Flag = {
  category: "ai_insight",
  severity: "info",
  title: "Diabetes screening due",
  description: "Patient has not had HbA1c in 12 months.",
  source: "ai",
  suggested_action: null,
};

describe("FlagCard", () => {
  it("renders severity and title", () => {
    render(<FlagCard flag={criticalFlag} />);

    expect(screen.getByText(/critical/i)).toBeInTheDocument();
    expect(screen.getByText(/Elevated potassium/)).toBeInTheDocument();
  });

  it("shows description when clicked (expanded)", () => {
    render(<FlagCard flag={criticalFlag} />);

    // Description should not be visible initially (isExpanded=false, AnimatePresence renders conditionally)
    expect(screen.queryByText(/Serum potassium is 6.1/)).not.toBeInTheDocument();

    // Click to expand
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/Serum potassium is 6.1/)).toBeInTheDocument();
    expect(screen.getByText(/Order repeat BMP and ECG/)).toBeInTheDocument();
  });

  it("renders category icon (svg element present)", () => {
    const { container } = render(<FlagCard flag={criticalFlag} />);

    // lucide icons render as <svg> elements
    const svgs = container.querySelectorAll("svg");
    expect(svgs.length).toBeGreaterThanOrEqual(1);
  });

  it("does not render suggested_action when null", () => {
    render(<FlagCard flag={infoFlag} />);

    // Expand to check content
    fireEvent.click(screen.getByRole("button"));
    expect(screen.queryByText(/Action:/)).not.toBeInTheDocument();
  });
});
