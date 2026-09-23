Space Fractions — Local Desktop Edition

Overview
Space Fractions is an interactive learning game to practice fraction skills. This repository implements the architecture-described game as a local desktop application with a graphical UI using Python 3 and Tkinter. It contains an intro screen, main menu, fraction questions, answer validation with feedback, visible score updates, progression, a final screen, a help screen, and an admin-only question editor. It runs entirely locally; no browser or hosted server is required.

Source facts preserved and mapped
- Architectural style in source: Microservices with GameComponent, QuestionComponent, and UserComponent; web-based UI; cloud deployment with APIs and databases.
- Use cases: Play Game, View Score, View Help, Update Questions (admin).
- State diagram: Playing, Paused, GameOver with transitions pause(), resume(), gameOver().

Local desktop adaptation decisions
- Delivery constraint override: Although the source targets web and cloud microservices, this implementation is a single-process local desktop app per the explicit task requirement. We map microservice components to Python modules/packages with clear responsibilities and interfaces:
  - GameComponent → space_fractions/core/game.py (game state and logic) and space_fractions/ui/* (UI).
  - QuestionComponent → space_fractions/services/question_service.py (load/save questions from local JSON).
  - UserComponent → space_fractions/core/user.py and services/user_service.py (simple local role selection).
- API contracts (OpenAPI/proto) are represented as internal function interfaces since there is no network. We document this mapping rather than exposing HTTP/gRPC.
- Persistence: Replaces PostgreSQL/Redis with a local JSON file for questions and a small JSON file for last score. This keeps user-facing behavior while avoiding heavy infrastructure on a desktop.
- Authn/Authz: Replaces OAuth2 with a minimal local role check (username + admin password) sufficient to gate the Update Questions use case. This is not production-grade security.
- Deployment/observability/k8s guidance is intentionally deferred as out of scope for a single-user desktop game. See Deferred infrastructure below.

Implemented use cases and screens
- Intro: brief animated intro with Skip option.
- Main Menu: Start Game, View Score, View Help, Admin (Update Questions), Login/Logout, Exit.
- Play Game: Multiple fraction questions with multiple-choice answers, keyboard navigation (1–4 to select, Enter to submit), Pause/Resume, feedback, live score.
- View Score: Shows last completed game score and total questions.
- View Help: Instructions on how to play and keyboard shortcuts.
- Update Questions (Admin): Simple local editor to add/edit/remove questions and save to data/questions.json. Requires admin role.
- Game Over: Final score summary with options to replay or return to menu.

State transitions realized
- Playing → Paused via Pause button or P key; Paused → Playing via Resume; Playing → GameOver when questions are exhausted.

Testing
- Non-GUI domain tests use pytest to validate:
  - Question loading
  - Answer validation correctness
  - Scoring accumulation
  - Progression through all questions and GameOver state
  - Pause/Resume state transitions

Quick start
Prerequisites
- Python 3.9+ with Tkinter available. On macOS, Tkinter ships with the system Python; for virtualenvs make sure Tkinter is included.

Setup
- Optional: create and activate a virtual environment
- Install dev dependencies for tests only:
  pip install -r requirements.txt

Run the desktop game
  python main.py

Run tests
  pytest -q

Repository structure
- main.py — entry point launching the Tkinter app
- space_fractions/
  - app.py — App container and navigation between screens
  - core/
    - game.py — Game state machine and scoring
    - question.py — Question model
    - user.py — User and roles
  - services/
    - question_service.py — Load/save questions from JSON
    - user_service.py — Simple in-memory session and last score persistence
  - ui/
    - intro.py, menu.py, game_view.py, help_view.py, score_view.py, admin_view.py — Screens
- data/
  - questions.json — Starter fraction questions
  - last_score.json — Created at runtime
- tests/
  - test_game_logic.py — Domain tests (no GUI)

Deferred infrastructure (documented)
- Source assumes microservices, REST/gRPC APIs, PostgreSQL/Redis, Kubernetes, OAuth2, and observability stacks. These are intentionally not implemented to honor the explicit desktop constraint. Their functional intent is preserved within local modules and data files:
  - OpenAPI / proto contracts → Python interfaces between components
  - PostgreSQL/Redis → local JSON persistence
  - OAuth2 → local role gate for admin actions
  - Kubernetes/CI/CD/monitoring → not applicable for single-user local app

Assumptions and ambiguities
- Concurrency and cloud-scale assumptions (A1: 1000 concurrent users, A2: 1-hour sessions) are not applicable to a local desktop game; we focus on single-user robustness.
- Admin authentication: a fixed demo password "admin" is used locally to enable Update Questions. Replace with proper auth if deploying differently.
- Introductory movie: implemented as a lightweight animated text sequence due to absence of media assets.

Accessibility and usability
- Keyboard: 1–4 to select options, Enter to submit, P to pause/resume, Esc to return to menu where appropriate, Tab focus order.
- Visuals: High-contrast text and focus highlight in widgets.

License
This project is provided for educational demonstration purposes.

Why local desktop instead of web
The source documentation is web/microservices oriented. Per the explicit delivery constraint of this task, we mapped the design to a local desktop runtime (Tkinter) while preserving functional behavior and component responsibilities.
