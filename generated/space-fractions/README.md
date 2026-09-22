# Space Fractions

A runnable, API-based fraction game built as three small Node.js and Express services.
This repository is the checked-in example produced by CodeAgentArc from the
files under `architecture/inputs/` at the project root. It has no browser
interface.

## What runs

| Service | Default port | Responsibility |
| --- | --- | --- |
| Game | 3001 | Starts games, serves questions, checks answers, tracks score and state |
| Question | 3002 | Stores questions, returns questions without answers, checks answers, accepts admin updates |
| User | 3003 | Issues and validates simple role tokens for local testing |

The Game service calls Question over HTTP. Question calls User to authorize
admin updates. Games and questions live in memory, so restarting a service
resets its data. The token is simply `user` or `admin`; this demonstrates the
service interaction and must not be treated as secure authentication.

## Install and test

Requires Node.js 18 or newer. The following commands work in macOS Terminal and
Windows PowerShell. From this directory:

```sh
npm install
npm test
```

The seven tests start and stop all three services automatically.

## Run locally on macOS

Start each service in a separate Terminal window from this directory:

```sh
PORT=3003 node services/user-service/src/start.js
PORT=3002 USER_BASE=http://localhost:3003 node services/question-service/src/start.js
PORT=3001 QUESTION_BASE=http://localhost:3002 node services/game-service/src/start.js
```

## Run locally on Windows

Start each service in a separate PowerShell window from this directory:

```powershell
$env:PORT="3003"; node services/user-service/src/start.js
$env:PORT="3002"; $env:USER_BASE="http://localhost:3003"; node services/question-service/src/start.js
$env:PORT="3001"; $env:QUESTION_BASE="http://localhost:3002"; node services/game-service/src/start.js
```

The order above starts dependencies before callers. Each service also has a
`GET /healthz` endpoint.

The examples below use `curl`, which is available on macOS. On Windows, use
`curl.exe` if PowerShell maps `curl` to another command.

## Try a game

1. `curl -s http://localhost:3001/play` returns a `gameId`.
2. Replace `<gameId>` below with that value. `curl -s http://localhost:3001/game/<gameId>/question` returns an ID, prompt, and options without the correct answer.
3. Submit that question ID and an option index:

   ```sh
   curl -s -X POST http://localhost:3001/game/<gameId>/answer \
     -H 'Content-Type: application/json' \
     -d '{"questionId":"<questionId>","answerIndex":1}'
   ```

4. `curl -s http://localhost:3001/score/<gameId>` shows the current score.
5. `curl -s http://localhost:3001/help` shows game instructions.

To add a question, get an admin token and send it to the Question service:

```sh
curl -s -X POST http://localhost:3003/token \
  -H 'Content-Type: application/json' -d '{"role":"admin"}'
curl -s -X POST http://localhost:3002/questions \
  -H 'Authorization: Bearer admin' -H 'Content-Type: application/json' \
  -d '{"prompt":"1/2 + 1/4 = ?","options":["1/4","3/4","2/3"],"answerIndex":1}'
```

For a game in `Playing`, `POST /game/<gameId>/pause` moves it to `Paused`,
`POST /game/<gameId>/resume` returns it to `Playing`, and
`POST /game/<gameId>/gameover` ends it. Invalid transitions return HTTP 400.
Only a question issued to the current game can be answered, and one question
cannot score twice. A request to update questions without an admin token fails.

The seven integration tests start all three services on temporary ports and
exercise play, score, help, admin updates, state transitions, and answer replay.
They need no separate server process or database.

## Architecture choices and limits

The architecture describes three components, a `/play` OpenAPI contract,
internal service and data contracts, and use cases for playing, viewing score
and help, and updating questions. The example uses UUID game IDs; the source
OpenAPI excerpt specified an integer, so this repository's `openapi.yaml`
records the actual UUID response. Additional HTTP routes make the other use
cases runnable. The source also
mentions PostgreSQL, Redis, RabbitMQ, Elasticsearch, OAuth2, Kubernetes, and
other infrastructure; these are represented by reference artifacts where
available, but are not running dependencies of this local example.

The repository includes `openapi.yaml`, `internal.proto`, SQL schema examples,
`k8s/spacefractions-deployment.yaml`, `architecture.md`, and
`traceability_matrix.csv`. The proto and Kubernetes files document intended
contracts and deployment shape; the local services communicate over HTTP and
do not run in Kubernetes. The SQL files describe future persistence, while
the running app uses memory. This implementation has no browser UI or
production authentication. The Question service's `/check` route is reachable
directly in this local version, so answers can be probed. A real deployment
would restrict internal routes and replace the token service.
