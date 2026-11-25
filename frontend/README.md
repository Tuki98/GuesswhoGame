# Guess the Character — Frontend

React + TypeScript (strict) single-page client for the FastAPI backend. The
server is authoritative for rooms, characters, assignments, turns, and match
results; this app renders personalized state and sends explicit actions. It can
run from the Vite dev server or be served by FastAPI as a production build.

## Prerequisites

- Node.js 20 or newer (Vite 6 requires Node 18+, tested on 20/22)
- npm 10 or newer
- The backend running at `http://localhost:8000` (see the root `README.md`)

## Setup

```powershell
cd frontend
npm install

# Optional: point at another backend or WebSocket origin
Copy-Item .env.example .env.local

npm run dev
```

Vite serves the app at `http://localhost:5173`. The backend's default
`CORS_ORIGINS` already allows that origin.

## Environment

Vite exposes only variables prefixed with `VITE_` to browser code. Both values
are optional in development and match a local backend by default.

| Variable | Development default | Production default | Notes |
|---|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | page origin (empty string) | Backend origin without a trailing slash and without `/api`. |
| `VITE_WS_BASE_URL` | derived from the API origin (`http` → `ws`) | page origin (`wss://` on HTTPS) | WebSocket origin without `/ws`. Leave empty to derive it. |

For same-origin production hosting, run `npm run build` with both variables
unset (or empty) and point the backend's `FRONTEND_DIST_DIR` at `dist/`. The
bundle then uses the current hostname, so it works through ngrok without
rebuilding.

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Vite dev server with HMR |
| `npm run typecheck` | `tsc -b` across the app and Vite config projects |
| `npm run build` | Type-check, then produce `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run test` | Vitest run (jsdom + React Testing Library) |
| `npm run test:watch` | Vitest in watch mode |

## Architecture

```text
src/
├── api/          # fetch client, error mapping, typed endpoint wrappers, auth retry
├── components/
│   ├── game/     # match header, identity, opponents, Q&A, guess dialog, result
│   ├── layout/   # brand and page shell
│   ├── room/     # invite, players, settings, teams, characters, start panel
│   └── ui/       # button, card, fields, modal, badges, feedback, toasts
├── hooks/        # useRoomLive: one WebSocket orchestration point
├── lib/          # errors, formatting, ids, session storage, class names
├── pages/        # landing, create, join, room shell, lobby, game, 404
├── realtime/     # protocol validation, RoomSocket, singleton, action dispatch
├── stores/       # Zustand: auth, room, match, connection, pending, UI
├── test/         # setup, fixtures, fake socket/realtime doubles
├── types/        # REST and WebSocket contracts mirrored from the backend
├── config.ts     # API/WS origins, timeouts, frame/reconnect limits
├── App.tsx       # routes: /, /create, /join, /room/:code, /play, *
└── main.tsx
```

### State ownership

- `authStore` holds the tab-scoped session, bootstraps it on load, rotates
  credentials through `POST /api/sessions/reconnect`, and persists to
  `sessionStorage` only.
- `roomStore` holds the room, players, teams, characters, and pending REST
  flags. REST mutations update it; WebSocket broadcasts are applied through
  `useRoomLive`, and collections are refreshed after room snapshots.
- `matchStore` holds the personalized `MatchState`, paginated history, last
  sequence, end reason, and WebSocket match actions.
- `connectionStore` tracks `idle | connecting | connected | reconnecting |
  disconnected | expired` plus the attempt count.
- `pendingStore` tracks per-action request IDs and timeouts so buttons cannot
  double-submit.
- `uiStore` owns transient toasts.

`RoomShell` resets room/match state whenever the session's room changes, guards
`/room/:code` against a different room, and moves to `/play` when the server
reports an active match. `GamePage` renders the completion screen from
authoritative match state.

### REST vs WebSocket

| Operation | Transport |
|---|---|
| Create/join room, settings, teams, leave/close, remove player | REST |
| Character add (JSON or multipart image) and delete | REST |
| Match start, question, answer, guess, cancel | WebSocket |
| Read room/players/teams/characters and match state/history | REST |
| Live room, presence, character, and match events | WebSocket |

