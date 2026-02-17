# SCOPE-V2: AI Doctor Assistant - Frontend Redesign

> **Goal:** Transform the frontend into a dark luxury aesthetic with warm gold accents, full Motion for React animations, split-pane layout, expandable flag cards, and theatrical briefing loading experience. Backend unchanged.
> **Status:** Planning
> **Created:** February 8, 2026
> **Depends on:** V1 complete (tagged `v1.0.0` at `8aa1d0b`)
> **Reviewed by:** UI/Design expert, React/Animation expert, Library/DX expert

---

## V2 Constraints (What's OUT)

| Feature | V2 Status | Deferred To |
|---------|-----------|-------------|
| Agent tools (MCP) | ❌ Out | V3 |
| Drug interaction DB | ❌ Out | V3 |
| Langfuse observability | ❌ Out | V3 |
| SSE streaming | ❌ Out | V3 |
| Authentication | ❌ Out | V3+ |
| Rate limiting | ❌ Out | V3+ |
| Mobile responsive | ❌ Out | V3+ |
| Briefing caching | ❌ Out | V3+ |
| Backend changes | ❌ Out | V3 |
| Dark/light mode toggle | ❌ Out | V3 (clinical risk documented below) |
| Patient search/filter | ❌ Out | V3 |

---

## V2 Scope (What's IN)

