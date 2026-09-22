Space Fractions — Microservices demo per architecture

Source facts
- Architectural style: Microservices (sections A/C)
- Components: GameComponent, QuestionComponent, UserComponent (section-4)
- External API contract: OpenAPI with /play (sections 11, 39)
- Internal contract: gRPC/proto with GameService.Play (sections 12, 39)
- Data model: games table with JSONB state (sections 13, 39)
- State model: Playing -> Paused -> Playing; Playing -> GameOver (StateDiagram)
- Use cases: End User can Play Game, View Score, View Help; Admin can Update Questions (UseCaseDiagram)

Explicit assumptions from source
- A1: 1000 concurrent users; 1h sessions (section-37)

Ambiguities and conflicts
- Architecture lists many infrastructure choices (PostgreSQL, Redis, RabbitMQ, Elasticsearch, OAuth2, Prometheus, Jenkins, Kubernetes, Docker, Terraform). These are out-of-scope for local runnable behavior here. We implement functional behavior and provide DDL and k8s snippet as artifacts. Infrastructure is deliberately deferred.
- Only /play is specified in OpenAPI, yet the Use Case and diagrams require more interactions (answering, scoring, help, state transitions, and admin question updates). We preserve the /play contract and add minimal additional endpoints to satisfy the use cases and state transitions as runnable behavior.

Implementation decisions
- Stack: Node.js + Express.js per sections 8–9 (GameComponent recommended stack). We implement three small HTTP microservices in a single repository: game-service, question-service, user-service.
- Persistence: In-memory stores for local run/tests to avoid external dependencies. SQL DDL files are provided to reflect the intended schema (section-13). Rationale: keeps runnable behavior without requiring DB/Redis in CI.
- Auth: Minimal token service (user-service) that issues and validates bearer tokens. Question updates require an admin token. This stands in for OAuth2 (section-19) and is intentionally simple for local runs.
- Internal integration: game-service calls question-service over HTTP (Node18 global fetch). question-service calls user-service /validate for admin-only routes.
- State enforcement: game-service enforces the Playing/Paused/GameOver transitions exactly as in the StateDiagram.

How to run (requires Node.js 18+)
- Install dependencies: from repository root run:
  npm install --prefix services/game-service
  npm install --prefix services/question-service
  npm install --prefix services/user-service

- Start services individually (in three terminals):
  PORT=3001 QUESTION_BASE=http://localhost:3002 node services/game-service/src/start.js
  PORT=3002 USER_BASE=http://localhost:3003 node services/question-service/src/start.js
  PORT=3003 node services/user-service/src/start.js

- Example flow
  1) Get an admin token: curl -s -X POST http://localhost:3003/token -H 'Content-Type: application/json' -d '{"role":"admin"}'
  2) Add/update a question: curl -s -X POST http://localhost:3002/questions -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' -d '{"prompt":"1/2 + 1/4 = ?","options":["1/4","3/4","2/3"],"answerIndex":1}'
  3) Start a game: curl -s http://localhost:3001/play
  4) Fetch the next question and answer it:
     curl -s http://localhost:3001/game/<gameId>/question
     curl -s -X POST http://localhost:3001/game/<gameId>/answer -H 'Content-Type: application/json' -d '{"questionId":"...","answerIndex":1}'
  5) View score: curl -s http://localhost:3001/score/<gameId>
  6) View help: curl -s http://localhost:3001/help
  7) State transitions:
     curl -s -X POST http://localhost:3001/game/<gameId>/pause
     curl -s -X POST http://localhost:3001/game/<gameId>/resume
     curl -s -X POST http://localhost:3001/game/<gameId>/gameover

Testing
- Tests are written with Node's built-in test runner (node:test). They spin up all three services in-process on ephemeral ports and exercise:
  - Play Game (create game, get a question, answer, get result)
  - View Score
  - View Help
  - Update Questions (admin-only)
  - State transitions and validation of invalid transition

Run tests:
  npm test

Artifacts (from architecture deliverables)
- architecture.md: brief extraction of relevant sections
- openapi.yaml: as provided for /play
- internal.proto: as provided
- k8s/spacefractions-deployment.yaml: as provided
- sql/game_ddl.sql: as provided
- traceability_matrix.csv: as provided

Deferred infrastructure (with reasons)
- PostgreSQL/Redis/RabbitMQ/Elasticsearch/OAuth2/Prometheus/Jenkins/Docker/Terraform/Kubernetes are not started locally to keep the repository self-contained and runnable on a plain Node18 environment. Their use is acknowledged in code comments and artifacts, and would be integrated behind configuration flags in a production environment.

Mapping of use cases to code and tests
- Play Game: services/game-service (routes /play, /game/:id/question, /game/:id/answer) — tested in test/app.test.js
- View Score: services/game-service (route /score/:id) — tested
- View Help: services/game-service (route /help) — tested
- Update Questions: services/question-service (route POST /questions, admin-only) — tested
- State transitions: services/game-service (routes /game/:id/pause, /resume, /gameover) — tested

License
- For demo purposes only.
