# API Reference - Phase 5

All routes are prefixed with `/api`. Interactive OpenAPI documentation is served
at `/docs` and `/openapi.json`.

## Authentication

Protected routes require a bearer session token:

```http
Authorization: Bearer <session_token>
```

Session tokens are issued only by room creation, room joining, and reconnection.
They are opaque 256-bit values; the server stores an HMAC-SHA256 hash keyed by
`SECRET_KEY`. Every request checks that the session exists and that
`session_expires_at` is in the future.

Authentication failures all return the same response so callers cannot tell
whether a token is missing, malformed, expired, or revoked:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/json

{"error": {"code": "invalid_session", "message": "Your session is invalid or has expired."}}
```

## Error envelope

Every error uses one shape:

```json
{
  "error": {
    "code": "conflict",
    "message": "This room is full.",
    "details": null
  }
}
```

`details` is omitted or contains validation details. Unexpected exceptions never
expose database internals, stack traces, or secrets.

| Status | Typical code | Meaning |
|---|---|---|
| 400 | `bad_request` | Malformed request that is not a validation error |
| 401 | `invalid_session` | Missing, malformed, expired, or revoked credentials |
| 403 | `permission_denied` | Authenticated but not allowed (host-only action, or character deletion by a non-host non-contributor) |
| 404 | `not_found` | Unknown room/code/player/character, or room you are not a member of |
| 409 | `conflict` | Room state, capacity, nickname, duplicate character, or host-protection conflict |
| 422 | `validation_error` | Invalid nickname, settings, character fields, image, or URL |

## Data rules

### Nicknames

- Trimmed; internal whitespace is collapsed to one space.
- Normalized with Unicode NFKC.
- 2–24 characters after normalization.
- Empty names, control/format characters, and unsupported code points are
  rejected.
- International scripts are allowed.
- Uniqueness is case-insensitive (Unicode case folding) within a room via
  `nickname_key`; the original capitalization is preserved for display.

### Room codes

- Format: `GTC-XXXX`, where each `X` comes from an unambiguous alphabet
  (`I`, `O`, `0`, and `1` are excluded).
- Generated with a cryptographically secure random source.
- Lookup trims surrounding whitespace and uppercases the code.
- Collisions are retried atomically up to eight times.

### Room states

| State | Joining | Settings/removal | Closing |
|---|---|---|---|
| `waiting` | Allowed while below capacity | Host only | Host |
| `in_progress` | Rejected | Rejected | Host |
| `closed` | Rejected | Rejected | Rejected (already closed) |

New rooms always start in `waiting`.

### Public player fields

Room and participant responses include only:

```json
{
  "id": "uuid",
  "nickname": "Alice",
  "is_host": true,
  "is_connected": true,
  "is_ready": false,
  "joined_at": "2026-11-16T09:00:00Z"
}
```

Raw tokens, token hashes, reconnect credentials, and expiry internals are never
included in room reads.

### Characters

A character belongs to exactly one room. All character routes require
membership; non-members receive `404`, including when the room exists.

| Field | Required | Rules |
|---|---|---|
| `name` | Yes | Trimmed, NFKC-normalized, whitespace collapsed, 1–80 characters |
| `franchise` | No | Trimmed, NFKC-normalized, whitespace collapsed, 1–80 characters; blank becomes missing |
| `category` | Yes | One of the values below |
| `attributes` | No | JSON object; at most 50 top-level keys and 16 KiB serialized; no NaN/Infinity |
| `image` / `image_url` | Yes | Exactly one source; see [Image sources](#image-sources) |
| `contributed_by` | Server only | Always the authenticated player; client-supplied values are rejected |

The response includes `id`, `room_id`, `name`, `franchise`, `category`,
`image_url`, `attributes`, `contributed_by`, and `created_at`. Internal
filesystem paths are never exposed; `image_url` is a public `/media/...` URL.

#### Categories

`anime`, `manga`, `video_games`, `movies`, `tv`, `cartoons`, `comics`,
`internet_personalities`, `other`.

#### Duplicate detection

Uniqueness is per room, on the pair `(name, franchise)` after normalization:

- Unicode NFKC normalization, Unicode case folding, and collapsed whitespace.
- Missing and blank franchise both map to the empty franchise key, so
  `("Naruto", null)` and `("naruto", "   ")` are duplicates.
- A named franchise is distinct: `("Naruto", "Naruto")` and
  `("Naruto", "Boruto")` can coexist.
- The same character may be added to different rooms.
- Database constraint `uq_characters_room_id_name_key_franchise_key` enforces the
  rule; a duplicate returns `409 conflict`.

#### Image sources

Provide exactly one of:

- `image` — a multipart file part.
- `image_url` — a JSON field or multipart text field pointing at an external
  HTTP/HTTPS image.

Both paths apply the same rules:

- Content is decoded and must be a real JPEG, PNG, or WebP image. File
  extensions and declared content types are ignored.
- At most `IMAGE_MAX_BYTES` (5 MB by default) and 20 megapixels.
- Images are resized to at most 1600 px per side and re-encoded as WebP with a
  server-generated UUID filename under `MEDIA_ROOT/characters/`.
- External URLs must resolve only to public addresses (no localhost, private,
  link-local, multicast, or internal hostnames), use HTTP/HTTPS on port 80/443,
  and are fetched with `IMAGE_DOWNLOAD_TIMEOUT_SECONDS`, a byte cap, and manual
  redirect re-validation. DNS is resolved once and the connection is pinned to
  the validated IP.
- Invalid, unsafe, unreachable, or oversized images return `422 validation_error`
  and nothing is stored.

#### Lifecycle and deletion

| Room status | Create | Read/list | Delete |
|---|---|---|---|
| `waiting` | Allowed | Allowed | Allowed |
| `in_progress` | `409` | Allowed | `409` |
| `closed` | `409` | Allowed | `409` |

- The host may delete any character in the room while it is `waiting`.
- Any other member may delete only characters where `contributed_by` is their
  own player ID; otherwise the response is `403`.
- Deletion removes the database row and then the stored image. A filesystem
  cleanup failure is logged but does not fail the request.

---

## POST `/api/rooms`

Create a room and its host player atomically. No authentication is required.

### Request

```json
{
  "nickname": "Alice",
  "settings": {
    "max_players": 8,
    "game_mode": "individual"
  }
}
```

`settings` is optional. `max_players` is 2–16 (default 8); `game_mode` is
`individual` or `team` (default `individual`). Unknown settings are rejected.

### Response — `201 Created`

```json
{
  "room": {
    "id": "9f1c6a2e-5b1a-4e0f-9a6b-6a2f0f2a1b3c",
    "code": "GTC-7KQ2",
    "status": "waiting",
    "host_player_id": "51c1e3b4-2f7a-4e6e-9a1a-0e1f6b2c3d4e",
    "settings": {"max_players": 8, "game_mode": "individual"},
    "player_count": 1,
    "created_at": "2026-11-16T09:00:00Z",
    "updated_at": "2026-11-16T09:00:00Z"
  },
  "player": {
    "id": "51c1e3b4-2f7a-4e6e-9a1a-0e1f6b2c3d4e",
    "nickname": "Alice",
    "is_host": true,
    "is_connected": true,
    "is_ready": false,
    "joined_at": "2026-11-16T09:00:00Z"
  },
  "credentials": {
    "token_type": "bearer",
    "session_token": "<raw token>",
    "session_expires_at": "2026-11-17T09:00:00Z",
    "reconnect_token": "<raw reconnect token>",
    "reconnect_expires_at": "2026-11-23T09:00:00Z"
  }
}
```

The raw credentials are returned only here and by join/reconnect. Store them
client-side; they cannot be recovered later.

---

## POST `/api/rooms/join`

Join a `waiting` room by invitation code. No authentication is required.

### Request

```json
{
  "code": "GTC-7KQ2",
  "nickname": "Bob"
}
```

### Response — `200 OK`

Same shape as room creation, with the joiner as a non-host player.

### Errors

| Status | Cause |
|---|---|
| 404 | Code does not match a room |
| 409 | Room is `in_progress` or `closed`, is full, or nickname is taken |

---

## GET `/api/rooms/{room_id}`

Return public room information. Requires authentication and membership.

### Response — `200 OK`

The `room` object shown above. Non-members receive `404`.

---

## GET `/api/rooms/{room_id}/players`

List room participants. Requires authentication and membership. Ordered by join
time.

### Response — `200 OK`

```json
{
  "players": [
    {
      "id": "51c1e3b4-2f7a-4e6e-9a1a-0e1f6b2c3d4e",
      "nickname": "Alice",
      "is_host": true,
      "is_connected": true,
      "is_ready": false,
      "joined_at": "2026-11-16T09:00:00Z"
    }
  ]
}
```

---

## PATCH `/api/rooms/{room_id}/settings`

Update room settings. Host only. Allowed only while the room is `waiting`.

### Request

At least one field is required:

```json
{
  "max_players": 6,
  "game_mode": "team"
}
```

### Response — `200 OK`

The updated `room` object.

### Errors

| Status | Cause |
|---|---|
| 403 | Authenticated player is not the host |
| 409 | Room is not `waiting`, or `max_players` is below the current player count |
| 422 | No fields supplied or a value is out of range |

---

## DELETE `/api/rooms/{room_id}/players/{player_id}`

Remove another participant. Host only. Allowed only while the room is `waiting`.
The removed player's session and reconnect credentials stop working immediately.

### Response — `204 No Content`

### Errors

| Status | Cause |
|---|---|
| 403 | Authenticated player is not the host |
| 404 | Target player is not in this room |
| 409 | Target is the host, or the room is not `waiting` |

The host cannot remove themselves; they must close the room instead.

---

## POST `/api/rooms/{room_id}/leave`

Leave a room. Requires authentication and membership. The player row is deleted,
which invalidates their credentials.

### Response — `204 No Content`

### Errors

| Status | Cause |
|---|---|
| 409 | The host tried to leave |

The host must close the room instead.

---

## POST `/api/rooms/{room_id}/close`

Close the room. Host only. Allowed from `waiting` or `in_progress`.

### Response — `200 OK`

The `room` object with `"status": "closed"`.

### Errors

| Status | Cause |
|---|---|
| 403 | Authenticated player is not the host |
| 409 | Room is already `closed` |

---

## POST `/api/rooms/{room_id}/characters`

Add a character to a `waiting` room. Requires authentication and membership.
The contributor is always the authenticated player.

### Request — JSON with an image URL

```http
Content-Type: application/json
Authorization: Bearer <session_token>

