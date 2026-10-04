# Frontend

The web UI is a React + TypeScript single-page app in `web/`, built with Vite. In production FastAPI serves `web/dist` at `/`; in development Vite serves it and proxies `/api` to the backend.

## Stack (and why each piece is there)

| Package | Purpose |
|---|---|
| React 19, TypeScript, Vite | App, types, dev server and build |
| Tailwind CSS v4 | Utility styling on top of the design tokens ([DESIGN_SYSTEM.md](DESIGN_SYSTEM.md)) |
| Radix (`dialog`, `popover`, `tooltip`, `slot`) | Accessible primitives behind the shadcn-style components in `components/ui/` |
| `motion` (Motion for React) | Page, list, layout and state animations, with shared tokens |
| `@react-three/fiber` + `three` | The 3D hero scene (lazy-loaded) |
| TanStack Query | Server state: caching, refetching, mutations |
| React Router | Routes |
| `lucide-react` | Icons |
| `sonner` | Toasts |
| `@fontsource-variable/geist`, `…/jetbrains-mono` | Self-hosted fonts (no third-party requests) |
| `class-variance-authority`, `clsx`, `tailwind-merge` | Component variants and class merging (shadcn convention) |
| Vitest, Testing Library, jsdom (dev) | Unit and component tests |

The visual effects modelled on Aceternity UI and Magic UI patterns (spotlight, moving border, cursor-following glow card, grain texture) are small in-repo components in `components/effects/`, not extra libraries.

## Structure

```
web/src/
├── App.tsx                 providers + routes
├── main.tsx                fonts, CSS, theme/motion before first paint
├── index.css               design tokens, glass, noise, grid, reduced motion
├── lib/                    no React components:
│   ├── api.ts              typed API client (fetch; XHR for upload progress)
│   ├── errors.ts           ApiError + friendly messages (5xx details never shown)
│   ├── markdown.ts         safe Markdown subset + citation parsing
│   ├── citations.ts        abstention rule (mirrors the backend)
│   ├── queries.ts          TanStack Query hooks
│   ├── preferences.ts      theme, motion, access token (browser storage)
│   ├── events.ts           tiny signals: auth-required, scene-pulse
│   ├── format.ts, types.ts, utils.ts
├── components/
│   ├── ui/                 button, primitives, overlays, feedback (shadcn-style)
│   ├── layout/             AppShell, PreferencesProvider, AuthDialog
│   ├── navigation/         NavBar (glass → solid on scroll), Logo, StatusIndicator
│   ├── hero/               Hero, HowItWorks
│   ├── 3d/                 KnowledgeScene (R3F), HeroVisual (picks 3D or fallback), SceneFallback
│   ├── effects/            Background (ambient, grid, grain, spotlight, moving border), GlowCard
│   ├── animations/         motion tokens
│   ├── upload/             UploadZone, PipelineProgress
│   ├── documents/          cards, grid, status, delete dialog, classification bars
│   ├── search/             result card, similarity bar, document filter
│   ├── qa/                 ChatProvider, ChatTurnView, AnswerContent, AskComposer
│   ├── citations/          CitationChip
│   ├── sources/            SourcesPanel
│   └── settings/           controls, ApiKeyField, EvaluationLab
└── pages/                  Home, Documents, DocumentDetail, Search, Ask, Settings, About, NotFound
```

Business logic (API calls, parsing, error mapping) lives in `lib/`; components render and wire it up; 3D and effects are isolated.

## Views

| Route | What it shows |
|---|---|
| `/` | Hero with the 3D scene, upload panel, recent documents, "How it works" pipeline |
| `/documents` | Library with name/category filter and status filter; upload panel; empty state |
| `/documents/:id` | Metadata, warnings, classification scores, indexed passages grouped by page; `?page=n` scrolls to and highlights a page (citation deep links) |
| `/search` | Semantic search (Ctrl/⌘ K), document filter, top-k, ranked results with similarity bars |
| `/ask` | Conversation with interactive citations and a sources panel; honest "unavailable" state without an LLM |
| `/settings` | Model, retrieval & indexing (live chunk diagram), Evaluation lab, classification labels, limits, browser preferences |
| `/about` | Architecture, components, what DocMind does not claim |

## Data flow and API communication

- Every request goes to the same origin under `/api`. If a token is stored, `X-API-Key` is added (`lib/api.ts`).
- A `401` emits `auth-required`, which opens the token dialog. If `/api/health` says `auth_required` and no token is stored, the dialog opens immediately.
- Upload uses `XMLHttpRequest` to report **real** byte progress. Processing is a single request without progress, so the pipeline view shows the remaining stages as one indeterminate step rather than inventing percentages.
- TanStack Query caches `health` (refreshed every 20 s), `documents`, document details, chunks and settings; mutations invalidate what they affect.

## Untrusted content

Document text and LLM answers are always rendered as React text. Answers use `lib/markdown.ts`, which outputs plain data for a small Markdown subset and never produces links, images or HTML. See [SECURITY.md](SECURITY.md).

## 3D scene

`KnowledgeScene` shows a stack of document sheets (the corpus) inside a shell of connected semantic nodes (the embedding space), with retrieval beams that brighten on uploads, searches and answers.
- **Lightweight:** one canvas, shared geometries and materials, an instanced mesh for nodes, single draw calls for links and particles, no post-processing.
- **No re-renders:** animation runs in `useFrame` without React state, and the loop is paused when the hero is off-screen or the tab is hidden.
- **Lazy-loaded:** three.js loads only on the home page.
- **Fallbacks:** `HeroVisual` uses the static CSS `SceneFallback` instead when WebGL is unavailable, reduced motion is on, or the viewport is narrower than 768 px.

## Accessibility

- **Structure:** semantic landmarks, a skip link, and visible accent focus rings (`:focus-visible`).
- **Controls:** labelled controls, `aria-live` for streaming states, and Radix primitives for dialogs, popovers and tooltips (focus management, Escape to close).
- **Keyboard:** citation chips open on focus, and the upload zone has a "Browse files" button for keyboard users.
- **Reduced motion:** the OS setting or the in-app setting disables decorative animation and the 3D scene. CSS transitions become instant and Motion is configured with `reducedMotion="always"`.

## Commands

```bash
cd web
npm install
npm run dev         # http://localhost:5173, proxies /api to DOCMIND_API_URL (default http://127.0.0.1:8000)
npm run typecheck
npm test            # 34 tests
npm run build       # web/dist (served by the API)
```
