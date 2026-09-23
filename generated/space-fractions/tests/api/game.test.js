const request = require('supertest');
const { startGameService, STATE } = require('../../services/game-service');
const { startQuestionService } = require('../../services/question-service');
const { startUserService } = require('../../services/user-service');

let servers = {};
let ports = { game: 0, question: 0, user: 0 };
let baseUrl;

beforeAll(async () => {
  servers.q = await startQuestionService(ports.question);
  const qPort = servers.q.server.address().port;
  servers.u = await startUserService(ports.user);
  const uPort = servers.u.server.address().port;
  servers.g = await startGameService({ port: ports.game, questionUrl: `http://127.0.0.1:${qPort}`, userUrl: `http://127.0.0.1:${uPort}` });
  const gPort = servers.g.server.address().port;
  baseUrl = `http://127.0.0.1:${gPort}`;
});

afterAll(async () => {
  await new Promise((r) => servers.g.server.close(r));
  await new Promise((r) => servers.q.server.close(r));
  await new Promise((r) => servers.u.server.close(r));
});

describe('Game API - Play Game use case and state transitions', () => {
  test('Start game returns gameId and progresses through questions ending in GameOver', async () => {
    const agent = request.agent(baseUrl);
    const start = await agent.get('/api/play').expect(200);
    const gameId = start.body.gameId;

    // Loop through 5 questions answering 0 each time
    for (let i = 0; i < 5; i++) {
      const q = await agent.get(`/api/game/${gameId}/next-question`).expect(200);
      expect(q.body).toHaveProperty('prompt');
      const ans = await agent.post(`/api/game/${gameId}/answer`).send({ questionId: q.body.questionId, answer: 0 }).expect(200);
      expect(ans.body).toHaveProperty('asked');
    }

    const state = await agent.get(`/api/game/${gameId}/state`).expect(200);
    expect(state.body.state).toBe('GameOver');
  });

  test('Pause and resume transitions', async () => {
    const agent = request.agent(baseUrl);
    const start = await agent.get('/api/play').expect(200);
    const gameId = start.body.gameId;
    const paused = await agent.post(`/api/game/${gameId}/pause`).expect(200);
    expect(paused.body.state).toBe('Paused');
    const resumed = await agent.post(`/api/game/${gameId}/resume`).expect(200);
    expect(resumed.body.state).toBe('Playing');
  });

  test('Rejects unissued questions and answer replay', async () => {
    const agent = request.agent(baseUrl);
    const start = await agent.get('/api/play').expect(200);
    const gameId = start.body.gameId;
    const q = await agent.get(`/api/game/${gameId}/next-question`).expect(200);

    await agent.post(`/api/game/${gameId}/answer`)
      .send({ questionId: 'not-issued', answer: 0 })
      .expect(400);

    await agent.post(`/api/game/${gameId}/answer`)
      .send({ questionId: q.body.questionId, answer: 0 })
      .expect(200);

    await agent.post(`/api/game/${gameId}/answer`)
      .send({ questionId: q.body.questionId, answer: 0 })
      .expect(409);

    const state = await agent.get(`/api/game/${gameId}/state`).expect(200);
    expect(state.body.asked).toBe(1);
  });
});


describe('Admin - Update Questions use case', () => {
  test('Admin can update question bank via proxy endpoint', async () => {
    const agent = request.agent(baseUrl);
    // Login as admin
    const login = await agent.post('/api/login').send({ username: 'admin' }).expect(200);
    expect(login.body.isAdmin).toBe(true);
    const me = await agent.get('/api/me').expect(200);
    expect(me.body.isAdmin).toBe(true);
    const resp = await agent.post('/api/admin/questions').send({ questions: [
      { id: 'a1', prompt: '1/2 + 1/2 = ?', options: ['1/2','1','2','0'], answerIndex: 1 },
    ]}).expect(200);
    expect(resp.body.ok).toBe(true);
    expect(resp.body.count).toBe(1);
  });
});
