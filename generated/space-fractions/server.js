// Entry point to start all microservices for local development
// Source fact: Architecture style is Microservices with GameComponent, QuestionComponent, UserComponent.
// Implementation decision: run three Express apps in one Node process on distinct ports to minimize infra.

const { startGameService } = require('./services/game-service');
const { startQuestionService } = require('./services/question-service');
const { startUserService } = require('./services/user-service');

async function main() {
  const ports = {
    game: process.env.GAME_PORT ? parseInt(process.env.GAME_PORT, 10) : 3000,
    question: process.env.QUESTION_PORT ? parseInt(process.env.QUESTION_PORT, 10) : 3001,
    user: process.env.USER_PORT ? parseInt(process.env.USER_PORT, 10) : 3002,
  };

  // Start Question and User first; Game depends on them
  await startQuestionService(ports.question);
  await startUserService(ports.user);
  await startGameService({
    port: ports.game,
    questionUrl: `http://localhost:${ports.question}`,
    userUrl: `http://localhost:${ports.user}`,
  });

  console.log('Space Fractions services started:', ports);
  console.log(`Frontend available at http://localhost:${ports.game}`);
}

main().catch((err) => {
  console.error('Failed to start services', err);
  process.exit(1);
});