{
  "name": "Naruto",
  "franchise": "Naruto",
  "category": "anime",
  "attributes": {"village": "Leaf"},
  "image_url": "https://example.com/naruto.png"
}
```

### Request — multipart with an image upload

```http
Content-Type: multipart/form-data; boundary=...

name=Naruto
franchise=Naruto
category=anime
attributes={"village":"Leaf"}
image=<binary>
```

Multipart accepts `image` **or** a text `image_url`, but not both. `attributes`
is a JSON object serialized as text and is optional. JSON requests must include
`image_url`; the JSON shape does not accept an inline binary file.

### Response — `201 Created`

```json
{
  "id": "6d2f4b3a-1c9e-4a7d-8b2f-3e5c7a9d1f42",
  "room_id": "9f1c6a2e-5b1a-4e0f-9a6b-6a2f0f2a1b3c",
  "name": "Naruto",
  "franchise": "Naruto",
  "category": "anime",
  "image_url": "/media/characters/0b7c1d2e3f4a5b6c7d8e9f0a1b2c3d4e.webp",
  "attributes": {"village": "Leaf"},
  "contributed_by": "51c1e3b4-2f7a-4e6e-9a1a-0e1f6b2c3d4e",
  "created_at": "2026-11-16T10:00:00Z"
}
```

### Errors

| Status | Cause |
|---|---|
| 404 | Room does not exist or you are not a member |
| 409 | Room is not `waiting`, or the normalized character already exists |
| 422 | Invalid field, no image source, two image sources, invalid image/URL, or untrusted `contributed_by` |

---

## GET `/api/rooms/{room_id}/characters`

List the room's characters in submission order. Requires authentication and
membership. Allowed in every room state.

### Response — `200 OK`

```json
{"characters": [ { "...": "CharacterResponse" } ]}
```

---

## GET `/api/rooms/{room_id}/characters/{character_id}`

Return one character. Requires authentication and membership. The character must
belong to the room; otherwise the response is `404`. Allowed in every room state.

### Response — `200 OK`

A single `CharacterResponse`.

---

## DELETE `/api/rooms/{room_id}/characters/{character_id}`

Remove a character while the room is `waiting`. Requires authentication and
membership.

- The host may remove any character.
- Other members may remove only their own contributions.

### Response — `204 No Content`

### Errors

| Status | Cause |
|---|---|
| 403 | Authenticated member is neither the host nor the contributor |
| 404 | Unknown room/character, character in another room, or non-member |
| 409 | Room is not `waiting` |

---

## POST `/api/rooms/{room_id}/matches`

Start a match. Host only; the room must be in `waiting`. The body is empty —
identity comes from the session.

The start operation atomically moves the room to `in_progress`, creates a fresh
assignment for every participant, and writes `match_created` and
`match_started` events. Any validation failure (not enough characters, impossible
derangement, team validation) rolls the whole operation back and leaves the room
in `waiting`.

### Response — `201 Created`

`MatchStateResponse` for the host:

```json
{
  "match": {
    "id": "c1a2b3d4-0000-4000-8000-000000000001",
    "room_id": "9f1c6a2e-5b1a-4e0f-9a6b-6a2f0f2a1b3c",
    "mode": "individual",
    "status": "active",
    "phase": "in_progress",
    "turn_index": 0,
    "current_turn_id": "51c1e3b4-2f7a-4e6e-9a1a-0e1f6b2c3d4e",
    "current_turn_kind": "player",
    "current_turn_name": "Alice",
    "participant_count": 2,
    "started_at": "2026-11-16T10:00:00Z",
    "finished_at": null,
    "winner_player_id": null,
    "winner_team_id": null,
    "winner_name": null
  },
  "self": {
    "player_id": "51c1e3b4-2f7a-4e6e-9a1a-0e1f6b2c3d4e",
    "nickname": "Alice",
    "team_id": null,
    "team_name": null,
    "is_your_turn": true,
    "can_ask": true
  },
  "identity_assigned": true,
  "identity_revealed": false,
  "opponents": [],
  "participants": [],
  "pending_question": null,
  "question_history": [],
  "allowed_recipient_ids": [
    "51c1e3b4-2f7a-4e6e-9a1a-0e1f6b2c3d4e"
  ]
}
```

The opponent list contains the host's visible characters; the host's own secret
character is never present.

### Errors

| Status | Cause |
|---|---|
| 403 | Authenticated player is not the host |
| 404 | Room does not exist or the player is not a member |
| 409 | Room is not `waiting`, an active match already exists, or prerequisites failed |

---

## GET `/api/matches/{match_id}`

Get match details. Requires authentication and room membership. Returns the
public match view plus the participant roster. Assignments are never included.

### Response — `200 OK`

```json
{
  "match": { "...": "MatchInfoResponse" },
  "participants": [
    {
      "id": "51c1e3b4-2f7a-4e6e-9a1a-0e1f6b2c3d4e",
      "name": "Alice",
      "kind": "player",
      "is_connected": true,
      "member_player_ids": ["51c1e3b4-2f7a-4e6e-9a1a-0e1f6b2c3d4e"]
    },
    {
      "id": "9f1c6a2e-5b1a-4e0f-9a6b-6a2f0f2a1b3c",
      "name": "Bob",
      "kind": "player",
      "is_connected": true,
      "member_player_ids": ["9f1c6a2e-5b1a-4e0f-9a6b-6a2f0f2a1b3c"]
    }
  ]
}
```

`kind` is `"player"` (free-for-all) or `"team"` (team mode). For teams,
`id` is the team id and `member_player_ids` lists the member player ids.

---

## GET `/api/matches/{match_id}/state`

Get the personalized match state. Requires authentication and room
membership; always the caller's own private fields only.

### Response — `200 OK`

- `match`: `MatchInfoResponse`.
- `self`: caller identity context (`player_id`, `nickname`, `team_id`, `team_name`,
  `is_your_turn`, `can_ask`).
- `identity_assigned`: whether the caller has a server-side assignment for this
  match. Always `true` for participants.
- `identity_revealed`: always `false`; the caller's secret character is never
  exposed, even after a win.
- `opponents`: visible characters assigned to other participants. Each entry
  contains `owner_id`, `owner_kind`, `owner_name`, and a public `character`
  summary (`id`, `name`, `franchise`, `category`, `image_url`, `attributes`).
  The caller's own character is never included.
- `participants`: public participant roster.
- `pending_question`: the current unanswered question, when the match is active
  and the caller may answer it; `can_answer` reflects authorization.
- `question_history`: answered questions in ascending order, including answer
  content and authors.
- `allowed_recipient_ids`: recipient owner ids the current turn may choose from;
  empty when the caller cannot ask.

---

## POST `/api/matches/{match_id}/questions`

Ask a question on the active turn.

### Request

```json
{
  "content": "Does your character have a superhuman ability?",
  "recipient_player_id": "51c1e3b4-2f7a-4e6e-9a1a-0e1f6b2c3d4e"
}
```

`content` is required, non-empty, and at most 500 characters after trimming.
Exactly one recipient must be provided: `recipient_player_id` for free-for-all
or `recipient_team_id` for team mode.

### Response — `201 Created`

The created `QuestionResponse`, including `question_id`/`id`, author, content,
recipient, timestamps, and (when answered) the answer. `can_answer` is `false` for
a freshly created pending question.

### Errors

| Status | Cause |
|---|---|
| 403 | Caller is not the active player/team |
| 409 | Match is not active, a question is already pending, or the recipient is invalid |
| 422 | Empty content, content over 500 characters, missing/ambiguous recipient, self-recipient, or non-participant recipient |

---

## POST `/api/matches/{match_id}/questions/{question_id}/answer`

Answer the pending question. Designated-recipient authorization applies; in team
mode any authorized member of the recipient team may answer.

### Request

```json
{
  "content": "Yes, their power is energy-based."
}
```

`content` is required, non-empty, and at most 1000 characters after trimming.

### Response — `200 OK`

The updated `QuestionResponse` with the stored answer and `can_answer: false`.

### Errors

| Status | Cause |
|---|---|
| 403 | Caller is not the designated recipient |
| 404 | Question does not exist for this match |
| 409 | Match is not active or the question was already answered |

---

## POST `/api/matches/{match_id}/guesses`

Submit a guess at any time while the match is active. The guessed character must
be validated server-side against the caller's secret assignment.

### Request

```json
{
  "character_id": "6d2f4b3a-1c9e-4a7d-8b2f-3e5c7a9d1f42"
}
```

The client supplies only the character id. The server decides whether the caller
is correct; it never accepts an identity, team, or contributor identifier.

### Response — `200 OK`

`GuessResultResponse`:

```json
{
  "correct": true,
  "match": {
    "id": "c1a2b3d4-0000-4000-8000-000000000001",
    "room_id": "9f1c6a2e-5b1a-4e0f-9a6b-6a2f0f2a1b3c",
    "mode": "individual",
    "status": "finished",
    "phase": "finished",
    "turn_index": 0,
    "current_turn_id": null,
    "current_turn_kind": "player",
    "current_turn_name": null,
    "participant_count": 2,
    "started_at": "2026-11-16T10:00:00Z",
    "finished_at": "2026-11-16T10:05:00Z",
    "winner_player_id": "51c1e3b4-2f7a-4e6e-9a1a-0e1f6b2c3d4e",
    "winner_team_id": null,
    "winner_name": "Alice"
  }
}
```

For a correct guess the match is transitioned to `finished` with exactly one
winner (atomic compare-and-swap). An incorrect guess does not change the turn,
eliminate anyone, or penalize; it writes `guess_submitted` and `guess_incorrect`
events.

### Errors

| Status | Cause |
|---|---|
| 404 | Character does not exist in the room |
| 409 | Match is not active (finished/cancelled) |

---

## POST `/api/matches/{match_id}/cancel`

Cancel a pending or active match. Host only. The match transitions to
`abandoned` and the room returns to `waiting` when a match was active.

### Response — `200 OK`

`MatchStateResponse` with `match.phase == "cancelled"` and
`match.status == "abandoned"`.

### Errors

| Status | Cause |
|---|---|
| 403 | Authenticated player is not the host |
| 404 | Match does not exist or the player is not a member |
| 409 | Match is already `finished` or `abandoned` |

---

## GET `/api/matches/{match_id}/history`

Paginated event history. Cursor-paged by `after_sequence` (exclusive upper bound;
pass back `next_after_sequence` to continue) with a default limit of 50 and a
maximum of 100.

### Response — `200 OK`

```json
{
  "events": [
    {
      "id": "e3f4a5b6-0000-4000-8000-000000000002",
      "match_id": "c1a2b3d4-0000-4000-8000-000000000001",
      "actor_player_id": "51c1e3b4-2f7a-4e6e-9a1a-0e1f6b2c3d4e",
      "event_type": "match_started",
      "payload": {
        "mode": "individual",
        "participant_count": 2,
        "turn_order": ["51c1e3b4-2f7a-4e6e-9a1a-0e1f6b2c3d4e", "9f1c6a2e-5b1a-4e0f-9a6b-6a2f0f2a1b3c"]
      },
      "sequence_number": 2,
      "created_at": "2026-11-16T10:00:00Z"
    }
  ],
  "has_more": false,
  "next_after_sequence": null
}
```

Event types used by the engine: `match_created`, `match_started`,
`question_sent`, `answer_sent`, `guess_submitted`, `guess_correct`,
`guess_incorrect`, `match_finished`, `match_cancelled`.

Event payloads never contain session tokens, hashes, credentials, or secrets.

### Errors

| Status | Cause |
|---|---|
| 404 | Match does not exist or the player is not a member |

---

## Team management endpoints

Teams are managed only while the room is `waiting`.

### POST `/api/rooms/{room_id}/teams`

Create a team. Host only.

```json
{
  "name": "Alpha"
}
```

### Response — `201 Created`

```json
{
  "id": "9f1c6a2e-5b1a-4e0f-9a6b-6a2f0f2a1b3c",
  "room_id": "9f1c6a2e-5b1a-4e0f-9a6b-6a2f0f2a1b3c",
  "name": "Alpha",
  "members": [ { "...": "PublicPlayerResponse" } ]
}
```

### GET `/api/rooms/{room_id}/teams`

List teams. Requires authentication and membership.

### PUT `/api/rooms/{room_id}/players/{player_id}/team`

Assign or remove a player's team. Host only; allowed only while the room is
`waiting`.

```json
{
  "team_id": "9f1c6a2e-5b1a-4e0f-9a6b-6a2f0f2a1b3c"
}
```

Passing `team_id: null` removes team membership.

### Errors

| Status | Cause |
|---|---|
| 403 | Not the host |
| 404 | Room/player/team not found |
| 409 | Room is not `waiting`, team name exists, or team assignment is inconsistent |
| 422 | Blank or overly long team name |

---

## POST `/api/sessions/reconnect`

Restore a player session using the dedicated reconnect credential. The room may
be in any state — reconnection restores existing membership and does not create
a new player.

### Request

```json
{
  "reconnect_token": "<raw reconnect token>"
}
```

### Response — `200 OK`

Same shape as room creation, with `room`, `player`, and a fresh `credentials`
pair. Behaviour:

- Player identity, nickname, team, and room membership are preserved.
- `is_connected` becomes `true` and `last_seen_at` is updated.
- The session token and reconnect token are rotated together in one
  compare-and-swap update.
- The previous session and reconnect tokens become invalid immediately.
- No duplicate player is created.

### Errors

| Status | Cause |
|---|---|
| 401 | Credential is unknown or `reconnect_expires_at` has passed |
| 422 | Body is missing or malformed |

Calling reconnect twice with the same credential succeeds once; the second call
returns `401`. Clients must persist the newly returned tokens.

---

## Session lifetimes

| Setting | Default | Purpose |
|---|---|---|
| `SESSION_TOKEN_TTL_HOURS` | 24 | Absolute session lifetime; checked on every request |
| `RECONNECT_TOKEN_TTL_HOURS` | 168 | Recovery window; must be ≥ session TTL |

An expired session cannot access room routes. Use the reconnect token to obtain
a new session before the reconnect window closes. A disconnected player remains
a room member until they leave, are removed by the host, or the room is deleted;
`is_connected` is presence metadata, not an authorization decision.

---

## Media serving

Validated images are served by a static mount:

```http
GET /media/characters/<uuid>.webp
```

- The mount is unauthenticated and lives outside `/api`. Access is controlled by
  the unguessable UUID filename, so the URL behaves as a capability. Treat it as
  a secret and do not enable directory listings.
- Filenames are generated server-side; client filenames and paths are never used.
- Stored bytes are always re-encoded WebP, even when the source was PNG or JPEG.
- `MEDIA_URL_PREFIX` changes the public prefix; `MEDIA_ROOT` changes the storage
  directory. Both are server configuration, never request input.

---

## WebSocket API - `/ws/rooms/{room_code}`

Phase 5 adds an authenticated, room-scoped WebSocket endpoint for real-time
updates. It is not under `/api` because browsers cannot attach an
`Authorization` header to a WebSocket handshake.

```text
ws://localhost:8000/ws/rooms/ABCD12?token=<session_token>
```

- Use `wss://` in production.
- The connection is accepted only after the session token and room membership
  are validated server-side. Missing, invalid, expired, unknown-room, and
  non-member handshakes all close with code `1008` **before** the socket is
  accepted; no error frame, room name, or token detail is sent.
