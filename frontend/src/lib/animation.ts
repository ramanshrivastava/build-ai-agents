export const stagger = {
  fast: 0.05,
  normal: 0.08,
  slow: 0.1,
  section: 0.15,
} as const;

export const spring = {
  gentle: { stiffness: 300, damping: 24 },
  snappy: { stiffness: 400, damping: 28 },
} as const;
