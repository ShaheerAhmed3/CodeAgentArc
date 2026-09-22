// Integration tests using Node's built-in test runner
// Covers: Play Game, View Score, View Help, Update Questions (admin), State transitions

const { test, before, after } = require('node:test');
const assert = require('node:assert');

const { createApp: createUserApp } = require('../services/user-service/src/app');
const { createApp: createQuestionApp } = require('../services/question-service/src/app');
const { createApp: createGameApp } = require('../services/game-service/src/app');

let servers = [];
let bases = {};

async function listen(app) {
  return new Promise((resolve) => {
    const srv = app.listen(0, () => {
      const { port } = srv.address();
      resolve({ srv, port });
    });
  });
}

before(async () => {
  // Start user-service
  const userApp = createUserApp();
  const { srv: userSrv, port: userPort } = await listen(userApp);
  servers.push(userSrv);
  bases.user = `http://localhost:${userPort}`;

  // Start question-service with USER_BASE
  const questionApp = createQuestionApp({ USER_BASE: bases.user });
  const { srv: questionSrv, port: questionPort } = await listen(questionApp);
  servers.push(questionSrv);
  bases.question = `http://localhost:${questionPort}`;

  // Start game-service with QUESTION_BASE
  const gameApp = createGameApp({ QUESTION_BASE: bases.question });
  const { srv: gameSrv, port: gamePort } = await listen(gameApp);
  servers.push(gameSrv);
  bases.game = `http://localhost:${gamePort}`;
});

after(async () => {
  for (const s of servers) s.close();
});

async function jsonFetch(url, opts = {}) {
  const r = await fetch(url, { ...opts, headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) } });
  const body = await r.json().catch(() => null);
  return { status: r.status, body };
}

// helper to discover the correct index for a given question via question-service /check
async function discoverCorrectIndex(question) {
  for (let i = 0; i < question.options.length; i++) {
    const chk = await jsonFetch(`${bases.question}/check`, { method: 'POST', body: JSON.stringify({ questionId: question.id, answerIndex: i }) });
    if (chk.status === 200 && chk.body.correct) return i;
  }
  throw new Error('No correct index found');
}

// Use case: Play Game -> get gameId, fetch question, submit correct answer once
test('Play Game end-to-end and scoring', async () => {
  const play = await jsonFetch(`${bases.game}/play`);
  assert.strictEqual(play.status, 200);
  const gameId = play.body.gameId;
  assert.ok(gameId);

  const qres = await jsonFetch(`${bases.game}/game/${gameId}/question`);
  assert.strictEqual(qres.status, 200);
  const question = qres.body;
  assert.ok(question.id && question.prompt && Array.isArray(question.options));

  const correctIndex = await discoverCorrectIndex(question);

  const correct = await jsonFetch(`${bases.game}/game/${gameId}/answer`, {
    method: 'POST',
    body: JSON.stringify({ questionId: question.id, answerIndex: correctIndex })
  });
  assert.strictEqual(correct.status, 200);
  assert.strictEqual(correct.body.correct, true);
  const scoreAfterCorrect = correct.body.score;
  assert.strictEqual(scoreAfterCorrect, 1);
});

// New tests: wrong-question submission and replay rejection
test('Reject answering a question that was never issued to the game', async () => {
  // Start a new game and fetch its issued question first (deterministic)
  const play = await jsonFetch(`${bases.game}/play`);
  const gameId = play.body.gameId;
  const qres = await jsonFetch(`${bases.game}/game/${gameId}/question`);
  assert.strictEqual(qres.status, 200);
  const issuedQuestion = qres.body;

  // Now admin creates a distinct new question that was not issued to this game
  const adminTok = await jsonFetch(`${bases.user}/token`, { method: 'POST', body: JSON.stringify({ role: 'admin' }) });
  const adminToken = adminTok.body.token;
  const newQ = await jsonFetch(`${bases.question}/questions`, { method: 'POST', headers: { Authorization: `Bearer ${adminToken}` }, body: JSON.stringify({ prompt: '3/5 + 1/5 = ?', options: ['1/5', '3/5', '4/5'], answerIndex: 2 }) });
  assert.strictEqual(newQ.status, 201);
  assert.notStrictEqual(newQ.body.id, issuedQuestion.id, 'Newly created question should differ from the one issued to the game');

  // Try to answer using the admin-created question id which was never issued to this game
  const wrongQAnswer = await jsonFetch(`${bases.game}/game/${gameId}/answer`, { method: 'POST', body: JSON.stringify({ questionId: newQ.body.id, answerIndex: 0 }) });
  assert.ok(wrongQAnswer.status >= 400, `expected rejection, got ${wrongQAnswer.status}`);
});