- The token is a short-lived session token (24 h by default), not a reconnect
  token. If it has expired, rotate credentials through
  `POST /api/sessions/reconnect`, then reconnect.
- Because browsers cannot set handshake headers, the session token appears in
  the query string. Avoid logging full WebSocket URLs at proxies and reverse
  proxies; use TLS so the URL is not visible on the wire. Never put the
  long-lived reconnect token in the URL.

### Envelope

Incoming messages:

```json
{
  "event": "question.submit",
  "request_id": "client-generated-id",
  "payload": { "content": "Is it a hero?", "recipient_player_id": "..." }
}
```

| Field | Required | Notes |
|---|---|---|
| `event` | yes | Must be one of the supported events |
| `request_id` | no | Echoed on the direct response; deduplicated per connection |
| `payload` | no | Event-specific object; unknown fields are rejected |

Outgoing messages:

```json
{
  "event": "match.state",
  "request_id": "client-generated-id",
  "payload": { "...": "..." }
}
```

| Field | Notes |
|---|---|
| `event` | Event name |
| `payload` | Recipient-specific object |
| `request_id` | Present on direct responses to a client request |
| `event_id` | Reserved for future server event identifiers; currently omitted |
| `sequence_number` | Reserved; persisted ordering is available via the REST history endpoint |