Match mutations use the socket because REST match routes do **not** broadcast
`match.started` or turn changes; using the socket keeps every client in sync.

### WebSocket lifecycle

- One socket per tab at
  `ws://<origin>/ws/rooms/{room_code}?token={session_token}`.
- Every action gets a fresh `crypto.randomUUID()` `request_id`; actions are
  never queued while offline, and duplicate sockets are never opened.
- Messages are schema-checked per event. Malformed frames surface a protocol
  error instead of updating state.
- Exponential backoff (1 s → 15 s cap, jitter-free, resettable via "Retry now").
- Close code `1008` triggers one credential rotation through the reconnect
  endpoint and a fresh URL. If rotation fails, the session is marked expired.
- On reconnect the server sends a personalized snapshot (`room.state` or
  `match.state`). The client then reconciles persisted events with
  `GET /api/matches/{id}/history?after_sequence=<last known>` and merges by
  sequence number. It never replays client actions or invents sequence numbers.
- Per-connection deduplication on the server means a retry after reconnect must
  use a new request ID and a new action; the client does not resend
  unknown-outcome actions.

### Authentication and security

- Session tokens live only in `sessionStorage` (tab-scoped). Reconnect tokens
  are used only to call the reconnect endpoint; nothing is written to
  `localStorage`.
- Tokens are never logged, rendered, put in analytics, or included in REST
  URLs. The WebSocket token is in the query string because browsers cannot set
  handshake headers; use TLS in production.
- `401`/`invalid_session` triggers exactly one automatic reconnect-and-retry.
  Permission and validation errors are never retried.
- The backend is authoritative: the UI never derives turns, ownership, winners,
  assignments, or opponent secrets locally. All actions are disabled while the
  socket is not connected, and server errors are mapped to safe messages that
  hide internal details.
- The backend never reveals a player's own assigned character
  (`identity_revealed` is always `false`), so the result screen shows winners
  and question history, not your identity.

### Screens and flows

1. **Landing** — create a room or join with a code.
2. **Create** — nickname, capacity, and individual/team mode.
3. **Join** — `/join?code=GTC-ABCD` normalizes the code; signed-in tabs warn
   before replacing the session.
4. **Lobby** (`/room/:code`) — invite link/code, presence and readiness, host
   settings, player removal, teams, and character management with drag-free
   image previews (client-side preview plus multipart upload).
5. **Match** (`/play`) — personalized identity card, visible opponents,
   turn-aware question composer, pending-question answer card, tabbed question
   timeline/history, guess dialog, cancellation, and roster.
6. **Result** — winner, end reason, question summary, and a return to the
   lobby; no secret identity is exposed.

Team mode reuses the same screens: recipients and participants become teams and
the identity card shows the team-scoped assignment.

### Testing

The suite runs entirely in jsdom with fake API modules, fake sockets, and a
fake realtime singleton; no test performs a network request.

- `src/api` — client errors/timeouts/multipart/media URLs and auth retry.
- `src/realtime` — protocol validation, socket lifecycle/backoff/auth rotation,
  and action dispatch.
- `src/stores` — session persistence/bootstrapping, match history pagination and
  merge, and LOCAL mutations.
- `src/hooks` — room, presence, match, error, and reconnect event handling.
- `src/components` and `src/pages` — permission-aware rendering, Q&A, guess,
  result, readiness, access guards, and form validation.

### Current limitations

- The invitation URL is composed client-side
  (`${origin}/join?code=${room.code}`) because the backend exposes no invitation
  URL field.
- The guess dialog narrows candidates by removing characters already visible as
  other participants' identities and characters contributed by the guessing
  player/team. This is a UX hint, not authority; the backend validates guesses.
- The pending question is rendered once in its dedicated answer card; the
  timeline filters that duplicate out while the result screen counts it in the
  recorded question history.
- Real-time delivery requires the backend's single-worker deployment. Multiple
  workers need a shared broker (out of scope).
- No offline action queue, i18n, or browser-driven end-to-end tests yet. The
  current suite is 131 tests across 17 files (Vitest + React Testing Library).
