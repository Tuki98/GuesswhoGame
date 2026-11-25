# Architecture

## Goals

The backend is a modular monolith. Business rules will live in a game engine that
does not depend on FastAPI, HTTP requests, or WebSocket handlers. Phase 1
establishes those boundaries; Phase 3 adds the room character collection and its
image pipeline on top of them; Phase 4 adds the game engine (secure assignment,
turns, questions and answers, guesses, events, and personalized state). The
phase keeps the same dependency direction: services depend on models and
repositories, repositories on SQLAlchemy models, and core on no application
code.

## Layers and dependency direction

```text
app.main (app factory)
   ├── app.api           HTTP routes, dependencies, error envelope
   ├── app.schemas       Pydantic request/response contracts
   ├── app.services      room, session, character, and permission business rules
   ├── app.repositories  framework-free data-access queries
   ├── app.core          settings, errors, tokens, nicknames, images, media, URL safety
   ├── app.database      engine, sessions, declarative base
   └── app.models        SQLAlchemy domain entities
```

Dependencies point inward:

- `models` and `core` do not import FastAPI.
- `repositories` depend only on SQLAlchemy models and sessions.
- `services` depend on `core`, `models`, and `repositories`; they never import
  FastAPI/Starlette, so room, character, and future game rules are testable in
  isolation.
- `api` depends on all inner layers and translates domain errors into HTTP.

Transaction boundaries live in services. Routes never call `commit` or
`rollback`; they validate HTTP input, invoke one service operation, and map the
result to a response schema.

`create_app(settings)` returns a fresh application with its own `Database`
instance. Settings and the engine are stored on `app.state`, so tests can inject
an isolated in-memory database without module-level global state.

## Persistence

SQLAlchemy 2.x declarative models use UUID primary keys and UTC timestamps. The
`UTCDateTime` type decorator stores naive UTC values in SQLite and returns
timezone-aware UTC datetimes to application code.

| Table | Purpose | Key integrity rules |
|---|---|---|
| `rooms` | Private lobby and configuration | Unique invitation code; `waiting`/`in_progress`/`closed` status |
| `players` | Nickname-scoped participant | Unique case-folded nickname key per room; unique session/reconnect token hashes; absolute session expiry; FK to room/team |
| `teams` | Team-mode container | Unique name per room |
| `characters` | Room's shared character pool | Unique normalized `(room_id, name_key, franchise_key)`; required category enum; name/image path non-blank; FK to room/contributor |
| `matches` | A play session | Non-negative turn index; at most one winner; monotonic `event_sequence` counter |
| `assignments` | Secret identity mappings | Exactly one of player/team; unique character, player, and team per match |
| `questions` | Question/answer within a match | Exactly one recipient at a time; pending question unique per match; answer state complete |
| `game_events` | Ordered, append-only event log | Positive, unique sequence per match |

SQLite foreign key enforcement is enabled per connection via a `PRAGMA`. Cascades
remove room-owned data, while assigned characters use `ON DELETE RESTRICT` so a
frozen match collection cannot lose an assigned character.

### Intentional circular foreign keys

`rooms.host_player_id` references `players.id`, while `players.room_id`
references `rooms.id`. SQLite supports circular foreign keys, so the database
constraint is retained. `RoomService.create_room` inserts the room with a
nullable host, inserts the host player, then assigns `host_player_id` — all in
one transaction. Code and credential collisions roll back the whole attempt and
retry, so no partial room or orphan player can survive a failure. SQLAlchemy
emits a table-sort warning for this cycle; the test configuration suppresses
only that warning, not other SQLAlchemy warnings.

### Configuration JSON

Room, match, character, and event configuration/payload columns use mutable JSON.
Alembic stores them as plain `JSON`, and the ORM tracks in-place mutations.
`rooms.configuration` is validated through the framework-free `RoomConfig`
model (`max_players` 2–16, default 8; `game_mode` individual/team) and exposed
to clients as `settings`.

### Character collection and media pipeline

Phase 3 keeps all character rules in `CharacterService`, which has no HTTP
dependency. `app.core.characters` owns name/franchise normalization, category
coercion, attribute validation, and key derivation. `CharacterRepository`
performs room-scoped reads and the unique-key probe; the database unique
constraint is the final arbiter under races.