Only JSON **text** frames are accepted. Binary frames, malformed JSON, invalid
payloads, unknown events, duplicate `request_id` values, and messages larger
than **8192 bytes** are rejected with a structured `error` event. The 8192-byte
cap also bounds the free-text question (500) and answer (1000) limits enforced by
the services.

### Incoming events

| Event | Payload | Behavior |
|---|---|---|
| `room.get_state` | none | Returns the caller's personalized `room.state` |
| `player.set_ready` | `{ "ready": bool, "target_player_id"?: uuid }` | Self, or any participant when the caller is host; waiting rooms only |
| `character.add` | `{ "name", "franchise"?, "category"?, "attributes"?, "image_url" }` | Reuses `CharacterService`; `image_url` is required because binary uploads stay REST-only |
| `character.delete` | `{ "character_id": uuid }` | Host or contributor; waiting rooms only |
| `match.start` | none | Host only; delegates to `MatchService.start_match` |
| `match.get_state` | none | Personalized state of the room's active match |
| `question.submit` | `{ "content", "recipient_player_id"? , "recipient_team_id"? }` | Active-turn owner only |
| `answer.submit` | `{ "content", "question_id": uuid }` | Designated recipient only |
| `guess.submit` | `{ "character_id": uuid }` | Server compares against the caller's own assignment |
| `match.cancel` | none | Host only; returns the room to `waiting` |

