# Guess the Character — Project Specification

**Project type:** Real-time multiplayer web game  
**Status:** Development specification  
**Backend:** Python + FastAPI  
**Frontend:** React + TypeScript  
**Database:** SQLite  
**Real-time communication:** WebSockets  
**Development environment:** Local machine + ngrok  
**Primary goal:** Build a private multiplayer character-guessing game playable directly from a web browser.

---

# 1. Project Overview

Build a multiplayer web application inspired by the classic Guess Who? concept, but with a reverse identity-guessing mechanic.

Players are randomly assigned characters from a shared collection. Each player can see the characters assigned to other players, but cannot see their own character.

The objective is to discover one's own identity by asking questions and receiving answers from other participants.

The application must support:

- Individual multiplayer matches.
- Team-based matches.
- Private rooms with invitation codes.
- User-submitted characters.
- Random character assignment.
- Real-time communication.
- Questions and free-text answers.
- Unlimited guessing attempts.
- Persistent match history.
- Player reconnection.

The application must be fully playable through a browser. No installation should be required for participants.

# 2. Core Gameplay Rules

These rules are mandatory and must be implemented consistently on the backend.

## 2.1 Character Assignment

At the beginning of a match:

1. The system collects all eligible characters.
2. The game engine randomly assigns one character to each player or team.
3. Each player can see the character assigned to every other player.
4. A player must never see their own assigned character.
5. Character assignments must be unique within a match.
6. The server must keep all assignments private.

Example with four players:

| Player | Secret character | Characters visible |
|---|---|---|
| Player 1 | Naruto | Luffy, Goku, Shrek |
| Player 2 | Luffy | Naruto, Goku, Shrek |
| Player 3 | Goku | Naruto, Luffy, Shrek |
| Player 4 | Shrek | Naruto, Luffy, Goku |

The character assignment algorithm must guarantee that no participant receives their own character.

Use a randomized derangement algorithm or an equivalent validated assignment strategy.

Do not expose secret character information through API responses, WebSocket messages, logs, frontend state, or browser-visible HTML.

## 2.2 Questions and Answers

Question rules:

- Players take turns asking questions.
- Questions are submitted as free text.
- Answers are also free text.
- The answering player can respond naturally.
- Questions and answers must be stored in the match history.

Example:

Player 1: "Am I from an anime?"

Player 2: "Yes."

Player 2: "Am I blonde?"

Player 1: "Yes."

Player 1: "Am I a pirate?"

Player 2: "Yes."

The question and answer sequence must be synchronized across all connected participants.

For multiplayer matches, implement an explicit turn order and responder selection. Use a configurable sequential order, with the next eligible opponent answering the active player's question as the initial default.

## 2.3 Guessing Rules

Players can attempt to guess their own character at any time.

Guessing is independent of the normal question turn.

When a player submits a guess:

- The backend validates the submitted character.
- If incorrect, register the attempt and continue the match.
- Incorrect guesses do not consume a turn.
- Incorrect guesses do not eliminate players.
- There is no attempt limit.
- If correct, register the winner and trigger the match-ending event.

In team mode, any team member may submit a guess on behalf of their team.

A successful guess ends the match by default.

The backend must validate guesses against the actual secret assignment, never against client-provided information.

# 3. Game Modes

The architecture must support both individual and team-based gameplay.

## 3.1 Individual Mode

Each player receives an independent secret character.

Players can see the identities of all other participants but not their own.

The match supports two or more participants.

Default configuration:

- Minimum: 2 players.
- Recommended maximum: 8 players.
- One secret character per player.
- Independent guessing attempts.
- First successful guess wins.

## 3.2 Team Mode

Players are grouped into teams.

Each team receives one shared secret character.

Team members share the same identity.

Opposing teams can see the character assigned to each other team.

Team members must not see their own team's secret character.

Any team member can submit questions or guesses on behalf of the team.

Default configuration:

- Minimum: 2 teams.
- Recommended maximum: 4 teams.
- At least 1 player per team.
- One shared character per team.
- First team to correctly identify its character wins.

