# Frontend-Specific Instructions

## Monorepo Context

This is part of a monorepo. Before starting work, read:
- `../docs/ARCHITECTURE.md` — System architecture and data flow
- `../CLAUDE.md` — Project-wide instructions and patterns

Start Claude Code from repo root to ensure visibility into all docs.

## Project Structure (V1)

```
src/
├── main.tsx
├── App.tsx
├── components/
│   ├── ui/                 # shadcn/ui components
│   ├── layout/
│   │   ├── Header.tsx
│   │   ├── Sidebar.tsx
│   │   └── MainArea.tsx
│   ├── patients/
│   │   ├── PatientCard.tsx
│   │   ├── PatientList.tsx
│   │   └── PatientDetails.tsx
│   └── briefing/
│       ├── BriefingView.tsx
│       └── FlagCard.tsx
├── pages/
│   └── PatientsPage.tsx
├── hooks/
│   ├── usePatients.ts
│   └── useBriefing.ts
├── services/
│   └── api.ts
├── types/
│   └── index.ts
└── lib/
    └── utils.ts            # calculateAge(), cn(), etc.
```

> **V1 Note:** No SSE streaming — simple fetch + loading spinner. No framer-motion animations. Use HTML `<details>` for collapsible sections.

## Running the Dev Server

```bash
cd frontend && npm run dev
```

## Running Tests

```bash
cd frontend && npm test
```

## Building for Production

```bash
cd frontend && npm run build
```

## Key Patterns

### Server State (React Query)
```typescript
import { useQuery, useMutation } from '@tanstack/react-query';

const { data, isLoading, error } = useQuery({
  queryKey: ['patients'],
  queryFn: () => api.getPatients(),
});
```

### Component Structure
```typescript
interface MyComponentProps {
  title: string;
  onAction: () => void;
}

export function MyComponent({ title, onAction }: MyComponentProps) {
  return <div>{title}</div>;
}
```

### API Integration
- All API calls go through `services/api.ts`
- Handle loading/error states in components
- Use environment variable `VITE_API_URL` for backend URL

## Testing

- Co-locate tests: `Component.test.tsx` next to `Component.tsx`
- Use `screen.getByRole` over `getByTestId`
- Mock API calls, never hit real backend

## Styling

- Use Tailwind CSS utility classes
- Keep styles co-located with components
- Prefer composition over complex CSS

## Important Reminders

- Functional components only (no class components)
- Type all props with interfaces
- Use React Query for server state
- Handle loading and error states
- No `any` types without justification

---

## Behavioral Guidelines

Behavioral guidelines to reduce common LLM coding mistakes.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
