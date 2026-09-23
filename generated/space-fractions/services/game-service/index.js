const express = require('express');
const cookieParser = require('cookie-parser');
const path = require('path');
const { v4: uuidv4 } = require('uuid');

// In-memory session store keyed by sessionId cookie
const sessions = new Map();
// In-memory games by id
const games = new Map();

// Game state machine constants (source: StateDiagram)
const STATE = {
  Playing: 'Playing',
  Paused: 'Paused',
  GameOver: 'GameOver',
};

function newGame(ownerUserId) {
  return {
    id: uuidv4(),
    ownerUserId,
    state: STATE.Playing,
    score: 0,
    totalQuestions: 5,
    asked: 0,
    currentQuestionId: null,
    answeredQuestionIds: new Set(),
    lastResult: null, // 'correct' | 'incorrect'
    createdAt: Date.now(),
  };
}

function ensureSession(req, res, next) {
  let sid = req.cookies['sid'];
  if (!sid) {
    sid = uuidv4();
    res.cookie('sid', sid, { httpOnly: true, sameSite: 'Lax' });
  }
  if (!sessions.has(sid)) {
    sessions.set(sid, { userId: null, username: 'guest', lastGameId: null, isAdmin: false });
  }
  req.session = sessions.get(sid);
  req.sid = sid;
  next();
}

function authRequired(req, res, next) {
  if (!req.session.userId) {
    return res.status(401).json({ error: 'Not authenticated' });
  }
  next();
}

function adminRequired(req, res, next) {
  if (!req.session.isAdmin) {
    return res.status(403).json({ error: 'Admin only' });
  }
  next();
}

