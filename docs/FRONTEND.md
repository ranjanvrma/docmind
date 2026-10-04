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
│   ├── citations.ts        not-found sentence + abstention rule (mirrors the backend; badges use the server's `grounding`)
│   ├── queries.ts          TanStack Query hooks
│   ├── preferences.ts      theme, motion (browser storage; no credentials)
│   ├── events.ts           tiny signal: scene-pulse
│   ├── format.ts, types.ts, utils.ts
├── components/
│   ├── ui/                 button, primitives, overlays, feedback (shadcn-style)
│   ├── layout/             AppShell, PreferencesProvider
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
| `/` | Hero with the 3D scene and the visitor's own stats (their documents and indexed passages from `/api/documents`; Q&A enabled or search only from `/api/health`), upload panel, recent documents, "How it works" pipeline |
| `/documents` | Library with name/category filter and status filter; upload panel; empty state |
| `/documents/:id` | Metadata, warnings, classification scores, indexed passages grouped by page; `?page=n` scrolls to and highlights a page (citation deep links) |
| `/search` | Semantic search (Ctrl/⌘ K), document filter, top-k, ranked results with similarity bars |
| `/ask` | Conversation with interactive citations and a sources panel; a badge per answer from the server's `grounding` ("Grounded · N sources cited", "Not found in your documents", "Could not be verified"); an unverified model reply appears only in a collapsed "Show unverified reply" disclosure, as plain text; honest "unavailable" state without an LLM |
| `/settings` | Visitors: only "This browser" (theme, motion), a note that server settings are managed by the administrator, and an "Administrator sign-in" link. After admin sign-in: model, retrieval & indexing (live chunk diagram), Evaluation lab, classification labels, limits. The admin's "Re-index now" re-indexes only the admin's own session documents; visitors' documents keep their old chunks until re-processed. |
| `/about` | Architecture, components, what DocMind does not claim |

## Data flow and API communication

- Every request goes to the same origin under `/api` with `credentials: "same-origin"`. Visitor requests carry **no token**: the server's HttpOnly session cookie is sent automatically, and JavaScript never sees it (`lib/api.ts`).
- The administrator token is kept in a module variable for the current page only (never in `localStorage` or `sessionStorage`) and is sent as `X-API-Key` only to `/api/admin/*`; reloading signs out. `preferences.ts` removes the `docmind.token` key that older versions stored. There is no token dialog any more.
- Error mapping (`lib/errors.ts`): `429` shows "Too many requests. Please try again in N seconds/minutes." (from `Retry-After`) plus the server's detail; `409` (document quota) and `503` "at capacity" have friendly messages; `401` means administrator access is required.
- The upload panel tells visitors: "Private to this browser · deleted after 24 h of inactivity or when the server restarts" (the hours come from `session_ttl_hours` in `/api/health`).
- Upload uses `XMLHttpRequest` to report **real** byte progress. Processing then runs in the background on the server (`POST /api/documents/process` with `"background": true`, answered with `202`). Each upload result follows the document's live status: *Queued for processing…*, *Extracting, embedding and indexing…*, *Indexed N chunks*, or the error. There is no per-stage progress from the server, so the processing stages are shown as one indeterminate step rather than invented percentages.
- TanStack Query caches `health` (refreshed every 20 s), `documents`, document details, chunks and (for the administrator) settings; mutations invalidate what they affect. The document list is polled every 1.5 s, but only while a document is `queued` or `processing`.

## Code splitting

Every route except Home is loaded on demand with React Router's `lazy`. The main chunk is 92 KB gzipped (229 KB before splitting). The home page still loads shared chunks, about 211 KB gzipped on first load. The 3D hero chunk (about 243 KB gzipped) is loaded only on the home page, and only on desktop widths (≥ 768 px) with motion allowed and WebGL available.

## Untrusted content

Document text and LLM answers are always rendered as React text. Answers use `lib/markdown.ts`, which outputs plain data for a small Markdown subset and never produces links, images or HTML. See [SECURITY.md](SECURITY.md).

## 3D scene

`KnowledgeScene` shows a stack of document sheets (the corpus) inside a shell of connected semantic nodes (the embedding space), with retrieval beams that brighten on uploads, searches and answers.
- **Lightweight:** one canvas, shared geometries and materials, an instanced mesh for nodes, single draw calls for links and particles, no post-processing.
- **No re-renders:** animation runs in `useFrame` without React state, and the loop is paused when the hero is off-screen or the tab is hidden.
- **Lazy-loaded:** three.js loads only on the home page, and only when the 3D scene will actually be shown.
- **Fallbacks:** `HeroVisual` uses the static CSS `SceneFallback` instead when WebGL is unavailable, reduced motion is on, or the viewport is narrower than 768 px.

## Accessibility

- **Structure:** semantic landmarks, a skip link, and visible accent focus rings (`:focus-visible`).
- **Controls:** labelled controls, `aria-live` for streaming states, and Radix primitives for dialogs, popovers and tooltips (focus management, Escape to close).
- **Keyboard:** citation chips open on focus, and the upload zone has a "Browse files" button for keyboard users.
- **Reduced motion:** the OS setting or the in-app setting disables decorative animation and the 3D scene. CSS transitions become instant and Motion is configured with `reducedMotion="always"`.
- **Small screens:** single-column grids use `grid-cols-1` (`minmax(0, 1fr)`), so long filenames no longer make cards wider than a 375 px screen.

## Commands

```bash
cd web
npm install
npm run dev         # http://localhost:5173, proxies /api to DOCMIND_API_URL (default http://127.0.0.1:8000)
npm run typecheck
npm test            # 48 tests
npm run build       # web/dist (served by the API)
```