All operations call the same room, character, match, and session services as the
REST API. There is no second game engine and no client-supplied actor identity.

**Character images:** WebSocket character creation accepts an `image_url` and
runs the full download and image-validation pipeline. Multipart/binary uploads
remain available only through
`POST /api/rooms/{room_id}/characters`; successful REST uploads and deletions
broadcast `character.added` / `character.deleted` to the room.

### Outgoing events

| Event | Payload | Recipients |
|---|---|---|
| `room.state` | Public room view | Direct response / initial snapshot |
| `room.updated` | Public room view | Room, after a REST settings change or room close |
| `player.joined` | Public player fields | Room, after a REST join |
| `player.left` | `{ "player_id" }` | Room, after a REST leave or host removal |
| `player.connected` | `{ "player_id", "nickname" }` | Room, only on the player's first connection |
| `player.disconnected` | `{ "player_id", "room_id" }` | Room, only after the player's last connection closes |
| `player.ready_changed` | `{ "player_id", "nickname", "ready" }` | Room, including the sender |
| `character.added` | `{ "character_id", "name" }` | Room |
| `character.deleted` | `{ "character_id" }` | Room |
| `match.started` | `{ "match_id", "status" }` | Room; the host also receives a full personalized `match.state` response |
| `match.state` | Personalized match state | Direct response / initial snapshot / `match.get_state` |
| `match.turn_changed` | `{ "current_turn_id" }` | Room, after an answer advances the turn |
| `question.received` | Question id, content, author, recipient | Only the recipient player (all their tabs) or team |
| `answer.received` | `{ "question_id", "answer", "author_player_id" }` | Only the question author (all their tabs) |
| `guess.incorrect` | `{ "character_id", "correct": false }` | Only the requesting connection |
| `match.finished` | `{ "winner_player_id", "winner_team_id", "reason" }` | Room |
| `match.cancelled` | `{ "reason": "host_cancelled" }` | Room |
| `connection.heartbeat` | `{}` | The individual connection every 30 seconds (transient, not persisted) |
| `error` | `{ "code", "message" }` | The requesting connection |