async function startGameService({ port, questionUrl, userUrl }) {
  const app = express();
  app.use(cookieParser());
  app.use(express.json());
  app.use(ensureSession);

  // Serve frontend
  app.use('/', express.static(path.join(__dirname, '../../frontend/public')));

  // External API: /play (source: openapi.yaml)
  app.get('/api/play', async (req, res) => {
    // Ensure user exists (guest ok)
    const game = newGame(req.session.userId || 'guest');
    games.set(game.id, game);
    req.session.lastGameId = game.id;
    res.json({ gameId: game.id });
  });
  // Alias to conform exactly to OpenAPI path
  app.get('/play', (req, res) => res.redirect(307, '/api/play'));

  // Game state endpoints implementing state transitions
  app.post('/api/game/:id/pause', (req, res) => {
    const g = games.get(req.params.id);
    if (!g) return res.status(404).json({ error: 'Game not found' });
    if (g.state !== STATE.Playing) return res.status(400).json({ error: 'Not in Playing state' });
    g.state = STATE.Paused; // transition: pause()
    res.json({ state: g.state });
  });

  app.post('/api/game/:id/resume', (req, res) => {
    const g = games.get(req.params.id);
    if (!g) return res.status(404).json({ error: 'Game not found' });
    if (g.state !== STATE.Paused) return res.status(400).json({ error: 'Not in Paused state' });
    g.state = STATE.Playing; // transition: resume()
    res.json({ state: g.state });
  });

  app.get('/api/game/:id/state', (req, res) => {
    const g = games.get(req.params.id);
    if (!g) return res.status(404).json({ error: 'Game not found' });
    res.json({
      id: g.id,
      state: g.state,
      score: g.score,
      asked: g.asked,
      totalQuestions: g.totalQuestions,
      lastResult: g.lastResult,
    });
  });

  // Orchestrate next question via Question service
  app.get('/api/game/:id/next-question', async (req, res) => {
    const g = games.get(req.params.id);
    if (!g) return res.status(404).json({ error: 'Game not found' });
    if (g.state !== STATE.Playing) return res.status(400).json({ error: 'Game is not active' });
    if (g.asked >= g.totalQuestions) {
      g.state = STATE.GameOver; // transition: gameOver()
      return res.json({ done: true, state: g.state, score: g.score });
    }
    try {
      const url = `${questionUrl}/api/questions/next?index=${g.asked}`;
      const r = await fetch(url);
      if (!r.ok) {
        console.error('Question service error', r.status, await r.text());
        return res.status(502).json({ error: 'Question service error' });
      }
      const data = await r.json();
      g.currentQuestionId = data.id;
      res.json({
        gameId: g.id,
        index: g.asked,
        prompt: data.prompt,
        options: data.options,
        questionId: data.id,
      });
    } catch (e) {
      console.error('Failed to fetch question', e);
      res.status(500).json({ error: 'Failed to fetch question' });
    }
  });

  // Submit answer: check via Question service
  app.post('/api/game/:id/answer', async (req, res) => {
    const g = games.get(req.params.id);
    if (!g) return res.status(404).json({ error: 'Game not found' });
    if (g.state !== STATE.Playing) return res.status(400).json({ error: 'Game is not active' });
    const { questionId, answer } = req.body || {};
    if (!questionId || typeof answer === 'undefined') return res.status(400).json({ error: 'Missing fields' });
    if (g.answeredQuestionIds.has(questionId)) {
      return res.status(409).json({ error: 'Question already answered' });
    }
    if (!g.currentQuestionId || questionId !== g.currentQuestionId) {
      return res.status(400).json({ error: 'Question was not issued as the current question for this game' });
    }
    // Claim the question before the service call so simultaneous submissions cannot score twice.
    g.currentQuestionId = null;
    g.answeredQuestionIds.add(questionId);
    try {
      const r = await fetch(`${questionUrl}/api/questions/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: questionId, answer }),
      });
      const data = await r.json();
      if (data.correct) {
        g.score += 1;
        g.lastResult = 'correct';
      } else {
        g.lastResult = 'incorrect';
      }
      g.asked += 1;
      if (g.asked >= g.totalQuestions) {
        g.state = STATE.GameOver; // transition: gameOver()
      }
      res.json({
        correct: data.correct,
        score: g.score,
        state: g.state,
        asked: g.asked,
        totalQuestions: g.totalQuestions,
      });
    } catch (e) {
      // Allow a genuine retry when the internal check failed before producing a result.
      g.answeredQuestionIds.delete(questionId);
      g.currentQuestionId = questionId;
      res.status(500).json({ error: 'Failed to check answer' });
    }
  });

  // View score use case
  app.get('/api/score/current', (req, res) => {
    const lastGame = req.session.lastGameId ? games.get(req.session.lastGameId) : null;
    if (!lastGame) return res.json({ hasGame: false });
    res.json({ hasGame: true, gameId: lastGame.id, score: lastGame.score, state: lastGame.state });
  });

  // View help content (simple)
  app.get('/api/help', (req, res) => {
    res.json({
      title: 'How to play Space Fractions',
      steps: [
        'Click Play to start a new game',
        'Read the fraction prompt and choose the correct answer using keyboard 1-4 or mouse',
        'Press P to pause/resume the game',
        'At the end, view your score and play again',
      ],
    });
  });

  // Proxy user endpoints for convenience
  app.post('/api/login', async (req, res) => {
    try {
      const r = await fetch(`${userUrl}/api/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req.body || {}),
      });
      const data = await r.json();
      // set session
      req.session.userId = data.userId;
      req.session.username = data.username;
      req.session.isAdmin = data.isAdmin;
      res.json(data);
    } catch (e) {
      res.status(500).json({ error: 'Login failed' });
    }
  });

  app.get('/api/me', (req, res) => {
    res.json({ userId: req.session.userId, username: req.session.username, isAdmin: req.session.isAdmin });
  });

  // Admin: update questions (use case)
  app.post('/api/admin/questions', adminRequired, async (req, res) => {
    try {
      const r = await fetch(`${questionUrl}/api/admin/questions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req.body || {}),
      });
      const data = await r.json();
      res.json(data);
    } catch (e) {
      res.status(500).json({ error: 'Failed to update questions' });
    }
  });

  return new Promise((resolve) => {
    const server = app.listen(port, () => {
      console.log(`Game service listening on ${server.address().port}`);
      resolve({ app, server });
    });
  });
}

module.exports = { startGameService, STATE };