Character identity stores a display form and a comparison key. `name_key` and
`franchise_key` are NFKC-normalized, case-folded, whitespace-collapsed strings;
missing franchise uses an empty key. The unique constraint is
`(room_id, name_key, franchise_key)`, so the same character may exist in
different rooms but not twice in one room. Keys are capped at 240 characters to
absorb case-fold/NFKC expansion.

Images pass through one pipeline regardless of source:

1. `app.core.images` streams the source through a byte cap, decodes with Pillow,
   enforces a 20-megapixel cap, resizes to at most 1600 px, and re-encodes as
   WebP. Re-encoding strips metadata and rejects polyglots and renamed files.
2. `app.core.media` writes the bytes to a server-generated
   `characters/<uuid>.webp` path under `MEDIA_ROOT`. It rejects empty data and
   verifies on deletion that the resolved target stays inside the characters
   directory, blocking traversal and symlink escapes.
3. `app.core.url_safety` and `app.core.image_download` handle external URLs:
   only HTTP/HTTPS on ports 80/443, hostnames are IDNA-normalized, credentials
   are rejected, internal suffixes and non-public addresses are refused, DNS is
   resolved once, and the socket is pinned to the validated IP. HTTPS keeps SNI
   and certificate verification against the original hostname. Redirects are
   followed manually, re-validated per hop, limited to three, and HTTPS→HTTP
   redirects are rejected.

`image_path` remains internal. Responses build `image_url` from
`MediaStorage.public_url`, and `create_app` mounts `MEDIA_ROOT` at
`MEDIA_URL_PREFIX` with `StaticFiles`. The route stores the file before the
database insert and removes it on any commit failure; deletion commits the row
first, then removes the file and logs cleanup failures.

## Security invariants

These must remain true in every later phase:

1. A player's own secret character is never included in any API response,
   WebSocket message, log, or browser-visible state.
2. Personalized game state is built server-side per authenticated player/team.
3. The complete assignment table is never sent to clients.
4. Session and reconnect tokens are stored only as keyed hashes. Raw tokens are
   returned once at create/join/reconnect and never persisted.
5. Every protected route resolves the player from the bearer token; client
   supplied player/team IDs are never trusted for authorization.
6. Room reads require membership. Non-members receive `404`, not `403`, so room
   existence cannot be enumerated. Host-only writes require
   `rooms.host_player_id` to equal the authenticated player.
7. Session expiry is absolute (`players.session_expires_at`) and checked on
   every request. Reconnection uses a separate, longer-lived credential that is
   rotated by a compare-and-swap update; the old session and reconnect tokens
   both become invalid.
8. Guesses are validated against server-side assignments (Phase 4).
9. Duplicate/replayed commands are rejected or idempotently handled.
10. Unexpected exceptions return a generic error envelope; internal paths,
    database URLs, and secrets are never sent to clients.
11. Production refuses to start with development defaults or wildcard CORS.
12. Uploaded and downloaded images are validated by decoded content, byte- and
    pixel-capped, and stored under generated filenames. Client filenames,
    extensions, and content types are never trusted.
13. Outbound image requests resolve DNS once, validate every address, pin the
    connection to the validated IP, re-validate each redirect, and reject
    non-public destinations. This blocks SSRF and DNS rebinding.
14. A character's contributor is always the authenticated player. Client input
    cannot set `contributed_by`, and deletion authorization uses the stored
    contributor plus `rooms.host_player_id`.
15. Internal filesystem paths and media roots never appear in API responses;
    only `image_url` under the configured public prefix is exposed.
16. WebSocket connections authenticate the session and verify room membership
    before `accept()`. Every rejection uses close code `1008` with no frame, so a
    socket cannot probe token or room state.
17. Every WebSocket action delegates to the same services as REST and resolves
    its actor from the connection's authenticated player. Outgoing payloads are
    serialized per recipient: own secret assignments, team secrets, private
    questions, tokens, and assignment rows are never broadcast.
18. WebSocket frames are JSON text capped at 8 KB, schema-validated per event,
    and deduplicated by `request_id` for the life of a connection. Presence and
    heartbeats are transient and never persisted as `GameEvent` rows.

## API conventions