Personalized state never includes the caller's own secret assignment, another
player's private question or answer, session credentials, token hashes, or
internal assignment rows. Match state is built by the existing Phase 4
serializer for the authenticated player.

### Error events

```json
{
  "event": "error",
  "request_id": "client-generated-id",
  "payload": { "code": "permission_denied", "message": "..." }
}
```

Transport/protocol codes:

| Code | Meaning |
|---|---|
| `invalid_message` | Non-JSON, non-object JSON, or non-text frame |
| `unknown_event` | Event name is not supported |
| `invalid_payload` | Payload fails the event schema (wrong type, unknown field, bad UUID) |
| `message_too_large` | Frame exceeds 8192 bytes; the connection is closed |
| `duplicate_request` | `request_id` was already processed on this connection |
| `internal_error` | Unexpected failure; no internal detail is exposed and the connection is dropped |

Domain failures reuse the REST error codes (`validation_error`, `not_found`,
`permission_denied`, `conflict`, `service_unavailable`). A failed action never
rolls forward into a second game event.

### Ordering, idempotency, and reconnection

- Ordering of persisted match events is owned by the existing
  `matches.event_sequence` counter and `GameEvent.sequence_number`. WebSocket
  notifications describe state changes; they do not invent persisted events for
  heartbeats or presence.