| Feature | Description |
|---------|-------------|
| Dark luxury theme | Charcoal background, warm gold (#D4AF37) accents |
| Inter font | Self-hosted variable font with defined type scale |
| Motion for React | Staggered lists, layout animations, spring physics, reduced motion support |
| Split-pane layout | Briefing (top) + Patient details (bottom), resizable divider |
| Flag card expand | Collapse/expand on click (hover delay for desktop) with layout animation |
| Theatrical loading | Cycling status messages with phase indicator during ~2min generation |
| Patient details card grid | Replace `<details>` with 2-column card grid |
| Accessibility | `prefers-reduced-motion`, keyboard expand, ARIA attributes, focus-visible |

---

## V2 Approach

### What Changes
```
┌─────────────────────────────────────────────────────────────────┐
│                     V2 Frontend Changes                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  V1 (Current)              →   V2 (Target)                      │
│  ─────────────                 ──────────────                    │
│  Light theme, system fonts →   Dark charcoal + gold, Inter      │
│  No animations             →   Motion for React (reduced-motion) │
│  Static flag cards         →   Click-to-expand (hover delay)    │
│  <details> accordions      →   2-col card grid                  │
│  Single scroll area        →   Resizable split pane             │
│  Basic spinner             →   Theatrical loading overlay       │
│  Briefing below details    →   Briefing ABOVE details           │
│  Hardcoded blue selection  →   Gold selection with spring       │
│                                                                  │
│  Backend: NO CHANGES                                            │
│  API: NO CHANGES                                                │
│  Data models: NO CHANGES                                        │
│  Types: NO CHANGES                                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **Dark mode only** — No toggle in V2. `class="dark"` on `<html>`. Light mode CSS vars kept functional for V3 toggle.
2. **`motion` package (not `framer-motion`)** — The `framer-motion` package has been renamed to `motion`. React 19 requires `motion` for full compatibility. Import from `"motion/react"`.
3. **`LazyMotion` + `domMax`** — Tree-shakeable Motion loading. Saves ~9KB vs full import while keeping layout animations and AnimatePresence.
4. **`MotionConfig reducedMotion="user"`** — Respects OS-level "Reduce Motion" preference automatically. Transforms skip, opacity still animates. Medical app accessibility requirement.
5. **Split pane via `react-resizable-panels` v4** — Lightweight (~8KB), keyboard-accessible, WAI-ARIA compliant.
6. **Self-hosted Inter** — Via `@fontsource-variable/inter`. No Google Fonts CDN (HIPAA/privacy consideration for medical app). ~45KB Latin subset.
7. **Briefing above details** — Primary clinical output on top. Patient data as reference material below.
8. **Click-to-expand flags (with hover delay)** — Primary: `onClick` toggle on all devices. Enhancement: 300ms hover delay on desktop. Required: `onFocus`/keyboard expand, `aria-expanded`.
9. **Gold used sparingly** — Reserved for primary actions (Generate button), selected states, and focus rings. Section headings use foreground weight, not gold color.

### Clinical Dark Mode Risk (V3 Action)

> **Note:** Dark UIs in bright clinical settings (exam rooms, nursing stations) can cause screen glare and readability issues for users with astigmatism. The light mode CSS vars are kept functional in V2. V3 should add a toggle. If V2 is tested with clinical users, consider bumping this to V2 scope.

---

## Technology Additions

### New Dependencies

| Package | Version | Effective Size | Purpose |
|---------|---------|---------------|---------|
| `motion` | ^12 | ~25KB (with LazyMotion + domMax) | All animations: layout, stagger, spring, presence |
| `react-resizable-panels` | ^4 | ~8KB | Split pane with draggable divider |
| `@fontsource-variable/inter` | ^5 | ~45KB (Latin woff2) | Self-hosted Inter variable font |

> **Note:** `tw-animate-css` (already installed) is kept — shadcn/ui components depend on it internally. Don't expand its usage; use Motion for all new V2 animations.

### Existing Stack (Unchanged)

| Component | Technology |
|-----------|------------|
| Framework | React 19 |
| Language | TypeScript (strict) |
| Build | Vite 7 |
| Routing | React Router 7 |
| State | @tanstack/react-query@5 |
| UI Components | shadcn/ui (new-york) |
| Styling | Tailwind CSS 4 (OKLch) |
| Icons | lucide-react |

---

## Animation System

### Centralized Constants

All animation timing and spring values are defined in a single file to prevent drift across components.

**New file: `src/lib/animation.ts`**

```typescript
// Stagger timing scale — smaller items faster, larger sections slower
export const stagger = {
  fast: 0.05,    // Small items (patient list, badges)
  normal: 0.08,  // Medium items (detail cards)
  slow: 0.1,     // Large items (flags)
  section: 0.15, // Top-level sections
} as const;

// Spring presets — two is enough
export const spring = {
  gentle: { stiffness: 300, damping: 24 },  // List entrances, ambient animations
  snappy: { stiffness: 400, damping: 28 },  // Interactions (hover, expand, tap)
} as const;
```

### Import Convention

All Motion imports use the renamed package:
```typescript
import { m, AnimatePresence, MotionConfig, LazyMotion, domMax } from "motion/react"
```

Use `m` (not `motion`) for tree-shakeable components when using `LazyMotion`.

### Animation Specifications

| Animation | Type | Params | Source |
|-----------|------|--------|--------|
| Patient list stagger | `variants` + `staggerChildren` | `stagger.fast`, `spring.gentle` | NOT AnimatePresence |
| Card hover | `whileHover` | `scale: 1.02`, `spring.snappy` | |
| Card tap | `whileTap` | `scale: 0.98` | |
| Flag expand | `layout="position"` + `AnimatePresence` | `spring.snappy` | Only on FlagCard div |
| Briefing sections | `variants` + `staggerChildren` | `stagger.section` | NOT AnimatePresence |
| Flag items | `variants` + `staggerChildren` | `stagger.slow`, slide from left | |
| Loading icon pulse | keyframes | `scale: [1,1.15,1]`, 2s, `easeInOut` | |
| Status message cycle | `AnimatePresence mode="wait"` | fade+slide, 0.3s, `easeInOut` | |
| Loading dots | keyframes | `scale: [1,1.4,1]`, stagger 0.2s, `easeInOut` | |
| Details cards | `variants` + `staggerChildren` | `stagger.normal`, `spring.gentle` | |

### Reduced Motion

`<MotionConfig reducedMotion="user">` wraps the entire app. When OS "Reduce Motion" is enabled:
- Transform/layout animations skip instantly
- Opacity and color transitions still animate (safe for vestibular users)
- Zero code changes needed in individual components

### AnimatePresence Rules

Only use `AnimatePresence` where elements actually enter/exit the DOM:
- **YES:** Loading overlay message cycling (`mode="wait"`) — messages swap in/out
- **YES:** FlagCard expand content — inner content enters/exits
- **NO:** PatientList stagger — items load once, use `variants`
- **NO:** BriefingView sections — sections appear once, use `variants`

---

## Color Palette

> **Important:** OKLch values below are the source of truth. Test in-browser — do not rely on hex approximations. The values are tuned for a "dark charcoal" look (not pure black).

### Dark Mode (Primary)

| Token | OKLch Value | Usage |
|-------|-------------|-------|
| `--background` | `oklch(0.18 0.005 260)` | Main page background (dark charcoal) |
| `--foreground` | `oklch(0.93 0.01 85)` | Primary text (warm off-white) |
| `--card` | `oklch(0.23 0.008 260)` | Card backgrounds (slightly lighter) |
| `--card-foreground` | `oklch(0.93 0.01 85)` | Card text |
| `--primary` | `oklch(0.76 0.13 85)` | Gold accent (~#D4AF37) |
| `--primary-foreground` | `oklch(0.18 0.005 260)` | Text on gold surfaces |
| `--secondary` | `oklch(0.28 0.008 260)` | Elevated surfaces |
| `--secondary-foreground` | `oklch(0.88 0.01 85)` | Text on elevated surfaces |
| `--muted` | `oklch(0.26 0.006 260)` | Muted backgrounds |
| `--muted-foreground` | `oklch(0.60 0.02 85)` | Secondary text |
| `--accent` | `oklch(0.76 0.13 85 / 20%)` | Hover backgrounds (gold @ 20%) |
| `--accent-foreground` | `oklch(0.82 0.10 85)` | Lighter gold text |
| `--border` | `oklch(1 0 0 / 12%)` | Borders (white @ 12%) |
| `--input` | `oklch(1 0 0 / 15%)` | Input borders |
| `--ring` | `oklch(0.76 0.13 85)` | Focus rings (gold) |
| `--sidebar` | `oklch(0.15 0.004 260)` | Sidebar (darker than main) |
| `--sidebar-foreground` | `oklch(0.88 0.01 85)` | Sidebar text |
| `--sidebar-accent` | `oklch(0.76 0.13 85 / 15%)` | Sidebar hover (gold tint) |
| `--sidebar-border` | `oklch(1 0 0 / 8%)` | Sidebar border |
| `--destructive` | `oklch(0.70 0.19 22)` | Error states (red) |

### Flag Severity Colors (Dark-Adapted)

| Severity | Text | Background | Border |
|----------|------|------------|--------|
| Critical | `oklch(0.70 0.19 22)` | `oklch(0.25 0.05 22)` | `oklch(0.35 0.10 22)` |
| Warning | `oklch(0.80 0.15 70)` | `oklch(0.25 0.04 70)` | `oklch(0.40 0.08 70)` |
| Info | `oklch(0.70 0.14 250)` | `oklch(0.22 0.04 250)` | `oklch(0.35 0.08 250)` |

> **Note:** Warning hue shifted from 80 → 70 (more amber, further from gold at hue 85) to avoid visual confusion between warning flags and gold accents.

### Gold Scale (Tailwind tokens as `--color-gold-*`)

| Token | OKLch | Usage |
|-------|-------|-------|
| `gold-50` | `oklch(0.97 0.02 85)` | Lightest tint |
| `gold-400` | `oklch(0.76 0.13 85)` | Primary gold (= `--primary`) |
| `gold-600` | `oklch(0.58 0.12 85)` | Pressed states |
| `gold-900` | `oklch(0.28 0.05 85)` | Darkest |

---

## Typography Scale

| Element | Size | Weight | Leading | Tracking |
|---------|------|--------|---------|----------|
| Patient name (header) | 20px (`text-xl`) | 600 | 1.3 | `tracking-tight` |
| Section heading | 14px (`text-sm`) | 600 | 1.4 | `tracking-wider uppercase` |
| Body text | 14px (`text-sm`) | 400 | 1.5 | normal |
| Lab values | 14px (`text-sm`) | 500 | 1.4 | normal |
| Flag title | 14px (`text-sm`) | 600 | 1.4 | `uppercase` |
| Flag description | 14px (`text-sm`) | 400 | 1.5 | normal |
| Muted/caption | 12px (`text-xs`) | 400 | 1.4 | normal |
| Generate button | 14px (`text-sm`) | 500 | 1.4 | normal |

> **Clinical readability:** Minimum 14px for all primary content. 12px only for metadata (timestamps, reference ranges). Inter's `font-feature-settings: "cv11", "ss01"` enables disambiguated characters (l/1/I).

---

## UI Specifications

### Layout (V2)

```
┌─────────────────────────────────────────────────────────────────┐
│  🏥 AI Doctor Assistant                    [backdrop-blur header] │
├────────────────┬────────────────────────────────────────────────┤
│                │                                                 │
│  SIDEBAR       │  MAIN AREA                                      │
│  (260px)       │                                                 │
│  Dark bg       │  ┌─────────────────────────────────────────┐   │
│                │  │ [✨ Generate Briefing] (gold glow)       │   │
│  Patient List  │  │                                         │   │
│  (staggered    │  │ ═══════════════════════════════════════ │   │
│   entrance)    │  │                                         │   │
│                │  │ After briefing generated:               │   │
│  ┌──────────┐  │  │ ┌─────────────────────────────────────┐ │   │
│  │ Card     │  │  │ │ BRIEFING (55%, scrollable)          │ │   │
│  │ Gold sel │◄─┤  │ │ Flags (click to expand)             │ │   │
│  └──────────┘  │  │ │ Summary + Actions (stagger reveal)  │ │   │
│  ┌──────────┐  │  │ ├──── drag handle (8px, visible) ────┤ │   │
│  │ Card     │  │  │ │ PATIENT DETAILS (45%, scrollable)   │ │   │
│  └──────────┘  │  │ │ 2-column card grid                  │ │   │
│  ┌──────────┐  │  │ └─────────────────────────────────────┘ │   │
│  │ Card     │  │  └─────────────────────────────────────────┘   │
│  └──────────┘  │                                                 │
│                │                                                 │
└────────────────┴────────────────────────────────────────────────┘
```

### Gold Usage Strategy

Gold is reserved for **high-signal moments only** (luxury = restraint):

| Use Gold | Don't Use Gold (use neutral instead) |
|----------|--------------------------------------|
| Generate Briefing button | Section headings (use `foreground` + weight) |
| Selected patient card border + bg | Card header icons (use `muted-foreground`) |
| Focus rings (`--ring`) | Drag handle (use `muted-foreground`) |
| Loading Sparkles icon | Condition badges (use `secondary`) |
| | Flag chevrons (use severity color) |

### Patient Card (Sidebar)

- Same info density as V1: "John Smith, 67M"
- **V2 changes:**
  - `m.button` with `whileHover={{ scale: 1.02 }}`, `whileTap={{ scale: 0.98 }}`
  - Selected: `border-primary/50` (gold border) + `bg-sidebar-accent` (transparent gold bg)
  - Spring transition: `spring.snappy`
  - Staggered list entrance: `stagger.fast`, slide from left (via `variants`, NOT AnimatePresence)

### Generate Button

- Centered prominently at top of main area
- Gold glow: `shadow-lg shadow-primary/20`
- `m.div` wrapper: hover scale 1.05, tap scale 0.95
- Error state: destructive color text below button

### Loading Experience (During ~2min Generation)

```
┌─────────────────────────────────────────┐
│                                          │
│            ✨ (pulsing gold)              │
│                                          │
│   Step 4 of 11                           │
│   "Reviewing current medications..."     │
│   (fades in/out, cycles every 3.5s)     │
│                                          │
│              ● ● ●                       │
│        (staggered pulse dots)            │
│                                          │
│          [Cancel]                         │
│                                          │
└─────────────────────────────────────────┘
```

**Status messages (11, cycling every 3.5s):**
1. "Reading patient file..."
2. "Analyzing symptoms..."
3. "Reviewing current medications..."
4. "Checking lab results against guidelines..."
5. "Evaluating drug interactions..."
6. "Screening for overdue preventive care..."
7. "Assessing chronic condition management..."
8. "Identifying clinical flags..."
9. "Generating clinical summary..."
10. "Preparing suggested actions..."
11. "Finalizing briefing..."

**Cycling behavior:**
- Messages 1-10 cycle normally via index: `Math.floor(elapsed / 3.5) % 10`
- After ~100s elapsed, lock on message 11 ("Finalizing briefing...") — avoids jarring loop-back
- Phase indicator shown: "Step N of 11"
- Cancel button (calls `briefing.reset()`) — lets users abort long waits

### Flag Card Behavior

```
COLLAPSED (default):
┌─────────────────────────────────────────┐
│ 🔴 CRITICAL: HbA1c significantly high  ▼│
└─────────────────────────────────────────┘

EXPANDED (on click / hover-with-delay / focus):
┌─────────────────────────────────────────┐
│ 🔴 CRITICAL: HbA1c significantly high  ▲│
│                                          │
│   Current value 8.2% exceeds target of  │
│   7.0% indicating poor glycemic control │
│                                          │
│   Action: Consider medication adjustment │
│   [Labs]                                │
└─────────────────────────────────────────┘
```

**Interaction model (accessible):**
- **Primary:** `onClick` toggle on all devices
- **Enhancement:** `onHoverStart` with **300ms delay** before expanding (desktop only — prevents accidental expansion when mousing across)
- **Keyboard:** `onFocus` expands, `onBlur` collapses
- **ARIA:** `role="button"`, `aria-expanded="true|false"`, `tabIndex={0}`, `Enter`/`Space` key handling
- **Layout:** `layout="position"` (not `layout`) on FlagCard — animates sibling position shifts without conflicting with split-pane resize
- **Scroll:** Add `layoutScroll` to the scrollable briefing panel ancestor

### Patient Details Card Grid

```
┌──────────────────┐  ┌──────────────────┐
│ CONDITIONS        │  │ MEDICATIONS       │
│                   │  │                   │
│ • Type 2 Diabetes │  │ Metformin 1000mg  │
│ • Hypertension    │  │   twice daily     │
│ • CKD Stage 3    │  │ Lisinopril 20mg   │
│                   │  │   once daily      │
└──────────────────┘  └──────────────────┘
┌──────────────────────────────────────────┐
│ LAB RESULTS (full-width)                  │
│                                           │
│ HbA1c: 7.2%        (4.0–5.6) · Jan 2024 │
│ eGFR: 45            (>60) · Jan 2024     │
│ Creatinine: 1.8     (0.6–1.2) · Jan 2024│
└──────────────────────────────────────────┘
┌──────────────────┐  ┌──────────────────┐
│ ALLERGIES         │  │ RECENT VISITS     │
│                   │  │                   │
│ • Penicillin      │  │ Jan 15, 2024      │
│ • Sulfa drugs     │  │   Diabetes f/u    │
└──────────────────┘  └──────────────────┘
```

- Grid: `grid-cols-1 lg:grid-cols-2`, `gap-3`
- **Labs card spans full width** (`lg:col-span-2`) — most critical reference data, benefits from full width
- Card header: section title with icon, `text-sm font-semibold uppercase tracking-wider` (foreground color, not gold)
- Card icons: `text-muted-foreground` (neutral, not gold)
- Cards: `bg-card/50 backdrop-blur-sm`, `border-border/50`
- Card padding: `p-3` (tighter — clinical data density > breathing room)
- Lab out-of-range: `text-flag-critical` (red)
- Staggered entrance: `stagger.normal`, `spring.gentle` (via `variants`, NOT AnimatePresence)

### Split Pane

- `PanelGroup direction="vertical"` from `react-resizable-panels` v4
- Top Panel (55% default, **30% min**): Briefing with `overflow-y-auto`
- `PanelResizeHandle`: **8px tall**, `GripHorizontal` icon, `text-muted-foreground` (neutral), `hover:text-foreground` transition
- Bottom Panel (45% default, **25% min**): Patient details with `overflow-y-auto`
- **Keyboard resize:** Handle is focusable with arrow key support (built into react-resizable-panels)
- Add `layoutScroll` on briefing panel scroll container (prevents Motion layout animation offset when scrolled)

### Briefing Theatrical Reveal

Sections appear sequentially via `variants` + `staggerChildren` (NOT AnimatePresence):
1. **Header** (timestamp + regenerate) — fade in
2. **Flags** — heading fades, then flags stagger one-by-one from left (`stagger.slow`)
3. **Summary** — fades in as block, condition badges stagger (`stagger.fast`)
4. **Actions** — stagger in one-by-one

- Overall container: `stagger.section` between sections
- Section headings: `text-foreground font-semibold` (NOT gold — per gold restraint strategy)
- Regenerate button: `whileHover={{ scale: 1.05 }}`, `whileTap={{ scale: 0.95 }}`
- Flag wrappers: do NOT add `layout` prop (only on FlagCard itself — avoids double measurement)
- Add `key={patientId}` on BriefingView wrapper for clean unmount/remount on patient switch

### Scrollbar Styling

Add to `index.css` `@layer base`:
```css
* {
  scrollbar-width: thin;
  scrollbar-color: oklch(0.30 0.01 260) transparent;
}
```

---

## Project Structure Changes

### New Files
```
frontend/src/
├── lib/
│   └── animation.ts                     # ★ NEW: timing constants + spring presets
└── components/
    └── briefing/
        └── BriefingLoadingOverlay.tsx    # ★ NEW: loading experience
```

### Modified Files
```
frontend/
├── index.html                          # Add class="dark"
├── package.json                        # +3 dependencies (motion, panels, inter)
└── src/
    ├── main.tsx                         # Font import + LazyMotion + MotionConfig
    ├── App.tsx                          # Wrap in MotionConfig reducedMotion="user"
    ├── index.css                        # Full color palette rewrite + scrollbar
    ├── components/
    │   ├── ui/                          # No changes
    │   ├── layout/
    │   │   ├── Header.tsx               # Glassmorphism + gold icon
    │   │   ├── Sidebar.tsx              # Dark bg + 260px width
    │   │   └── MainArea.tsx             # Fixed height for split pane
    │   ├── patients/
    │   │   ├── PatientCard.tsx          # Gold selection + motion hover
    │   │   ├── PatientList.tsx          # Staggered animation (variants)
    │   │   ├── PatientDetails.tsx       # ★ Major rewrite: card grid
    │   │   └── GenerateButton.tsx       # Use loading overlay + cancel
    │   └── briefing/
    │       ├── BriefingView.tsx          # ★ Major rewrite: theatrical reveal
    │       └── FlagCard.tsx              # ★ Major rewrite: expand on click
    ├── pages/
    │   └── PatientsPage.tsx             # ★ Major rewrite: split pane
    ├── hooks/                           # No changes
    ├── services/                        # No changes
    ├── types/                           # No changes
    └── lib/
        ├── utils.ts                     # No changes
        └── animation.ts                 # ★ NEW: animation constants
```

**Total:** 14 modified, 2 new files. No files deleted. No backend changes.

---

## Task Breakdown

### Legend
- `[S]` Small (~15-30 min)
- `[M]` Medium (~30-60 min)
- `[L]` Large (~60-90 min)
- `→ verify:` How to verify task is complete
- `⛔ blocked by:` Task dependencies

---

## 0. Animation Foundation

### 0.1 Animation Constants [S]
- [ ] Create `src/lib/animation.ts` with `stagger` and `spring` constants
- [ ] Export `stagger.fast`, `stagger.normal`, `stagger.slow`, `stagger.section`
- [ ] Export `spring.gentle` (300/24) and `spring.snappy` (400/28)
- → verify: File imports without error in TypeScript
- ⛔ blocked by: none

---

## 1. Dependencies & Foundation

### 1.1 Install Dependencies [S]
- [ ] `npm install motion react-resizable-panels @fontsource-variable/inter`
- [ ] Verify all three appear in `package.json`
- → verify: `npm ls motion react-resizable-panels @fontsource-variable/inter`

### 1.2 Dark Mode, Font & Motion Setup [M]
- [ ] Add `class="dark"` to `<html>` in `index.html`
- [ ] Import `@fontsource-variable/inter` in `main.tsx` before `index.css`
- [ ] Add `LazyMotion features={domMax} strict` wrapper in `main.tsx`
- [ ] Add `MotionConfig reducedMotion="user"` wrapper in `App.tsx`
- [ ] All Motion imports use `from "motion/react"` and `m` component (not `motion`)
- → verify: App loads dark, Inter font in DevTools, Motion works, `prefers-reduced-motion: reduce` skips animations
- ⛔ blocked by: 1.1, 0.1

### 1.3 Color Palette Rewrite [L]
- [ ] Rewrite all OKLch values in `src/index.css` `:root` block (light mode, gold-tinted)
- [ ] Rewrite all OKLch values in `.dark` block (dark charcoal + gold, per palette table above)
- [ ] Add gold scale tokens (`--color-gold-50` through `--color-gold-900`) in `@theme inline`
- [ ] Add `--font-sans: "Inter Variable", ...` to `@theme inline`
- [ ] Update flag severity colors for dark backgrounds (warning hue 70, not 80)
- [ ] Add `font-feature-settings: "cv11", "ss01"`, antialiasing to body
- [ ] Add `::selection` gold highlight
- [ ] Add scrollbar styling (`scrollbar-width: thin`, themed color)
- [ ] Increase `--border` to `12%` opacity, `--accent` to `20%` opacity
- [ ] **Test in browser** — verify dark charcoal (not pure black), adequate contrast, gold accents visible
- → verify: App renders dark charcoal bg, warm off-white text, gold focus rings. All text meets WCAG AA contrast.
- ⛔ blocked by: 1.2

---

## 2. Layout Shell

### 2.1 Header Update [S]
- [ ] Add `backdrop-blur-sm`, `bg-background/95` for glassmorphism
- [ ] Set Stethoscope icon to `text-primary` (gold — one of the 4 gold moments)
- [ ] Add `tracking-tight` to title
- [ ] Adjust border to `border-border/50`
- → verify: Header has gold icon, glassmorphism blur, subtle border
- ⛔ blocked by: 1.3

### 2.2 Sidebar Update [S]
- [ ] Change `bg-background` to `bg-sidebar`
- [ ] Change border to `border-sidebar-border`
- [ ] Update width from 250px to 260px
- → verify: Sidebar visually darker than main area
- ⛔ blocked by: 1.3

### 2.3 MainArea Update [S]
- [ ] Update `ml-[250px]` to `ml-[260px]`
- [ ] Set `h-[calc(100vh-3.5rem)]` on `<main>` (needed for split pane)
- [ ] Remove `p-6` (panels manage own padding)
- → verify: Main area fills viewport height correctly
- ⛔ blocked by: 2.2

---

## 3. Sidebar Animations

### 3.1 PatientCard Animation [M]
- [ ] Replace `button` with `m.button` (tree-shakeable Motion component)
- [ ] Add `whileHover={{ scale: 1.02 }}`, `whileTap={{ scale: 0.98 }}`
- [ ] Use `spring.snappy` transition
- [ ] Replace hardcoded `blue-500`/`bg-blue-50` with `border-primary/50`, `bg-sidebar-accent`
- [ ] Replace `hover:bg-gray-100` with `hover:bg-sidebar-accent`
- → verify: Card scales on hover, gold border/bg when selected
- ⛔ blocked by: 0.1, 1.3

### 3.2 PatientList Stagger [M]
- [ ] Wrap list in `m.div` with `variants` using `stagger.fast` (NOT AnimatePresence)
- [ ] Wrap each item in `m.div` with slide-from-left variant using `spring.gentle`
- [ ] Set `initial="hidden" animate="visible"` on container (variants, not inline objects)
- [ ] Update error state to use `destructive` tokens (not hardcoded red)
- → verify: Patient list items animate in sequentially on load. Error state uses theme colors.
- ⛔ blocked by: 3.1

---

## 4. Patient Details Rewrite

### 4.1 Card Grid Layout [L]
- [ ] Create local `SectionCard` helper (Card + title + icon, uses `text-foreground` not `text-primary`)
- [ ] Replace 5 `<details>` elements with `SectionCard` instances
- [ ] Set up `grid-cols-1 lg:grid-cols-2` responsive grid with `gap-3`
- [ ] **Labs card spans full width** (`lg:col-span-2`)
- [ ] Map sections: Conditions (Activity), Medications (Pill), Labs (TestTube2), Allergies (ShieldAlert), Visits (CalendarDays)
- [ ] Style cards: `bg-card/50 backdrop-blur-sm`, `border-border/50`, padding `p-3`
- [ ] Card icons: `text-muted-foreground` (neutral)
- [ ] Lab values: `justify-between` layout, out-of-range `text-flag-critical`
- [ ] Handle empty states ("No conditions on file", etc.)
- [ ] Add staggered entrance via `variants` with `stagger.normal`, `spring.gentle`
- → verify: 2-column grid, labs full-width, neutral section headers, staggered entrance
- ⛔ blocked by: 0.1, 1.3

---

## 5. Flag Card Rewrite

### 5.1 Expand Behavior (Accessible) [L]
- [ ] Add `isExpanded` state
- [ ] Collapsed state: severity icon + title + chevron
- [ ] Expanded state: description + suggested action + category badge
- [ ] **Primary:** `onClick` toggle on all devices
- [ ] **Enhancement:** `onHoverStart` with 300ms delay via `useRef` timeout, `onHoverEnd` cancels + collapses
- [ ] **Keyboard:** `onFocus` expands, `onBlur` collapses
- [ ] **ARIA:** `role="button"`, `aria-expanded={isExpanded}`, `tabIndex={0}`, handle `Enter`/`Space`
- [ ] Use `layout="position"` (not `layout`) on outer `m.div` — avoids split-pane resize conflict
- [ ] Add `AnimatePresence` for expand content height animation using `spring.snappy`
- [ ] Add chevron rotation animation (180° on expand)
- → verify: Click expands/collapses. Hover with 300ms delay. Tab + Enter works. Screen reader announces expanded state.
- ⛔ blocked by: 0.1, 1.3

---

## 6. Briefing Loading Experience

### 6.1 Loading Overlay Component [M]
- [ ] Create `src/components/briefing/BriefingLoadingOverlay.tsx`
- [ ] Pulsing gold Sparkles icon: `scale: [1, 1.15, 1]`, 2s infinite, `easeInOut`
- [ ] 11 cycling status messages, rotating every 3.5s
- [ ] Phase indicator: "Step N of 11"
- [ ] After ~100s elapsed, lock on message 11 ("Finalizing briefing...")
- [ ] Messages animate with `AnimatePresence mode="wait"`: fade+slide, `easeInOut`
- [ ] Three animated dots: staggered pulse
- [ ] Cancel button (calls a provided `onCancel` callback)
- → verify: Messages cycle with phase indicator. Locks on final message after 100s. Cancel button visible.
- ⛔ blocked by: 1.1

### 6.2 Generate Button Update [M]
- [ ] When `isLoading`: render `BriefingLoadingOverlay` with `onCancel={() => briefing.reset()}`
- [ ] Button: `shadow-lg shadow-primary/20` for gold glow
- [ ] Wrap in `m.div` with hover/tap scale
- [ ] Error state: `text-destructive` below button
- → verify: Click Generate → loading overlay. Cancel aborts. After completion → briefing shows.
- ⛔ blocked by: 6.1

---

## 7. Split Pane Layout

### 7.1 PatientsPage Rewrite [L]
- [ ] Import `PanelGroup`, `Panel`, `PanelResizeHandle` from `react-resizable-panels`
- [ ] When briefing exists: render vertical `PanelGroup`
  - [ ] Top Panel (55% default, 30% min): BriefingView + `overflow-y-auto` + `layoutScroll` (for Motion)
  - [ ] PanelResizeHandle: 8px tall, `GripHorizontal` icon, `text-muted-foreground`, `hover:text-foreground`
  - [ ] Bottom Panel (45% default, 25% min): PatientDetails + `overflow-y-auto`
- [ ] When no briefing: GenerateButton at top, PatientDetails below, single scroll
- [ ] Briefing entrance: `m.div` with `initial={{ opacity: 0, y: 20 }}`
- [ ] Add `key={patientId}` on BriefingView for clean remount on patient switch
- [ ] Maintain existing behavior: reset briefing on patient change, URL-based selection
- → verify: Split pane with draggable 8px handle. Both panels scroll. Keyboard resize works.
- ⛔ blocked by: 4.1, 5.1, 6.2

---

## 8. Briefing Theatrical Reveal

### 8.1 BriefingView Rewrite [L]
- [ ] Outer container: `variants` with `stagger.section` (NOT AnimatePresence)
- [ ] Header (timestamp + regenerate): `sectionVariants` fade in
- [ ] Flags: `variants` container with `stagger.slow`, items slide from left using `spring.gentle`
- [ ] Summary: fade in block, key_conditions badges stagger using `stagger.fast`
- [ ] Actions: stagger in one-by-one
- [ ] Section headings: `text-foreground font-semibold` (NOT gold)
- [ ] Regenerate button: `whileHover={{ scale: 1.05 }}`, `whileTap={{ scale: 0.95 }}`
- [ ] Flag wrappers: do NOT add `layout` prop (only FlagCard has it)
- → verify: Briefing reveals section by section. Neutral headings. Flags slide in. No AnimatePresence used.
- ⛔ blocked by: 5.1, 7.1

---

## 9. Polish & Micro-interactions

### 9.1 Final Polish [M]
- [ ] Verify gold `::selection` highlight works
- [ ] Verify scrollbar styling (thin, themed)
- [ ] Test all animations for jank (60fps target)
- [ ] Test with OS "Reduce Motion" enabled — verify transforms skip, opacity still animates
- [ ] Verify dark theme contrast ratios (WCAG AA — use browser DevTools accessibility audit)
- [ ] Verify empty states render correctly with new theme
- [ ] Verify error states use `destructive` tokens consistently
- [ ] Verify flag card keyboard navigation (Tab, Enter, Space)
- [ ] Verify split pane keyboard resize (arrow keys on focused handle)
- → verify: All interactions smooth and accessible. No visual glitches. 60fps animations.
- ⛔ blocked by: 8.1

---

## Execution Sequence

### Phase 1: Foundation (Do First)
```
0.1 Animation Constants ─┐
                          ├─▶ 1.2 Dark Mode & Font & Motion ─▶ 1.3 Color Palette
1.1 Install Dependencies ─┘
```

### Phase 2: Layout (After Foundation)
```
1.3 ─▶ 2.1 Header ─┐
1.3 ─▶ 2.2 Sidebar ─┼─▶ 2.3 MainArea
```

### Phase 3: Components (Parallel After Foundation)
```
0.1 + 1.3 ─▶ 3.1 PatientCard ─▶ 3.2 PatientList Stagger
0.1 + 1.3 ─▶ 4.1 Patient Details Card Grid
0.1 + 1.3 ─▶ 5.1 Flag Card Expand
1.1 ─▶ 6.1 Loading Overlay ─▶ 6.2 Generate Button
```

### Phase 4: Integration (After Components)
```
4.1 + 5.1 + 6.2 ─▶ 7.1 Split Pane Layout
5.1 + 7.1 ─▶ 8.1 Briefing Theatrical Reveal
```

### Phase 5: Polish (Final)
```
8.1 ─▶ 9.1 Final Polish
```

---

## Parallel Execution Plan

### Agent 1: Theme & Layout
Execute in order:
1. Task 0.1 (Animation constants)
2. Tasks 1.1, 1.2, 1.3 (Foundation)
3. Tasks 2.1, 2.2, 2.3 (Layout shell)

### Agent 2: Components (after 1.3 complete)
Execute in order:
1. Tasks 3.1, 3.2 (Sidebar animations)
2. Task 4.1 (Patient details card grid)
3. Task 5.1 (Flag card expand)

### Agent 3: Loading & Integration (after Agent 2 complete)
Execute in order:
1. Tasks 6.1, 6.2 (Loading experience)
2. Task 7.1 (Split pane layout)
3. Task 8.1 (Briefing theatrical reveal)
4. Task 9.1 (Polish)

---

## Success Criteria for V2

- [ ] App renders with dark charcoal background and warm gold accents
- [ ] Inter font loads and renders correctly
- [ ] `prefers-reduced-motion: reduce` disables transform animations
- [ ] Patient list items animate in with staggered entrance
- [ ] Patient card selection shows gold border/background with spring animation
- [ ] Patient details render as 2-column card grid (labs full-width)
- [ ] Section headings are neutral (not gold) — gold reserved for actions/selection
- [ ] Generate Briefing button has gold glow effect
- [ ] Loading state shows cycling status messages with phase indicator and cancel button
- [ ] Briefing reveals theatrically (section by section, flags stagger)
- [ ] Flag cards collapse by default, expand on click/hover-delay/focus
- [ ] Flag cards have `aria-expanded` and keyboard support
- [ ] Split pane layout: briefing top, details bottom, 8px resizable divider
- [ ] Both split pane panels scroll independently
- [ ] Regenerate button works
- [ ] Error states display correctly with dark theme
- [ ] Empty states display correctly with dark theme
- [ ] `npm run build` — no TypeScript errors
- [ ] `npm run lint` — no lint errors

---

## Verification Commands

### Dependencies
```bash
cd frontend
npm ls motion react-resizable-panels @fontsource-variable/inter
```

### Build & Lint
```bash
cd frontend
npm run build    # No TypeScript errors
npm run lint     # No lint errors
```

### Manual Testing
```bash
cd frontend
npm run dev
# Open http://localhost:5173
# 1. Verify dark theme + gold accents (not pure black — charcoal)
# 2. Watch patient list stagger animation on load
# 3. Hover patient cards → scale animation
# 4. Select patient → gold selection state
# 5. See patient details as 2-col card grid (labs full-width)
# 6. Click Generate → theatrical loading overlay with phase indicator
# 7. Click Cancel → loading stops
# 8. Wait for briefing → section-by-section reveal
# 9. Click flag cards → expand in-place
# 10. Tab to flag card → Enter → expands (keyboard)
# 11. Drag split pane divider → both panels resize
# 12. Click Regenerate → loading state → new briefing
# 13. Switch patients → briefing resets cleanly
# 14. Test error states (stop backend, retry)
# 15. Enable OS "Reduce Motion" → verify animations skip
```