## 3.3 Match Configuration

Support configurable options:

- Individual or team mode.
- Number of teams.
- Maximum participants.
- Minimum character pool size.
- Turn order.
- Match title.
- Room privacy.
- Character collection rules.

The initial recommended defaults are:

- Both individual and team modes enabled.
- Shared character collection.
- Only the host can start a match.
- Minimum character pool: 30.
- Recommended character pool: 30–60.

These defaults must be configurable rather than hardcoded.

# 4. Room and Lobby System

Users must be able to create and join private rooms.

## 4.1 Room Creation

The host can:

- Create a private room.
- Choose a nickname.
- Select game mode.
- Configure match settings.
- Share an invitation code.
- Manage participants.
- Start the match.

Each room must have a unique short invitation code.

Example:

`GTC-82K4`

## 4.2 Joining a Room

Participants must be able to:

1. Open the application URL.
2. Enter a nickname.
3. Enter the room code.
4. Join the lobby.
5. Wait for the host to start the match.

No registration or account creation should be required for the MVP.

Use secure session tokens to identify participants.

## 4.3 Lobby

The lobby should display:

- Room code.
- Host.
- Connected players.
- Player readiness.
- Selected game mode.
- Team assignments when applicable.
- Available character collection.
- Start button for the host.

Participants must be able to leave the room.

The host should be able to remove participants before the match starts.

# 5. Character Management

Participants must be able to contribute characters to the room's shared collection.

## 5.1 Character Submission

Each character should support:

- Character name.
- Franchise or source.
- Category.
- Image.
- Optional description.
- Optional attributes.
- Contributor ID.
- Submission timestamp.

Suggested categories:

- Anime.
- Manga.
- Video games.
- Movies.
- Television series.
- Cartoons.
- Comics.
- Internet personalities.
- Other.

## 5.2 Character Images

Support:

1. Local image uploads.
2. Image URLs.

For local uploads:

- Store images on the backend.
- Generate unique filenames.
- Validate MIME type and file extension.
- Validate actual image contents.
- Limit upload size.
- Restrict allowed image formats.
- Prevent path traversal.
- Generate safe image paths.

Preferred formats:

- WebP.
- PNG.
- JPEG.

Suggested initial upload limit: 5 MB.

## 5.3 Character Attributes

Characters may have optional attributes such as:

- Gender presentation.
- Hair color.
- Species.
- Human or non-human.
- Powers.
- Franchise.
- Occupation.
- Clothing.
- Other descriptive properties.

Attributes must not be mandatory.

The game must support manually written questions even when character attributes are missing.

Do not implement automatic answer generation in the MVP.

The opponent must answer questions manually.

## 5.4 Duplicate Prevention

Implement duplicate detection within a room's collection.

At minimum, compare normalized character names and franchise names.

Allow the host to remove characters before starting a match.

Once a match starts, freeze its character collection and assignments.

# 6. Technical Architecture

Use a modular monolithic architecture.

Do not introduce microservices for the MVP.

## 6.1 Technology Stack

### Backend

- Python 3.11 or newer.
- FastAPI.
- Uvicorn.
- SQLAlchemy 2.x.
- Pydantic v2.
- SQLite.
- Alembic.
- WebSockets.
- Pytest.
- Pillow for image validation and processing.

### Frontend

- React.
- TypeScript.
- Vite.
- Tailwind CSS.
- React Router.
- Zustand for application state.
- Native WebSocket API or a dedicated WebSocket client service.

### Infrastructure

- ngrok.
- Local filesystem for uploaded images.
- Environment variables.
- Git.

Use compatible, stable dependency versions.

## 6.2 Architecture Diagram

```text
                  INTERNET
                      |
                    ngrok
                      |
                      v
              FastAPI Application
                      |
          +-----------+-----------+
          |                       |
          v                       v
      REST API                WebSockets
          |                       |
          +-----------+-----------+
                      |
                      v
                  Game Engine
                      |
       +--------------+--------------+
       |              |              |
       v              v              v
  Room Manager   Assignment      Turn Manager
                 Engine
       |              |              |
       +--------------+--------------+
                      |
                      v
               Persistence Layer
                      |
                      v
                   SQLite

Frontend:
React + TypeScript + Tailwind CSS
```