- A client-generated `request_id` is remembered for the lifetime of the
  connection. Re-sending the same id returns `duplicate_request` without calling
  the service again, so retries cannot create a duplicate question, answer, or
  guess event. Use a new `request_id` for a genuinely new action. The dedup
  window is per connection: after a reconnect, reconcile with the personalized
  snapshot (or match history) before retrying an action whose outcome is unknown.
- On connect (and after any reconnect) the server sends one complete snapshot:
  `room.state` while waiting, or `match.state` while a match is active. A
  reconnecting participant keeps the same player row, room membership, secret
  assignment, and turn position. The client cannot request another player's
  state: `match.get_state` always resolves the connection's authenticated
  player.
- Presence is transient: `player.connected` is emitted only when a player's
  first connection opens, and `player.disconnected` only when their last
  connection closes. A disconnected player is not skipped; the persisted turn
  order is unchanged.
- Each connection receives `connection.heartbeat` every 30 seconds. A failed
  send removes the connection record, and Uvicorn's native WebSocket
  ping/timeout handles dead TCP peers; no separate database heartbeat is
  written.
- If a client has a last-seen persisted sequence, it may call
  `GET /api/matches/{match_id}/history?after_sequence=<n>` to fetch missing
  persisted events after receiving the personalized snapshot. The WebSocket
  layer does not replay unverified history from client-supplied state.