- All REST routes are under `/api`. The real-time endpoint is `/ws/rooms/{room_code}`
  because browser WebSocket handshakes cannot set an `Authorization` header.
- Errors always use `{"error": {"code": "...", "message": "...", "details": ...}}`.
- Protected routes use `Authorization: Bearer <session_token>`. Authentication
  failures return `401 invalid_session` with `WWW-Authenticate: Bearer`; missing,
  malformed, expired, and revoked tokens are deliberately indistinguishable.
- Health endpoints:
  - `GET /api/health` returns service metadata; never touches the database.
  - `GET /api/health/ready` executes `SELECT 1`; returns `503` if unavailable.
- Room endpoints:
  - Create/join return `201`/`200` with room, public player, and credentials.
  - Room and participant reads require membership.
  - Host-only settings, removal, and close return `403` for authenticated
    non-hosts.
  - Joining a closed, in-progress, or full room returns `409`.
  - `DELETE` participant and `POST` leave return `204`.
- Public player responses contain only `id`, `nickname`, `is_host`,
  `is_connected`, `is_ready`, and `joined_at`. Token hashes and raw credentials
  never appear outside create/join/reconnect responses.
- Character endpoints:
  - `POST /api/rooms/{room_id}/characters` accepts `application/json` (with
    `image_url`) or `multipart/form-data` (with an `image` part or text
    `image_url`) and returns `201`.
  - `GET` list/detail and `DELETE` return `200`/`204`; reads work in every room
    state, while create/delete require `waiting` (`409` otherwise).
  - Non-members receive `404`; deletion by a non-host non-contributor returns
    `403`; invalid fields, images, and URLs return `422`.
  - Responses expose `image_url`, never `image_path`.
- Media is served outside `/api` at `MEDIA_URL_PREFIX` by an unauthenticated
  static mount. UUID filenames act as capability URLs.

## Real-time WebSocket layer

The WebSocket package is a transport adapter over the existing services; it owns
no game rules.

- **Endpoint (`app/api/websockets.py`).** Reads the session token from
  `?token=`, calls `SessionService.authenticate`, resolves the room, and verifies
  `player.room_id`. Only then does it `accept()`. It registers the connection,
  sends one personalized snapshot, announces first-connection presence, and
  enters the receive loop. Malformed, oversized, unknown, duplicated, and
  unauthorized requests produce structured `error` events; unexpected failures
  produce a generic `internal_error` and drop the socket. Tokens are never
  echoed.
- **Protocol (`app/websockets/protocol.py`).** Defines the incoming/outgoing
  envelopes, event-name constants, per-event Pydantic payload models
  (`extra="forbid"`), and the 8192-byte frame cap. Envelope fields
  `event_id`/`sequence_number` are reserved for future server identifiers;
  persisted ordering remains owned by `GameEvent.sequence_number`.
- **Dispatcher and handlers (`app/websockets/handlers.py`).** Each event maps to
  a `RoomService`, `CharacterService`, or `MatchService` call. Handlers build
  recipient-specific events and return the direct response; room, player, and
  team broadcasts go through the connection manager. `match.start` returns a
  full personalized `match.state` to the host and a lightweight `match.started`
  to the room; questions and answers are delivered only to their authorized
  recipient or team.
- **Connection manager (`app/websockets/manager.py`).** In-memory dictionaries
  index connections by connection id, player, room, and team under an
  `asyncio.Lock`. `connect`/`disconnect`/`send`/`broadcast` are concurrency-safe.
  Presence is emitted on the first connection and the last disconnect only.
  Failed or closed sends are treated as stale: the connection is removed and, if
  it was the player's last, `player.disconnected` is broadcast. Each connection
  has one heartbeat task (`connection.heartbeat` every 30 s) that stops with the
  connection.
- **REST-to-WebSocket notifications.** REST joins, leaves/removals, settings
  changes, room close, and character create/delete broadcast `player.joined`,
  `player.left`, `room.updated`, `character.added`, and `character.deleted`, so
  clients observe one consistent room view regardless of transport.
- **Reconnection.** A reconnecting player is authenticated again, resolves the
  existing `Player` row (no duplicate membership), and receives `room.state` or,
  during a match, `match.state` built by the Phase 4 serializer. The client can
  then fetch missing persisted events from the REST history endpoint; no state
  is reconstructed from client-supplied secrets.
