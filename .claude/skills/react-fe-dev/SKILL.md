---
name: react-fe-dev
description: React frontend development patterns for AI Doctor Assistant
---

# React Frontend Development Skill

## Tech Stack
- React 18+ with TypeScript strict mode
- Vite for build tooling
- React Query for server state management
- Zustand for client state (if needed)
- Tailwind CSS for styling
- Vitest + React Testing Library for testing

## Component Patterns
- Functional components only (no class components)
- Prefer composition over prop drilling
- Co-locate tests with components: `Component.test.tsx`
- Type all props with interfaces

## Hooks Guidelines
- Use `useMemo`/`useCallback` judiciously - not everywhere
- Create custom hooks for reusable logic in `hooks/` directory
- Use React Query's `useQuery` and `useMutation` for API calls

## File Structure
```
src/
├── components/        # Reusable UI components
│   ├── PatientList/
│   ├── Briefing/
│   └── common/
├── pages/             # Route-level components
├── hooks/             # Custom React hooks
├── services/
│   └── api.ts         # All API calls centralized here
└── types/             # TypeScript interfaces
```

## Code Style
- Use TypeScript strict mode
- Prefer early returns over nested conditionals
- Destructure props in function signature
- Use `interface` for props, `type` for unions

## Testing
- Test user interactions, not implementation details
- Use `screen.getByRole` over `getByTestId`
- Mock API calls, never hit real backend
- Run: `npm test`

## Development Server
- Run: `npm run dev`
- API URL configurable via `VITE_API_URL` env var
