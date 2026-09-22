// Game Service - Express app
// Implements: /play, /game/:id/question, /game/:id/answer, /score/:id, /help
// State transitions per StateDiagram: /game/:id/pause, /resume, /gameover

const express = require('express');
const { v4: uuidv4 } = require('uuid');

function createApp(config = {}) {
  const app = express();
  app.use(express.json());

  const QUESTION_BASE = config.QUESTION_BASE || process.env.QUESTION_BASE || 'http://localhost:3002';

  // In-memory game store
  // gameId -> { id, score, state, currentQuestionId, issued: Set, answered: Set }
  const games = new Map();

  // Helpers
  const states = {
    Playing: 'Playing',
    Paused: 'Paused',
    GameOver: 'GameOver',
  };

  function ensureGame(req, res, next) {
    const id = req.params.id;
    const g = games.get(id);
    if (!g) return res.status(404).json({ error: 'Game not found' });
    req.game = g;
    next();
  }

  // OpenAPI-specified route: returns only { gameId }
  app.get('/play', async (req, res) => {
    const id = uuidv4();
    const game = { id, score: 0, state: states.Playing, currentQuestionId: null, issued: new Set(), answered: new Set() };
    games.set(id, game);
    res.json({ gameId: id });
  });

  // Return next question for a game
  app.get('/game/:id/question', ensureGame, async (req, res) => {
    if (req.game.state !== states.Playing) {
      return res.status(400).json({ error: `Cannot fetch question while state=${req.game.state}` });
    }
    try {
      const r = await fetch(`${QUESTION_BASE}/question`);
      if (!r.ok) throw new Error(`Question service error: ${r.status}`);
      const q = await r.json();
      req.game.currentQuestionId = q.id;
      req.game.issued.add(q.id);
      // Do not leak correct answer; question-service already omits it
      return res.json(q);
    } catch (e) {
      return res.status(502).json({ error: e.message });
    }
  });

  // Submit an answer
  app.post('/game/:id/answer', ensureGame, async (req, res) => {
    if (req.game.state !== states.Playing) {
      return res.status(400).json({ error: `Cannot answer while state=${req.game.state}` });
    }
    const { questionId, answerIndex } = req.body || {};
    if (!questionId || typeof answerIndex !== 'number') {
      return res.status(400).json({ error: 'questionId and answerIndex are required' });
    }

    // Enforce that an active question exists and the submitted question matches it
    if (!req.game.currentQuestionId) {
      return res.status(400).json({ error: 'No active question for this game. Fetch /game/:id/question first.' });
    }
    if (questionId !== req.game.currentQuestionId) {
      // If it was never issued to this game, make that explicit
      if (!req.game.issued.has(questionId)) {
        return res.status(400).json({ error: 'Question was not issued to this game' });
      }
      return res.status(400).json({ error: 'Submitted question does not match the current active question' });
    }
    // Prevent replay: only one submission per issued question
    if (req.game.answered.has(questionId)) {
      return res.status(409).json({ error: 'This question has already been answered for this game' });
    }

    try {
      const r = await fetch(`${QUESTION_BASE}/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ questionId, answerIndex }),
      });
      if (!r.ok) throw new Error(`Question service error: ${r.status}`);
      const result = await r.json();

      // Mark answered and clear current active question regardless of correctness
      req.game.answered.add(questionId);
      req.game.currentQuestionId = null;

      if (result.correct) req.game.score += 1;
      return res.json({ correct: result.correct, score: req.game.score });
    } catch (e) {
      return res.status(502).json({ error: e.message });
    }
  });

  // View score
  app.get('/score/:id', ensureGame, (req, res) => {
    res.json({ gameId: req.game.id, score: req.game.score });
  });

  // Help endpoint
  app.get('/help', (req, res) => {
    res.json({ help: 'Welcome to Space Fractions! Solve fraction problems. Use /play to start, /game/:id/question to get a question, and /game/:id/answer to submit.' });
  });

  // State transition helpers
  function transition(game, to) {
    const from = game.state;
    if (from === states.Playing && to === states.Paused) { game.state = states.Paused; return true; }
    if (from === states.Paused && to === states.Playing) { game.state = states.Playing; return true; }
    if (from === states.Playing && to === states.GameOver) { game.state = states.GameOver; return true; }
    return false;
  }

  app.post('/game/:id/pause', ensureGame, (req, res) => {
    if (transition(req.game, states.Paused)) return res.json({ state: req.game.state });
    return res.status(400).json({ error: `Invalid transition from ${req.game.state} to ${states.Paused}` });
  });

  app.post('/game/:id/resume', ensureGame, (req, res) => {
    if (transition(req.game, states.Playing)) return res.json({ state: req.game.state });
    return res.status(400).json({ error: `Invalid transition from ${req.game.state} to ${states.Playing}` });
  });

  app.post('/game/:id/gameover', ensureGame, (req, res) => {
    if (transition(req.game, states.GameOver)) return res.json({ state: req.game.state });
    return res.status(400).json({ error: `Invalid transition from ${req.game.state} to ${states.GameOver}` });
  });

  // Introspection for tests
  app.get('/_debug/games/:id', ensureGame, (req, res) => {
    res.json(req.game);
  });

  // Health
  app.get('/healthz', (req, res) => res.json({ ok: true }));

  // Expose for tests
  app._store = games;
  app._states = states;

  return app;
}

module.exports = { createApp };