- **Deployment.** The manager lives in one process. The MVP must run a single
  Uvicorn worker. Multi-worker or multi-host fan-out would require a shared
  broker (Redis or PostgreSQL `LISTEN/NOTIFY`) and is explicitly out of scope
  for Phase 5.

## Frontend layer

- **Stack and structure.** The client is a Vite + React 18 + TypeScript
  (strict) SPA styled with Tailwind CSS and routed with React Router. Modules
  are split by responsibility: `types` mirror the REST and WebSocket schemas,
  `api` owns fetch, error mapping, and one-shot credential rotation,
  `realtime` owns the socket and envelope validation, `stores` hold Zustand
  state, `hooks/useRoomLive` applies server events, and `components`/`pages`
  render room and match views.
- **Authoritative server.** The client never computes assignments, turn
  ownership, permissions, or winners. It renders personalized `MatchState` and
  sends explicit actions. Match mutations (`match.start`, `question.submit`,
  `answer.submit`, `guess.submit`, `match.cancel`) use the WebSocket because
  REST match routes do not broadcast; lobby, team, and character changes use
  REST and rely on server broadcasts for fan-out.
- **Single socket.** `RoomSocket` opens exactly
  `/ws/rooms/{room_code}?token={session_token}`, refuses to create a duplicate
  while connecting or open, validates every incoming frame, assigns a fresh
  request ID to every outgoing action, caps frames at the server's limit, and
  applies exponential backoff with a reset control. Actions are never queued
  while disconnected.
- **Reconnection and reconciliation.** On reconnect the server sends
  `room.state` or `match.state`. The client then fetches persisted events with
  `after_sequence` set to the last known sequence and merges by sequence number.
  It does not replay actions or synthesize sequences. A `1008` close rotates
  credentials once through the reconnect endpoint; failure marks the session
  expired.
- **Session handling.** Sessions are tab-scoped in `sessionStorage`; reconnect
  tokens are used only against `POST /api/sessions/reconnect`. Nothing is
  written to `localStorage`, and tokens never enter logs, rendered markup, or
  REST query strings. `withAuth` retries exactly once after an invalid-session
  response and never retries permission or validation failures.
- **Rendering states.** Every screen handles loading, empty, disconnected,
  pending, and error states. Buttons that mutate server state are disabled while
  the socket is down; errors are mapped to safe user-facing messages.
- **Room scoping.** `RoomShell` resets room and match stores whenever the active
  session changes rooms, rejects a URL whose code differs from the session, and
  navigates to the match view when the server reports an active match.
- **Production hosting.** `create_app` serves the built SPA from
  `FRONTEND_DIST_DIR` when it contains `index.html`. `/assets` is mounted from
  the build, and a final catch-all returns files inside the resolved dist root
  or `index.html` for client-side routes. The fallback refuses the API prefix,
  the media prefix, `/ws`, `/docs`, `/redoc`, and `/openapi.json`, so API and
  transport behavior is unchanged. Production bundles default their REST and
  WebSocket bases to the page origin, which keeps HTTPS/WSS correct behind
  ngrok or any reverse proxy. The deployment is single-origin:
  `https://host/` (UI), `https://host/api`, `https://host/media`, and
  `wss://host/ws/...`.

## Testing approach

- **Unit:** settings validation, token generation/hashing, nickname
  normalization, room configuration, invitation codes, production guards,
  character normalization, image decode/limit/re-encode behavior, media path
  containment, URL/IP/DNS validation, and bounded download/redirect handling.
- **Integration:** HTTP health/error behavior, CORS, model constraints, cascades,
  foreign keys, mutable JSON, room lifecycle, host permissions, session
  authentication, reconnection rotation, concurrent capacity, character CRUD,
  duplicate/Unicode behavior, lifecycle freezes, deletion authorization,
  contributor tracking, and transaction cleanup; Alembic upgrade/downgrade,
  data conversion, and metadata parity.
- **Security:** persisted tokens are hashes; secrets, token hashes, and raw
  credentials do not appear in room reads or error responses; SSRF attempts,
  internal hosts, private DNS answers, and unsafe redirects are rejected.
