# Space Fractions

Source facts from architecture:
- Style: Microservices (GameComponent, QuestionComponent, UserComponent)
- Delivery: Web-based interactive learning tool with intro movie, main menu, question flow, ending scene with feedback
- External API contract: OpenAPI /play returning gameId
- Internal contract: GameService.Play in protobuf
- Data models: games table defined; QuestionComponent data durability

Implementation summary (minimum coherent system):
- Tech stack (preserving recommended defaults where feasible for dev): Node.js 18, Express.js 4. PostgreSQL/Redis/RabbitMQ/Elasticsearch/Prometheus/Jenkins/Terraform are explicitly deferred for local dev; in-memory + JSON-only flows are used. Reasons: avoid disproportionate infra for the educational demo while user-facing behavior stays complete.
- Three microservices run in a single Node process on distinct ports for simplicity:
  - Game service (port 3000): serves UI, orchestrates game logic, exposes API implementing state transitions (Playing → Paused → Playing, Playing → GameOver). Proxies auth and admin updates.
  - Question service (port 3001): manages questions, provides next/check APIs, supports admin update.
  - User service (port 3002): minimal login issuing a user identity; username "admin" yields admin role (temporary dev-only policy).
- Frontend: Accessible, responsive, vanilla HTML/CSS/JS served by the Game service. Screens implemented: Intro (animated canvas), Main Menu, Game (questions with keyboard control and pause/resume), Score, Help, Admin (update questions).

Ambiguities/conflicts and resolutions:
- Traceability table references sql/question_ddl.sql while deliverables list sql/game_ddl.sql. Implemented both to honor both references; QuestionComponent persists questions in production (assumption), GameComponent persists game state (source SQL). For dev, both are deferred with in-memory stores.
- Authn/Authz specifies OAuth2. Deferred; replaced by temporary username-based login to satisfy End User/Admin use cases without introducing secrets in browser code. Documented as a dev-only choice.
- Microservices vs single process: architecture requires microservices; to minimize local complexity, services are isolated as Express apps on separate ports but launched by a single node process. Containerization/Kubernetes manifests are provided but not wired for local demo.

Assumptions (from source and additional for implementation):
- A1 (source): Up to 1000 concurrent users; out of scope for local demo but supported by stateless APIs and separate services.
- Additional: For demo, a game has 5 questions. Question bank can be updated via Admin page JSON upload.

Security deferments:
- OAuth2, TLS, secret rotation, and service mesh are not implemented in this local build. Admin role is assigned if username is "admin" (insecure; dev-only). No secrets are sent to the frontend; only a transient session cookie (random id) is used by Game service.

Operations deferments:
- PostgreSQL/Redis/RabbitMQ/Elasticsearch/Prometheus/Jenkins/Terraform/Docker are intentionally not provisioned. SQL DDLs and k8s deployment snippet are included per architecture deliverables.

How to run (requires Node.js >= 18):
1. Install Node.js 18 (e.g., via nvm). Ensure `node -v` prints v18+.
2. Install dependencies: `npm install`
3. Start all services and UI: `npm start`
4. Open the frontend: http://localhost:3000

Frontend usage:
- Intro screen shows a spaceship animation; use Skip Intro or Start to reach the menu.
- Main Menu: Login with a username (type "admin" to access the Admin screen). Play Game starts a new game; View Score shows your last game score; View Help displays instructions.
- Game: Use number keys 1-4 or click options to answer. Press P or use Pause/Resume buttons to pause/resume. After 5 questions, the Score screen appears.
- Admin: Paste a JSON array of questions with fields { id, prompt, options, answerIndex } and submit to replace the question bank.

API mapping to use cases and tests:
- End User — Play Game: `GET /api/play`, `GET /api/game/:id/next-question`, `POST /api/game/:id/answer`, state transitions `POST /api/game/:id/(pause|resume)`.
- End User — View Score: `GET /api/score/current`.
- End User — View Help: `GET /api/help`.
- Admin — Update Questions: `POST /api/admin/questions` (requires admin login via `/api/login` with username "admin").

Artifacts included (from architecture deliverables):
- openapi.yaml, internal.proto, k8s/spacefractions-deployment.yaml, sql/game_ddl.sql, sql/question_ddl.sql, traceability_matrix.csv

Testing
- Unit/integration tests use Jest and Supertest to exercise the Game/Question APIs and the state machine transitions, plus jsdom-based UI tests for the question flow calling real service endpoints.
- The five tests also reject unissued-question submissions and repeated answers so one question cannot score twice.
- Note: Running tests requires Node/npm. In CI, run: `npm test`.

Accessibility/UX notes:
- Visible focus styles and keyboard operation for all interactive elements.
- ARIA labels and polite live regions for dynamic content (prompt, feedback, user status).
- Responsive grid for options and readable contrast.

Project structure
- services/game-service: Game logic + UI server
- services/question-service: Questions API and admin update
- services/user-service: Minimal auth
- frontend/public: Static assets (HTML/CSS/JS)
- sql, k8s, openapi.yaml, internal.proto: architecture artifacts

License
- Educational demo.