## 6.3 Backend Architecture

Keep business logic independent of HTTP and WebSocket handlers.

The Game Engine must not depend on FastAPI request objects.

Use services and domain logic to handle gameplay operations.

# 7. Project Structure

Use the following initial structure:

```text
guess-the-character/
|
├── backend/
|   ├── app/
|   |   ├── main.py
|   |   |
|   |   ├── core/
|   |   |   ├── config.py
|   |   |   ├── security.py
|   |   |   └── exceptions.py
|   |   |
|   |   ├── api/
|   |   |   ├── rooms.py
|   |   |   ├── players.py
|   |   |   ├── characters.py
|   |   |   ├── teams.py
|   |   |   └── games.py
|   |   |
|   |   ├── game/
|   |   |   ├── engine.py
|   |   |   ├── assignment.py
|   |   |   ├── turn_manager.py
|   |   |   ├── guess_engine.py
|   |   |   ├── team_manager.py
|   |   |   └── victory.py
|   |   |
|   |   ├── websocket/
|   |   |   ├── manager.py
|   |   |   ├── events.py
|   |   |   └── handlers.py
|   |   |
|   |   ├── models/
|   |   |   ├── room.py
|   |   |   ├── player.py
|   |   |   ├── team.py
|   |   |   ├── character.py
|   |   |   ├── match.py
|   |   |   ├── assignment.py
|   |   |   └── game_event.py
|   |   |
|   |   ├── schemas/
|   |   ├── repositories/
|   |   ├── services/
|   |   └── database/
|   |
|   ├── storage/
|   |   └── characters/
|   |
|   ├── tests/
|   |   ├── unit/
|   |   ├── integration/
|   |   └── security/
|   |
|   ├── alembic/
|   ├── alembic.ini
|   └── requirements.txt
|
├── frontend/
|   ├── src/
|   |   ├── components/
|   |   ├── pages/
|   |   ├── layouts/
|   |   ├── hooks/
|   |   ├── services/
|   |   ├── stores/
|   |   ├── types/
|   |   └── utils/
|   |
|   ├── public/
|   └── package.json
|
├── docs/
|   ├── ARCHITECTURE.md
|   ├── GAME_RULES.md
|   └── API.md
|
├── .env.example
├── .gitignore
├── README.md
└── docker-compose.yml
```

The structure can be refined when implementation requirements become clearer.

Avoid creating unnecessary empty modules.

# 8. Database Design

Use SQLAlchemy 2.x declarative models and Alembic migrations.

Recommended entities:

## Room

- id: UUID.
- code: unique string.
- host_player_id: UUID.
- status: enum.
- configuration: JSON.
- created_at: datetime.
- updated_at: datetime.

## Player

- id: UUID.
- room_id: UUID.
- nickname: string.
- session_token_hash: string.
- team_id: nullable UUID.
- is_connected: boolean.
- is_ready: boolean.
- joined_at: datetime.
- last_seen_at: datetime.

## Team

- id: UUID.
- room_id: UUID.
- name: string.
- created_at: datetime.

## Character

- id: UUID.
- room_id: UUID.
- name: string.
- franchise: nullable string.
- category: nullable string.
- image_path: string.
- attributes: JSON.
- contributed_by: UUID.
- created_at: datetime.

## Match

- id: UUID.
- room_id: UUID.
- mode: enum.
- status: enum.
- turn_index: integer.
- configuration: JSON.
- started_at: nullable datetime.
- finished_at: nullable datetime.
- winner_id: nullable UUID.
- winner_team_id: nullable UUID.

## Assignment

- id: UUID.
- match_id: UUID.
- character_id: UUID.
- player_id: nullable UUID.
- team_id: nullable UUID.

Exactly one of player_id or team_id must be populated.

Add a database constraint to enforce this rule.