- **WebSocket:** unit tests exercise the in-memory connection manager with fake
  sockets (multi-tab presence, room/player/team sends, failed-send cleanup,
  stale-connection protection, concurrency, and heartbeats). Integration tests
  use Starlette's synchronous `TestClient.websocket_connect` against the real ASGI
  app to cover pre-accept authentication rejection, protocol errors and size
  limits, request deduplication, room and character broadcasts, ready changes,
  full match flows (start, questions, answers, guesses, cancel), reconnect
  snapshots, REST/WS consistency, presence, team visibility, and secret/token
  non-leakage. A dedicated multi-client suite drives complete individual and
  team matches across independent socket clients, reconnect/history restoration,
  duplicate-frame rejection, and SPA hosting/reserved-prefix behavior. No
  WebSocket test opens a real network socket; the manual deployment probe used a
  real Uvicorn server and ngrok tunnel.
- Model tests build the schema from metadata; a separate test applies the real
  Alembic chain, asserts there is no metadata diff, and exercises data migration
  from Phase 1 to Phase 2 and from Phase 2 to Phase 3. This catches models and
  migrations drifting apart.
- **Frontend:** Vitest in jsdom with React Testing Library. Module mocks replace
  the API wrappers, a fake socket exercises `RoomSocket` lifecycle/backoff/auth
  rotation, and a fake realtime singleton records outgoing frames. Tests cover
  the fetch client and error mapping, auth retry/expiry, session bootstrapping,
  protocol validation, match-state and history reconciliation, room/presence/
  match event handling, disconnected-action guards, permission-aware rendering,
  question/answer/guess flows, result states, and route access guards. The
  backend suite is untouched by frontend tests.
- API tests use in-memory SQLite with `StaticPool`; the concurrent-capacity test
  uses a file-backed SQLite database so multiple writer connections serialize
  realistically. Dependencies are overridden only where a failure must be
  simulated. External image tests inject a fake DNS resolver and HTTP connection
  factory, so the suite never performs real DNS lookups or network requests.

## Assumptions recorded for later phases

- SQLite is the only database target for the MVP. Code avoids SQLite-only column
  types, but migrations use batch mode for SQLite.
- `characters.image_path` is required and stores a relative
  `characters/<uuid>.webp` path. External image URLs are downloaded at
  submission time and stored locally; remote content is never linked or trusted
  at read time.
- Character categories are a persisted enum with lowercase snake_case values.
  The migration coerces legacy free-text categories to `other` when they do not
  match a known value.
- Media files are served without authentication under UUID filenames. This is an
  accepted MVP capability-URL trade-off; authenticated media delivery is a
  future option if sharing becomes a concern.
- Outbound image downloads have a timeout and byte cap but no per-player rate
  limit. A production deployment should add one at the proxy or service layer.
- Image decoding is bounded at 20 megapixels and resized to 1600 px, but Pillow
  still decodes up to that bound. Stale temporary upload files are not swept
  periodically; the operating system or a future maintenance job must handle
  crashes that bypass normal cleanup.
- Nicknames are NFKC-normalized for display and case-folded into
  `players.nickname_key` for uniqueness. The display form keeps the player's
  capitalization and international characters.
- Session expiry is absolute and enforced by `SessionService.authenticate`.
  Reconnection always rotates both credentials; a disconnected player is never
  removed automatically.
- Invitation codes are `GTC-XXXX`, use an unambiguous alphabet, and are
  generated with `secrets.choice`. Collisions are retried up to eight times.
- Room capacity is enforced by an insert-then-recount inside the transaction,
  relying on SQLite writer serialization. A production database would need a
  row lock or a unique capacity mechanism.
- `is_connected` is set on create/join/reconnect. Phase 5 presence events are
  transport-level signals from the WebSocket connection manager; they do not
  rewrite `players.is_connected`, which remains authentication/lifecycle
  metadata.
- The WebSocket connection manager is in-memory and single-process. Running
  multiple Uvicorn workers would split presence and broadcasts; a shared broker
  is required before horizontal scaling. Session tokens appear in the WebSocket
  query string because browsers cannot set handshake headers, so deployments
  must use TLS and avoid logging full socket URLs.