test('Reject replay: cannot answer the same question twice', async () => {
  const play = await jsonFetch(`${bases.game}/play`);
  const gameId = play.body.gameId;
  const qres = await jsonFetch(`${bases.game}/game/${gameId}/question`);
  const question = qres.body;
  const correctIndex = await discoverCorrectIndex(question);

  const first = await jsonFetch(`${bases.game}/game/${gameId}/answer`, { method: 'POST', body: JSON.stringify({ questionId: question.id, answerIndex: correctIndex }) });
  assert.strictEqual(first.status, 200);

  const replay = await jsonFetch(`${bases.game}/game/${gameId}/answer`, { method: 'POST', body: JSON.stringify({ questionId: question.id, answerIndex: correctIndex }) });
  assert.ok(replay.status >= 400, `expected rejection on replay, got ${replay.status}`);
});

// Use case: View Score
test('View Score returns current score', async () => {
  const play = await jsonFetch(`${bases.game}/play`);
  const gameId = play.body.gameId;
  const score = await jsonFetch(`${bases.game}/score/${gameId}`);
  assert.strictEqual(score.status, 200);
  assert.deepStrictEqual(score.body, { gameId, score: 0 });
});

// Use case: View Help
test('View Help returns help text', async () => {
  const help = await jsonFetch(`${bases.game}/help`);
  assert.strictEqual(help.status, 200);
  assert.ok(help.body.help.includes('Space Fractions'));
});

// Use case: Update Questions (admin-only)
test('Admin can update questions; non-admin forbidden', async () => {
  // Get tokens
  const adminTok = await jsonFetch(`${bases.user}/token`, { method: 'POST', body: JSON.stringify({ role: 'admin' }) });
  assert.strictEqual(adminTok.status, 200);
  const adminToken = adminTok.body.token;

  const userTok = await jsonFetch(`${bases.user}/token`, { method: 'POST', body: JSON.stringify({ role: 'user' }) });
  const userToken = userTok.body.token;

  // Non-admin attempt
  const noAuth = await jsonFetch(`${bases.question}/questions`, { method: 'POST', body: JSON.stringify({ prompt: 'X', options: ['1'], answerIndex: 0 }) });
  assert.strictEqual(noAuth.status, 401);

  const userTry = await jsonFetch(`${bases.question}/questions`, { method: 'POST', headers: { Authorization: `Bearer ${userToken}` }, body: JSON.stringify({ prompt: 'X', options: ['1'], answerIndex: 0 }) });
  assert.strictEqual(userTry.status, 403);

  const adminTry = await jsonFetch(`${bases.question}/questions`, { method: 'POST', headers: { Authorization: `Bearer ${adminToken}` }, body: JSON.stringify({ prompt: '2/3 + 1/3 = ?', options: ['1', '2/3', '3/3'], answerIndex: 0 }) });
  assert.strictEqual(adminTry.status, 201);
  assert.strictEqual(adminTry.body.prompt, '2/3 + 1/3 = ?');
});

// State transitions
test('State transitions: pause, resume, gameover; invalid transitions rejected', async () => {
  const play = await jsonFetch(`${bases.game}/play`);
  const gameId = play.body.gameId;

  // initial state is Playing; pause is allowed
  const pause = await jsonFetch(`${bases.game}/game/${gameId}/pause`, { method: 'POST' });
  assert.strictEqual(pause.status, 200);
  assert.strictEqual(pause.body.state, 'Paused');

  // gameover from Paused should be invalid
  const badOver = await jsonFetch(`${bases.game}/game/${gameId}/gameover`, { method: 'POST' });
  assert.strictEqual(badOver.status, 400);

  // resume to Playing
  const resume = await jsonFetch(`${bases.game}/game/${gameId}/resume`, { method: 'POST' });
  assert.strictEqual(resume.status, 200);
  assert.strictEqual(resume.body.state, 'Playing');

  // gameover from Playing is allowed
  const over = await jsonFetch(`${bases.game}/game/${gameId}/gameover`, { method: 'POST' });
  assert.strictEqual(over.status, 200);
  assert.strictEqual(over.body.state, 'GameOver');

  // further transitions invalid
  const badResume = await jsonFetch(`${bases.game}/game/${gameId}/resume`, { method: 'POST' });
  assert.strictEqual(badResume.status, 400);
});