A character must not be assigned twice within the same match.

## GameEvent

- id: UUID.
- match_id: UUID.
- actor_player_id: nullable UUID.
- event_type: string.
- payload: JSON.
- sequence_number: integer.
- created_at: datetime.

Use a sequential event number to preserve the order of match actions.

The database must enforce appropriate foreign keys and uniqueness constraints.

# 9. API Design

Use REST for administrative operations and WebSockets for real-time gameplay.

Recommended REST endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| POST | /api/rooms | Create a room |
| POST | /api/rooms/join | Join a room |
| GET | /api/rooms/{room_id} | Get room information |
| PATCH | /api/rooms/{room_id}/settings | Update settings |
| POST | /api/rooms/{room_id}/characters | Add a character |
| GET | /api/rooms/{room_id}/characters | List characters |
| DELETE | /api/rooms/{room_id}/characters/{id} | Remove a character |
| POST | /api/rooms/{room_id}/teams | Create teams |
| POST | /api/games/{game_id}/start | Start a match |
| GET | /api/games/{game_id}/state | Get personalized game state |
| GET | /api/games/{game_id}/history | Get match history |

Use Pydantic request and response schemas.

Implement consistent HTTP error responses.

Never return internal database objects directly.

# 10. WebSocket Protocol

Implement an authenticated WebSocket connection for every participant.

Suggested endpoint:

`/ws/rooms/{room_code}`

Every client message must contain:

```json
{
  "event": "question_sent",
  "request_id": "uuid",
  "payload": {
    "question": "Am I human?"
  }
}
```

Server responses must follow a consistent structure:

```json
{
  "event": "question_received",
  "event_id": "uuid",
  "sequence_number": 12,
  "payload": {
    "player_id": "uuid",
    "question": "Am I human?"
  }
}
```

Required events:

### Room Events

- player_joined
- player_left
- player_disconnected
- player_reconnected
- room_updated
- room_closed

### Character Events

- character_added
- character_removed
- character_collection_updated

### Game Events

- game_started
- game_paused
- game_resumed
- turn_changed
- question_sent
- question_received
- answer_sent
- answer_received
- guess_submitted
- guess_incorrect
- guess_correct
- game_finished

### Synchronization Events

- state_resynchronized
- event_acknowledged
- server_error

Use event identifiers and request identifiers to prevent duplicate processing.

The backend must validate every incoming event.

Do not trust client-provided player IDs or team IDs.

# 11. Personalized Game State and Security

This is one of the most important requirements.

The backend must generate a personalized game state for each connected player.

Example:

```json
{
  "match_id": "uuid",
  "current_turn": "player_1",
  "your_identity": {
    "revealed": false
  },
  "visible_characters": [
    {
      "owner_id": "player_2",
      "character": {
        "name": "Naruto",
        "franchise": "Naruto",
        "image_url": "/media/characters/naruto.webp"
      }
    }
  ]
}
```

The secret character must never appear in this response.

The same rule applies to team mode.

Security requirements:

- Authenticate WebSocket connections.
- Validate room membership.
- Validate player permissions.
- Prevent identity leakage.
- Validate turn ownership.
- Validate question and answer ownership.
- Validate guessing attempts server-side.
- Prevent replayed or duplicated commands.
- Restrict image uploads.
- Avoid storing raw session tokens in the database.

Never send the complete assignment table to the frontend.

Never rely on frontend-only restrictions to protect secret information.

# 12. Frontend Design

The interface should feel like a modern multiplayer party game.

Design direction:

- Dark visual theme.
- Clean typography.
- Modern card layouts.
- Smooth transitions.
- Character portraits.
- Responsive layout.
- Clear player indicators.
- Real-time notifications.

Avoid overly complicated visual elements.

## Required Pages

### Home

- Create room.
- Join room.
- Enter nickname.
- Basic game instructions.

### Lobby

- Room code.
- Player list.
- Host indicator.
- Game configuration.
- Team management.
- Character submission.
- Ready status.
- Start button.

### Character Collection

