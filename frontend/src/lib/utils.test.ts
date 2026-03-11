import { describe, it, expect } from "vitest";
import { calculateAge, formatRelativeTime, isLabOutOfRange } from "./utils";

describe("calculateAge", () => {
  it("returns correct age for past birthday this year", () => {
    const dob = "1990-01-01";
    const age = calculateAge(dob);
    // Born 1990-01-01, today is 2026-03-11 → 36
    expect(age).toBe(36);
  });

  it("returns age minus one if birthday has not occurred yet this year", () => {
    const dob = "1990-12-25";
    const age = calculateAge(dob);
    // Born 1990-12-25, today is 2026-03-11 → 35 (birthday not yet)
    expect(age).toBe(35);
  });
});

describe("formatRelativeTime", () => {
  it('returns "Generated just now" for timestamps within the last minute', () => {
    const now = new Date().toISOString();
    expect(formatRelativeTime(now)).toBe("Generated just now");
  });

  it("returns minutes ago for recent timestamps", () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatRelativeTime(fiveMinAgo)).toBe("5m ago");
  });

  it("returns hours ago for older timestamps", () => {
    const threeHoursAgo = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeTime(threeHoursAgo)).toBe("3h ago");
  });

  it("returns days ago for timestamps older than 24h", () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeTime(twoDaysAgo)).toBe("2d ago");
  });
});

describe("isLabOutOfRange", () => {
  const range = { min: 4.0, max: 10.0 };

  it("returns false when value is within range", () => {
    expect(isLabOutOfRange(7.0, range)).toBe(false);
  });

  it("returns false when value equals min boundary", () => {
    expect(isLabOutOfRange(4.0, range)).toBe(false);
  });

  it("returns false when value equals max boundary", () => {
    expect(isLabOutOfRange(10.0, range)).toBe(false);
  });

  it("returns true when value is below min", () => {
    expect(isLabOutOfRange(3.9, range)).toBe(true);
  });

  it("returns true when value is above max", () => {
    expect(isLabOutOfRange(10.1, range)).toBe(true);
  });
});
