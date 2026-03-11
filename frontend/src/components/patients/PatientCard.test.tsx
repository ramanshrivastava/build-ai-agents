import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PatientCard } from "./PatientCard";
import type { Patient } from "@/types";

// Mock motion/react — replace m.button with plain <button>
vi.mock("motion/react", () => ({
  m: {
    button: ({
      children,
      className,
      onClick,
    }: {
      children: React.ReactNode;
      className?: string;
      onClick?: () => void;
    }) => (
      <button className={className} onClick={onClick}>
        {children}
      </button>
    ),
  },
}));

// Mock animation spring values
vi.mock("@/lib/animation", () => ({
  spring: { snappy: {} },
}));

const mockPatient: Patient = {
  id: 42,
  name: "Jane Doe",
  date_of_birth: "1990-06-15",
  gender: "Female",
  conditions: [],
  medications: [],
  labs: [],
  allergies: [],
  visits: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("PatientCard", () => {
  it("renders patient name and age", () => {
    render(
      <PatientCard patient={mockPatient} isSelected={false} onSelect={() => {}} />,
    );

    // Should show "Jane Doe, 35F" (born 1990-06-15, today 2026-03-11 → 35, birthday not yet)
    expect(screen.getByRole("button")).toHaveTextContent("Jane Doe");
    expect(screen.getByRole("button")).toHaveTextContent("F");
  });

  it("calls onSelect with patient ID on click", () => {
    const onSelect = vi.fn();
    render(
      <PatientCard patient={mockPatient} isSelected={false} onSelect={onSelect} />,
    );

    fireEvent.click(screen.getByRole("button"));
    expect(onSelect).toHaveBeenCalledWith(42);
  });

  it("applies selected styles when isSelected is true", () => {
    render(
      <PatientCard patient={mockPatient} isSelected={true} onSelect={() => {}} />,
    );

    const button = screen.getByRole("button");
    expect(button.className).toContain("border-primary/50");
  });
});
