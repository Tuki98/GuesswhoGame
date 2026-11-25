# Guess the Character

A private, browser-based multiplayer game inspired by Guess Who? — except each
player must discover **their own** secret character by asking questions. Other
players can see your character; you cannot.

> **Project status:** Phases 1–7 (Backend Foundation, Room Management,
> Character Management, the Game Engine, real-time WebSockets, the React
> frontend, and testing/deployment readiness) are complete. The built React app
> is served by FastAPI on one origin, and the single-origin flow has been
> verified locally and through an ngrok HTTPS tunnel. Timers, AI behaviour, and
> browser-driven end-to-end tests are not implemented. See
> [Roadmap](#roadmap).

---

## Technology

| Layer | Choice |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Persistence | SQLAlchemy 2.x, SQLite, Alembic |
| Validation | Pydantic v2 / pydantic-settings |
| Images | Pillow (content validation and WebP re-encoding) |
| Tests | Pytest, pytest-cov, httpx2 (Starlette test client); Vitest + React Testing Library |
| Quality | Ruff, mypy (strict), TypeScript strict |
| Frontend | React 18, TypeScript 5.7, Vite 6, Tailwind CSS 3, React Router 7, Zustand |

## Repository layout

```text
.
├── backend/
│   ├── app/
│   │   ├── api/          # HTTP routes, dependencies, error translation
│   │   ├── core/         # Settings, errors, tokens, image/URL/media utilities
│   │   ├── database/     # Engine/session management, declarative base
│   │   ├── models/       # SQLAlchemy domain models and enums
│   │   ├── repositories/ # Framework-free data-access queries
│   │   ├── schemas/      # Pydantic API schemas
│   │   ├── services/     # Room, session, character, and permission rules
│   │   ├── websockets/   # WS protocol, connection manager, event handlers
│   │   └── main.py       # Application factory and ASGI entry point
│   ├── alembic/          # Migration environment and versions
│   ├── tests/            # unit / integration / security tests
│   ├── data/             # Local SQLite files (ignored by git)
│   ├── storage/          # Uploaded character images (ignored by git)
│   ├── alembic.ini
│   ├── pyproject.toml    # Pytest, coverage, Ruff, mypy configuration
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── src/
│   │   ├── api/          # fetch client, typed endpoints, auth retry
│   │   ├── components/   # ui / layout / room / game components
│   │   ├── hooks/        # useRoomLive WebSocket orchestration
│   │   ├── lib/          # errors, formatting, ids, session storage
│   │   ├── pages/        # landing, create, join, room, game, 404
│   │   ├── realtime/     # protocol, socket, singleton, action dispatch
│   │   ├── stores/       # Zustand state (auth, room, match, connection, UI)
│   │   ├── test/         # setup, fixtures, fake sockets/realtime
│   │   └── types/        # REST and WebSocket contracts
│   ├── .env.example
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts
├── docs/
│   ├── API.md
│   └── ARCHITECTURE.md
├── .env.example
├── .gitignore
├── README.md
└── development.md        # Full project specification
```

## Local setup

Prerequisites: Python 3.11+ for the backend and Node.js 20+ (npm 10+) for the
frontend. Run each side in its own terminal.

### Backend

```powershell
# From the repository root
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install backend dependencies
pip install -r backend\requirements-dev.txt

# Create local configuration (root .env is read when running from backend/)
Copy-Item .env.example .env
# Edit .env and set a random SECRET_KEY:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"

# Create/upgrade the SQLite schema
cd backend
..\.venv\Scripts\alembic.exe upgrade head

# Run the API
..\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`, interactive docs at
`http://localhost:8000/docs`, and health checks at:

- `GET /api/health` — liveness
- `GET /api/health/ready` — database readiness

### Frontend

```powershell
# In a second terminal, from the repository root
cd frontend
npm install

# Optional: override the API/WebSocket origins
Copy-Item .env.example .env.local

# Run the Vite dev server
npm run dev
```

The app opens at `http://localhost:5173`; the default backend CORS
configuration already allows that origin. See
[frontend/README.md](frontend/README.md) for routes, architecture, state
ownership, and the WebSocket lifecycle.

## Production build and single-origin deployment

FastAPI serves the compiled SPA when `FRONTEND_DIST_DIR` points at a directory
containing `index.html`. REST (`/api`), media (`/media`), WebSockets (`/ws`),
and the framework routes (`/docs`, `/redoc`, `/openapi.json`) are registered
first and are never shadowed by the SPA fallback, so unknown API paths still
return JSON `404` instead of the HTML shell.

```powershell
# 1. Build the frontend (from the repository root)
cd frontend
npm ci
npm run build

# 2. Start the production backend (from backend/)
cd ..\backend
$env:ENVIRONMENT = "production"
$env:SECRET_KEY = (..\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))")
$env:FRONTEND_DIST_DIR = "../frontend/dist"
..\.venv\Scripts\alembic.exe upgrade head
..\.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. The same origin now serves the UI, REST API,
uploaded images, and the `/ws/rooms/{room_code}` WebSocket endpoint.

Production builds default `VITE_API_BASE_URL` to the page origin, so the
bundle works behind any hostname (including ngrok). Setting the variable
explicitly to an empty string has the same effect; setting it to another origin
keeps the split frontend/backend deployment. If `FRONTEND_DIST_DIR` is unset or
does not contain `index.html`, FastAPI runs API-only and the SPA routes return
`404`.

The SQLite database (`backend/data/`) and uploaded images
(`backend/storage/characters/`) survive restarts because they live on disk.
Keep both directories persistent when deploying, and back up the database
before upgrades.

## Feature history

Phase 2 adds private rooms and player sessions. All room routes require
`Authorization: Bearer <session_token>`:

- `POST /api/rooms` — create a room and become its host
- `POST /api/rooms/join` — join a waiting room by invitation code
- `GET /api/rooms/{room_id}` — read public room information
- `GET /api/rooms/{room_id}/players` — list participants
- `PATCH /api/rooms/{room_id}/settings` — update settings (host only)
- `DELETE /api/rooms/{room_id}/players/{player_id}` — remove a participant (host only)
- `POST /api/rooms/{room_id}/leave` — leave a room
- `POST /api/rooms/{room_id}/close` — close a room (host only)
- `POST /api/sessions/reconnect` — rotate credentials using a reconnect token

Raw session and reconnect tokens are returned only by create, join, and
reconnect. See [docs/API.md](docs/API.md) for request/response examples.

Phase 3 adds the room character collection. All character routes require
membership and accept a JSON body or a multipart form:

- `POST /api/rooms/{room_id}/characters` — add a character (image upload or URL)
- `GET /api/rooms/{room_id}/characters` — list the room's characters
- `GET /api/rooms/{room_id}/characters/{character_id}` — read one character
- `DELETE /api/rooms/{room_id}/characters/{character_id}` — remove a character
  while the room is waiting (host or contributor)

Character creation and deletion are allowed only while the room status is
`waiting`; reads work in every room state. Uploaded and downloaded images are
decoded, size- and pixel-capped, and re-encoded as WebP under generated
filenames. The API returns a `/media/characters/<uuid>.webp` URL, never a
filesystem path.

Phase 4 adds the game engine behind the room and character foundations. The
service keeps assignment, turn, and event rules in inner layers and exposes:

- `POST /api/rooms/{room_id}/matches` — start a match (host only, from `waiting`)
- `GET /api/matches/{match_id}` — public match details and participants
- `GET /api/matches/{match_id}/state` — personalized state, opponents, pending question
- `POST /api/matches/{match_id}/questions` — ask on the active turn (max 500 chars)
- `POST /api/matches/{match_id}/questions/{question_id}/answer` — answer pending (max 1000 chars)
- `POST /api/matches/{match_id}/guesses` — guess a character (server-validated)
- `POST /api/matches/{match_id}/cancel` — cancel a match (host only)
- `GET /api/matches/{match_id}/history` — paginated events
- Team management: `POST /api/rooms/{room_id}/teams`,
  `GET /api/rooms/{room_id}/teams`,
  `PUT /api/rooms/{room_id}/players/{player_id}/team`

Match statuses reuse the existing Phase 1 enum values and are exposed with
clearer lifecycle names: `pending` → `created`, `active` → `in_progress`,
`finished` → `finished`, `abandoned` → `cancelled`.

Phase 5 adds real-time communication over WebSockets at:

```text
ws://localhost:8000/ws/rooms/{room_code}?token=<session_token>
```

The socket is authenticated and room-scoped before it is accepted. Clients send
`{"event", "request_id", "payload"}` envelopes and receive state, presence,
character, and match events. Match questions, answers, guesses, cancellation,
readiness, and character changes are delegated to the existing services, so REST
and WebSocket clients share validation and transaction rules. Each connection
first receives a personalized snapshot (`room.state` while waiting,
`match.state` during a match), and reconnecting restores the same player and
secret assignment. The in-memory connection manager supports multiple tabs per
player and runs in the single Uvicorn worker used by the MVP.

See [docs/API.md](docs/API.md#websocket-api---wsroomsroom_code) for the full
event list, payloads, error codes, and security notes.

Phase 6 adds the React frontend. It mirrors the backend contracts exactly and
covers the complete flow:

- **Landing, create, and join** — room code normalization, nickname validation,
  capacity and individual/team mode selection, and invitation links
  (`/join?code=GTC-ABCD`).
- **Lobby** — invite code/link, live presence and readiness, host settings,
  participant removal, team creation/assignment, and character management with
  URL or multipart image upload and client-side previews.
- **Match** — personalized identity card, visible opponents, turn-aware question
  composer, pending-answer card, question timeline and REST history, guess
  dialog, cancellation, and error feedback for individual and team modes.- **Results** — winner and end reason from authoritative match state, a question
  summary, and return to the lobby. The backend never reveals your own
  assignment (`identity_revealed` is always `false`), so results do not show it.

Match actions (`match.start`, `question.submit`, `answer.submit`, `guess.submit`,
`match.cancel`) travel over the WebSocket so every tab receives the broadcast
events; lobby, team, and character changes use REST. The client opens the exact
authenticated socket URL, assigns a unique `request_id` to every action, applies
schema validation to every frame, reconnects with exponential backoff, rotates
credentials once after a `1008` close, and reconciles persisted events through
`GET /api/matches/{id}/history?after_sequence=` without replaying actions. See
[frontend/README.md](frontend/README.md) for the architecture and setup details.

The default database file is `backend/data/guess_the_character.db`; character
images default to `backend/storage/characters/`.

### Public testing with ngrok

Build the frontend and start the production backend as described above, then
expose the single port:

```powershell
ngrok http 8000
```

Open the `https://…ngrok-free…` URL in a browser. Because the bundle uses the
page origin, REST, media, and WebSockets automatically use HTTPS/WSS; no
`localhost` URLs are baked into the production bundle.

Verified on 2026-11-18 with ngrok 3.39.11: the public HTTPS root and deep links
served the SPA, `/api/health` returned the production envelope, a real `wss://`
handshake returned `room.state`, a `room.get_state` round trip succeeded, and an
invalid token was rejected. Free ngrok plans show a one-time browser warning
page; add an `ngrok-skip-browser-warning: true` header for scripted probes (the
normal browser flow continues after clicking through the warning). The tunnel
URL changes on each restart unless a reserved domain is configured. Run a
single Uvicorn worker because the WebSocket registry is in-process.

## Configuration

Settings are read from environment variables and `.env` files. See
`.env.example` for all fields.

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | `development`, `test`, or `production` |
| `DEBUG` | `false` | Must be `false` in production |
| `SECRET_KEY` | dev placeholder | HMAC key for session tokens; ≥32 chars in production |
| `DATABASE_URL` | `sqlite:///./data/guess_the_character.db` | SQLAlchemy URL |
| `CORS_ORIGINS` | localhost:5173 origins | JSON array; wildcards rejected in production |
| `SESSION_TOKEN_TTL_HOURS` | `24` | 1–720 hours |
| `RECONNECT_TOKEN_TTL_HOURS` | `168` | 1–720 hours; must be ≥ session TTL |
| `MEDIA_ROOT` | `./storage` | Directory for validated character images |
| `MEDIA_URL_PREFIX` | `/media` | Public URL prefix; must start with `/` and not end with `/` |
| `FRONTEND_DIST_DIR` | unset | Directory containing the built `index.html`; enables same-origin SPA hosting |
| `IMAGE_MAX_BYTES` | `5242880` | Upload/download byte cap; 1 KB–5 MB |
| `IMAGE_DOWNLOAD_TIMEOUT_SECONDS` | `5` | Outbound image fetch timeout; ≤30 s |

Production startup fails fast if the default/short secret, debug mode, or a
wildcard CORS origin is used. In the single-origin deployment no cross-origin
requests occur, so `CORS_ORIGINS` may be set to `[]`; keep the Vite dev origin
only if you also run the separate development server.

## Database migrations

```powershell
cd backend

# Apply all migrations
..\.venv\Scripts\alembic.exe upgrade head

# Create a migration after changing models
..\.venv\Scripts\alembic.exe revision --autogenerate -m "describe change"

# Inspect applied revision
..\.venv\Scripts\alembic.exe current

# Roll back everything
..\.venv\Scripts\alembic.exe downgrade base
```

Migration `0002` converts Phase 1 room statuses (`lobby` → `waiting`,
`in_game` → `in_progress`, `finished` → `closed`), backfills case-insensitive
nickname keys and session expiry, and adds reconnect credentials. Migration
`0003` adds normalized character name/franchise keys, a required category enum,
and the per-room uniqueness constraint; it backfills keys for existing rows,
deduplicating collisions with a numeric suffix. Migration `0004_game_engine`
adds the `questions` table, the per-match `event_sequence` counter, and the
engine event types; it upgrades and downgrades cleanly.
The test suite verifies that the full migration chain produces exactly the model
metadata, upgrades and downgrades cleanly, and that existing Phase 1/2 rows are
converted safely.

## Tests and quality checks

Backend (from `backend/`):

```powershell
cd backend

..\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing
..\.venv\Scripts\ruff.exe check app tests alembic\env.py
..\.venv\Scripts\ruff.exe format --check app tests alembic\env.py
..\.venv\Scripts\mypy.exe app
```

Generated migrations under `alembic/versions` are excluded by the Ruff
configuration and are intentionally not passed on the command line; passing
them explicitly overrides the exclusion and reports pre-existing formatting
warnings in generated files.

Frontend (from `frontend/`):

```powershell
cd frontend

npm run test        # Vitest + React Testing Library
npm run typecheck   # TypeScript strict project build
npm run build       # Production bundle
```

The verified Phase 7 baseline is **440 backend tests at 95.65% coverage**
(threshold 90%) and **131 frontend tests in 17 files**. Coverage includes unit
tests (settings, token security, nickname normalization, room configuration,
invitation codes, character normalization, image validation, media paths,
URL/SSRF validation, bounded downloads, WebSocket connection manager, heartbeat,
presence, and send-failure cleanup), integration tests (health, error envelope,
schema constraints, cascades, migrations, room lifecycle, permissions,
concurrent capacity, reconnection, character CRUD, duplicates, cleanup,
WebSocket authentication, protocol validation, room broadcasts, individual and
team match flows, and reconnect synchronization), and security tests (tokens are
never stored in plaintext, server secrets and secret assignments never reach API
or WebSocket responses, cross-room sockets are rejected, replayed frames create
no duplicate events, and image requests cannot reach internal addresses).
`tests/integration/test_multi_client_integration.py` drives complete individual
and team matches over independent WebSocket clients plus real REST calls,
including reconnection, personalized state/history restoration, incorrect and
correct guesses, and duplicate-frame rejection. `test_frontend_hosting.py`
verifies SPA serving, reserved-prefix 404s, and path-traversal containment.
External image tests use a fake DNS resolver and HTTP transport; no backend test
performs a real network request.

Frontend coverage (131 tests in 17 files) includes the fetch client
(error envelopes, timeouts, multipart, media URLs), authorization retry and
session expiry, session persistence and bootstrapping, WebSocket envelope
validation, socket lifecycle/backoff/auth rotation, request-ID dispatch,
match-state and history pagination/merge, room and match event orchestration,
disconnected-action guards, permission-aware rendering, character and guess
dialogs, question/answer flows, result states, and route access guards. Tests
run in jsdom with fake API modules, sockets, and a fake realtime singleton; none
performs a network request.

## Security notes

- Session and reconnect tokens are 256-bit random values. Only HMAC-SHA256
  digests keyed by `SECRET_KEY` are stored; raw tokens are returned once at
  create/join/reconnect and are never persisted or logged by the backend.
- Every room read and write authenticates its bearer token and verifies
  membership; non-members receive `404` so room IDs cannot be enumerated.
  Host-only operations return `403` for authenticated non-hosts.
- Session expiry is absolute and enforced on every request. A separate,
  longer-lived reconnect credential rotates both tokens atomically on every
  reconnection, so two clients cannot share one player identity.
- Nicknames and character names are NFKC-normalized and compared with Unicode
  case folding and collapsed whitespace, preventing visually equivalent
  duplicates while allowing international names.
- Character images are validated by decoded content (JPEG/PNG/WebP only),
  capped at 5 MB and 20 megapixels, resized to at most 1600 px, and re-encoded as
  WebP with generated UUID filenames. Client filenames and content types are
  ignored.
- External image URLs must use HTTP/HTTPS on ports 80/443, resolve only to
  public addresses, and are downloaded with a timeout, a byte cap, and manual
  redirect re-validation. DNS is resolved once and the connection is pinned to
  the validated IP, blocking SSRF and DNS rebinding.
- Media files are served without authentication under unguessable UUID names, so
  the URL acts as a capability. Do not expose the media directory listing.
- When FastAPI serves the SPA, the fallback checks the resolved file against the
  dist root and refuses `/api`, `/media`, `/ws`, `/docs`, `/redoc`, and
  `/openapi.json`, so it cannot disclose files outside the build or turn API
  404s into HTML.
- `npm audit` reports **0 vulnerabilities** after upgrading Vitest to 4.1.12 and
  React Router to 7.18.6; the backend uses current pinned requirements with no
  reported security advisories. Run `npm audit` and `pip list --outdated`
  periodically.
- SQLite foreign keys are enabled on every connection.
- API errors use one envelope: `{"error": {"code", "message", "details"}}` and
  unexpected exceptions never expose internal details.
- Configuration secrets are held in `SecretStr` and masked in representations.
- Secret character assignments (Phase 4) must be validated and personalized
  server-side; the database schema enforces one owner per assignment and one
  character per owner/match.
- The WebSocket endpoint authenticates and checks room membership **before**
  accepting the socket; all failures close with code `1008` and send no detail.
  Every action resolves its actor from the connection's authenticated player, so
  clients cannot select another player or room.
- Incoming frames are capped at 8 KB, must be JSON text, and are schema-validated
  per event. `request_id` deduplication prevents retries from creating duplicate
  game events. `player.connected`/`player.disconnected` are transient presence
  signals and are never written to the persisted `GameEvent` history.
- Outgoing state is built by the Phase 4 personalized serializer. Own secret
  assignments, team secrets, other players' private questions, tokens, and
  internal assignment rows are never broadcast.
- The session token travels in the WebSocket query string because browsers cannot
  set handshake headers. Use TLS in production and avoid logging full socket
  URLs; never put the long-lived reconnect token in the URL.
- The frontend keeps sessions in `sessionStorage` (tab-scoped) and never writes
  tokens to `localStorage`, logs, or REST URLs. A `401` rotates credentials once
  through the reconnect endpoint; permission and validation errors are never
  retried. The UI disables actions while disconnected, hides internal error
  details, and never derives assignments, turns, or winners locally.
- The connection manager is in-memory and per-process. Run a single Uvicorn
  worker; multi-worker or multi-host deployments need a shared broker, which is
  out of scope until a later phase.

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| 1 | Backend foundation: app factory, settings, SQLAlchemy, SQLite, Alembic, models, health, tests | ✅ Complete |
| 2 | Room creation, invitation codes, joining, lobby, host permissions, sessions, reconnection | ✅ Complete |
| 3 | Character collection, image upload/URL support, duplicate prevention | ✅ Complete |
| 4 | Game engine: assignment, turns, questions/answers, guesses, victory, teams | ✅ Complete (backend) |
| 5 | WebSocket manager, authentication, events, personalized state, reconnection | ✅ Complete |
| 6 | React frontend: landing, lobby, collection, game, results, WS reconnection | ✅ Complete |
| 7 | Testing/security validation, frontend build served by FastAPI, single-origin ngrok deployment | ✅ Complete |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design decisions and the
security invariants that later phases must preserve.