- Character grid.
- Image previews.
- Search.
- Category filters.
- Add character dialog.
- Remove character action.

### Game Screen

This is the main gameplay interface.

It must contain:

1. Opponents' visible character cards.
2. Player and team information.
3. Current turn indicator.
4. Question input.
5. Answer input when appropriate.
6. Guess button.
7. Match history.
8. Real-time notifications.
9. Connection status.

Players must never see their own character.

### Results Screen

- Winner.
- Revealed identities.
- Final match statistics.
- Match history.
- Play again option.
- Return to lobby.

# 13. Reconnection and Persistence

Participants must be able to reconnect after losing Internet connectivity.

Implement:

- Secure session restoration.
- Reconnection tokens.
- Player connection status.
- Match state recovery.
- Event sequence tracking.
- WebSocket reconnection.
- State resynchronization.

When a participant reconnects, send their personalized current game state.

Do not restart the match because one player temporarily disconnects.

For the MVP, use a configurable reconnection timeout.

Persist all important game events and assignments.

The application must not depend exclusively on in-memory game state.

For single-process deployment, SQLite and a database-backed state model are sufficient.

# 14. Development and Deployment

The application must run locally on the host machine.

Recommended development ports:

- Frontend development: 5173.
- Backend: 8000.
- SQLite: local database file.

For public testing, serve the built frontend through FastAPI and expose a single HTTP origin with ngrok.

This simplifies WebSocket connectivity, HTTPS, and CORS configuration.

Suggested development command:

```bash
ngrok http 8000
```

The public URL must be shared with participants.

The application should use environment variables for configuration.

Provide:

- `.env.example`
- `.gitignore`
- `README.md`
- Local installation instructions.
- Development commands.
- ngrok deployment instructions.

Do not commit secrets, database files, uploaded images, or session credentials.

# 15. Testing Strategy

Use Pytest for backend tests.

Test the game engine independently from FastAPI.

## Assignment Tests

- Every player receives one character.
- Every team receives one character.
- No player sees their own identity.
- No duplicate assignments.
- Assignment works with different participant counts.
- Invalid character pools are rejected.

## Gameplay Tests

- Questions are accepted only from the active player.
- Answers are accepted only from the designated responder.
- Questions and answers are recorded.
- Incorrect guesses do not consume turns.
- Incorrect guesses do not eliminate participants.
- Guessing is allowed outside normal turns.
- Correct guesses finish the match.
- A second winner cannot be registered after the match finishes.

## Team Tests

- Team members share the same identity.
- Team members cannot see their own identity.
- Opposing teams can see the assigned characters.
- Any authorized team member can submit a guess.
- Only one winning team is registered.

## Security Tests

- Players cannot access other players' secret identities.
- Unauthorized players cannot join protected sessions.
- Invalid WebSocket messages are rejected.
- Players cannot impersonate other players.
- Duplicate requests are handled safely.

## Integration Tests

Simulate multiple players connecting to the same room.

Test:

- Room creation.
- Joining.
- Character submission.
- Match initialization.
- Question and answer exchange.
- Incorrect guessing.
- Correct guessing.
- Disconnection.
- Reconnection.
- Final match state.

# 16. Development Roadmap

Implement the project in the following order.

## Phase 1 — Backend Foundation

- Create the FastAPI application.
- Configure settings.
- Configure SQLAlchemy.
- Configure SQLite.
- Add Alembic migrations.
- Implement initial models.
- Create basic health endpoint.
- Add backend tests.

Deliverable: A working backend foundation.

## Phase 2 — Room Management

- Create rooms.
- Generate invitation codes.
- Join rooms.
- Manage participants.
- Implement host permissions.
- Implement lobby state.

Deliverable: Multiple users can join the same private room.

## Phase 3 — Character Management

- Add characters.
- Upload images.
- Support image URLs.
- Add categories and attributes.
- Prevent duplicates.
- Implement collection management.

Deliverable: Participants can create a shared character collection.

## Phase 4 — Game Engine

