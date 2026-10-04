# Design system

DocMind's interface is dark-first, calm and technical: glass surfaces over a near-black base, one cool accent, restrained motion, and a single meaningful 3D element. Everything is driven by CSS variables in `web/src/index.css`.

## Principles

- **Function first.** Effects must support a task: the upload glow says "drop here", the beam says "processing", the similarity bar explains a number.
- **One accent.** Cyan for interaction and focus; violet only as a secondary highlight (overlap in the chunk diagram, retrieval beams).
- **Glass where it means "surface",** for navigation, panels, cards and dialogs, not for every element.
- **Honest UI.** No fake progress, "Similarity" never "accuracy", clear empty and error states.

## Tokens

Defined on `:root`/`[data-theme="dark"]` and `[data-theme="light"]`, exposed to Tailwind via `@theme inline` (e.g. `bg-bg`, `text-fg-muted`, `border-line`).

| Token | Dark | Use |
|---|---|---|
| `--bg` / `--bg-2` / `--bg-3` | `#0b0c0f` / `#111318` / `#171a20` | base, secondary, elevated |
| `--surface` / `--surface-2` | white @ 3.5% / 6% | glass fills |
| `--surface-solid` | `#14161b` | dialogs, solid navigation |
| `--border` / `--border-strong` | white @ 8% / 15% | hairlines |
| `--fg` / `--fg-muted` / `--fg-faint` | `#ecebe6` / `#a1a2a8` / `#6e7077` | warm off-white text hierarchy |
| `--accent` (+ `-strong`, `-soft`, `-glow`) | `#67d0f5` | primary accent |
| `--accent-2` | `#b7a6f5` | secondary accent |
| `--success` / `--warning` / `--danger` | `#5fd4a3` / `#f2c66d` / `#f2837d` | status |

Light theme values are tuned for contrast on `#f4f3ef`.

## Surfaces

| Class | Recipe | Used for |
|---|---|---|
| `.glass` | `--surface` fill, `--border`, layered shadow, `blur(16px) saturate(140%)` | cards, panels, navigation at the top of the page |
| `.glass-strong` | 82% solid fill, `blur(22px)` | popovers, dialogs, composer |
| `.nav-solid` | 90% solid fill, `blur(24px)`, stronger shadow | navigation once the page scrolls, so content never shows through |
| `.gradient-border` | masked 1 px gradient ring | emphasis |
| `GlowCard` | glass + a cursor-following radial highlight (CSS variables, no React re-render) | document, result and component cards |

On screens narrower than 768 px, blur drops to 10 px and the grain is reduced.

## Atmosphere

- **Ambient light:** three static radial gradients behind everything (`.ambient`), with no blur filter.
- **Grid:** a faint 48 px grid fading out from the top (`.grid-pattern`).
- **Grain:** one static SVG `feTurbulence` tile at 3–4.5% opacity with overlay blending (`.noise-overlay`). It never animates.

## Typography

Geist Variable for UI, JetBrains Mono Variable for technical data (IDs, scores, page numbers, keyboard hints). Both are self-hosted.

| Role | Style |
|---|---|
| Display (hero) | 36–58 px, semibold, tight tracking, gradient on the key word |
| Page title | 24–30 px, semibold |
| Section / card title | 15 px semibold |
| Body | 14–15 px, relaxed leading |
| Metadata | 11–12 px, muted; eyebrows uppercase with wide tracking |
| Technical | mono 11–13 px |

## Motion

Shared tokens in `components/animations/motion.ts`:

| Token | Value | Use |
|---|---|---|
| `duration.fast` | 0.18 s | hover, press, exits |
| `duration.normal` | 0.32 s | state changes, list items, page transitions |
| `duration.slow` | 0.6 s | entrances, bar fills |
| `ease` | `[0.22, 1, 0.36, 1]` | fades and slides |
| `spring` | stiffness 380, damping 32 | navigation indicator, upload panel lift, save bar |
| `fadeUp`, `stagger()`, `listItem` | variants | entrances and lists |

Motion animates opacity, transform and blur only. Layout animation (`layoutId`, `layout`) is used for the navigation indicator and the sources list. The 3D scene runs slow, ambient movement only. Reduced motion (OS or in-app) disables decorative animation and the 3D scene.

## Components

shadcn-style, owned in `components/ui/`: `Button` (primary with optional shimmer, glass, ghost, outline, danger), `Badge`, `Kbd`, `Skeleton` (subtle shimmer), `Input`, `Segmented`, `StatusDot`, and Radix-based `Tooltip`, `Popover`, `Dialog`, `SheetContent`. Feedback: `ErrorState`, `EmptyState`, `DocumentIllustration`.
