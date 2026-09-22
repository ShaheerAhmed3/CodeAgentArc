This file extracts and preserves key architectural artifacts from the provided documentation.

- Architectural style: Microservices
- Components: GameComponent, QuestionComponent, UserComponent
- OpenAPI contract: see openapi.yaml
- Internal contract: see internal.proto
- Data model: see sql/game_ddl.sql
- K8s deployment snippet: see k8s/spacefractions-deployment.yaml
- Traceability matrix: see traceability_matrix.csv

The repository adds minimal endpoints implementing the use cases and state transitions as runnable behavior. Infra pieces (DB/Redis/RabbitMQ/etc.) are explicitly deferred for local runs.