- Implement match initialization.
- Implement randomized assignment.
- Implement individual mode.
- Implement team mode.
- Implement turn management.
- Implement question and answer flow.
- Implement guessing logic.
- Implement victory conditions.

Deliverable: A fully testable game engine.

## Phase 5 — Real-time Communication

- Implement WebSocket manager.
- Implement authentication.
- Implement event protocol.
- Implement broadcasting.
- Implement personalized state.
- Implement reconnection.
- Implement synchronization.

Deliverable: Multiple players can play simultaneously.

## Phase 6 — Frontend

- Implement home page.
- Implement lobby.
- Implement character collection.
- Implement game screen.
- Implement match history.
- Implement results screen.
- Connect REST API.
- Connect WebSockets.

Deliverable: A playable web application.

## Phase 7 — Testing and Deployment

- Run automated tests.
- Test multiple browser sessions.
- Test individual matches.
- Test team matches.
- Test reconnections.
- Test security.
- Build frontend.
- Serve frontend through FastAPI.
- Expose application through ngrok.

Deliverable: A complete multiplayer game accessible through a public URL.

# 17. Acceptance Criteria

The MVP is considered complete when:

1. A host can create a private room.
2. Multiple participants can join using a room code.
3. Participants can submit their own characters.
4. The host can start a match.
5. Characters are randomly assigned.
6. Each participant sees other participants' characters.
7. No participant can see their own character.
8. Players can ask questions in alternating turns.
9. Players can submit free-text answers.
10. Questions and answers are synchronized in real time.
11. Players can guess at any time.
12. Incorrect guesses do not consume turns.
13. Correct guesses finish the match.
14. Individual mode works.
15. Team mode works.
16. Participants can reconnect without losing match progress.
17. Match history is persisted.
18. The game works through ngrok.
19. No installation is required for participants.

# 18. Instructions for the OpenCode Agent

You are responsible for implementing this project according to this specification.

Follow these instructions:

1. Read the entire specification before implementing anything.
2. Inspect the existing repository before creating or modifying files.
3. If the repository already contains code, preserve useful existing functionality.
4. Do not overwrite existing files without inspecting them.
5. Follow the proposed modular architecture.
6. Keep business logic separate from API handlers.
7. Use type hints throughout the Python codebase.
8. Use Pydantic schemas for API validation.
9. Use TypeScript strict mode.
10. Write meaningful tests for every major game mechanic.
11. Do not hardcode player identities, characters, or room codes.
12. Do not implement secret character assignment in the frontend.
13. Never expose a player's own secret character.
14. Do not introduce unnecessary dependencies.
15. Do not implement placeholder functionality and mark it as complete.
16. Keep the README updated.
17. Use environment variables for configurable settings.
18. Run tests after each implementation phase.
19. Fix failing tests before proceeding.
20. Do not skip security requirements.

## Implementation Workflow

Work incrementally.

At the beginning:

- Inspect the repository.
- Identify the existing development environment.
- Check installed Python and Node.js versions.
- Prepare an implementation plan.
- Identify any architectural conflicts.

Then implement one phase at a time.

After each phase:

- List created and modified files.
- Explain the implemented functionality.
- Report tests executed.
- Report test results.
- Identify remaining work.

Do not attempt to generate the entire application in one massive operation.

Prioritize a working, tested backend and game engine before frontend polish.

If a requirement is ambiguous, document the assumption and choose the simplest implementation that preserves the gameplay rules.

Do not silently change the core game mechanics.

# 19. Final Development Objective

The final application should feel like a polished online party game.

Players should be able to open a link, join a private room, contribute characters, receive secret identities, interact with friends, and compete to discover who they are.

The architecture must remain maintainable and extensible so future features can include:

- Public room discovery.
- Permanent character libraries.
- Additional game modes.
- Custom categories.
- Character packs.
- Timed matches.
- Advanced team rules.
- Player statistics.
- Match replays.
- Optional automated question suggestions.

These features are future enhancements and must not delay the MVP.

**Primary development priority: A secure, reliable, fully functional multiplayer guessing game with individual and team modes.**