### Deployment limitation

`ConnectionManager` is intentionally in-memory and per-process. The MVP must run
a **single Uvicorn worker**; multiple workers would each know only their own
connections, so broadcasts and presence would be incomplete. Redis or another
shared broker is explicitly out of scope until a later phase.

## Client integration notes

The Phase 6 React client (`frontend/`) follows these rules and is a reference for
other clients:

- **Base URLs.** REST calls use `VITE_API_BASE_URL` (development default
  `http://localhost:8000`, production default: the page origin) and the socket
  derives `ws://`/`wss://` from `VITE_WS_BASE_URL` or the API origin. When the
  SPA is served by FastAPI under `FRONTEND_DIST_DIR`, one origin covers the UI,
  REST, media, and WebSockets. Browser origins must appear in backend
  `CORS_ORIGINS` only for split-origin development.
- **Authentication.** Send `Authorization: Bearer <session_token>` on every REST
  request. The socket takes `?token=<session_token>` because browsers cannot set
  handshake headers. Never place the reconnect token in a URL.
- **Session recovery.** On `401`/`invalid_session`, call
  `POST /api/sessions/reconnect` once with the reconnect token, replace both
  tokens, and retry the original request once. On socket close `1008`, rotate
  credentials and reconnect; do not retry until the new URL is ready.
- **Actions.** Use the socket for `match.start`, `question.submit`,
  `answer.submit`, `guess.submit`, `match.cancel`, readiness, and character
  changes when the live UI must fan out immediately. REST match mutations do not
  broadcast, so mixing transports can leave other tabs stale.
- **Envelopes.** Every outgoing action needs a unique `request_id`; reuse is only
  safe for an intentional retry of the same operation on the same connection,
  and per-connection deduplication resets after reconnect.
- **State.** Validate incoming `event` names and payload shapes before applying
  them. Treat the latest personalized snapshot as authoritative. After reconnect,
  fetch `GET /api/matches/{match_id}/history?after_sequence=<last>` and merge by
  `sequence_number`; never invent sequence numbers or replay unknown-outcome
  actions.
- **Status vs phase.** `match.status` is the persisted lifecycle enum
  (`pending`, `active`, `paused`, `finished`, `abandoned`). `match.phase` is the
  friendly, stable lifecycle value (`created`, `in_progress`, `finished`,
  `cancelled`) and is the correct field for UI branching such as showing the live
  table versus the result screen. `paused` maps to `phase == "in_progress"`.
- **Match completion.** `match.finished` and `match.cancelled` carry no full
  state. Reload `GET /api/matches/{match_id}/state` before rendering results;
  `match.get_state` resolves only an active match.
