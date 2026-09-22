// Question Service - Express app
// Provides: GET /question, POST /check, POST /questions (admin-only)
// Uses user-service /validate to authorize admin actions.

const express = require('express');
const { v4: uuidv4 } = require('uuid');

function createApp(config = {}) {
  const app = express();
  app.use(express.json());

  const USER_BASE = config.USER_BASE || process.env.USER_BASE || 'http://localhost:3003';

  // In-memory question bank: { id, prompt, options, answerIndex }
  const questions = new Map();

  // Seed a default question
  const q1 = { id: uuidv4(), prompt: '1/2 + 1/4 = ?', options: ['1/4', '3/4', '2/3'], answerIndex: 1 };
  questions.set(q1.id, q1);

  // Helper to strip answers
  function publicQuestion(q) {
    return { id: q.id, prompt: q.prompt, options: q.options };
  }

  // Pick a pseudo-random question
  function pickQuestion() {
    const arr = Array.from(questions.values());
    return arr[Math.floor(Math.random() * arr.length)];
  }

  app.get('/question', (req, res) => {
    const q = pickQuestion();
    res.json(publicQuestion(q));
  });

  app.post('/check', (req, res) => {
    const { questionId, answerIndex } = req.body || {};
    if (!questionId || typeof answerIndex !== 'number') {
      return res.status(400).json({ error: 'questionId and answerIndex are required' });
    }
    const q = questions.get(questionId);
    if (!q) return res.status(404).json({ error: 'Question not found' });
    const correct = q.answerIndex === answerIndex;
    res.json({ correct });
  });

  // Admin-only: add or update a question
  app.post('/questions', async (req, res) => {
    const auth = req.headers['authorization'] || '';
    try {
      const r = await fetch(`${USER_BASE}/validate`, { headers: { 'Authorization': auth } });
      // Validation endpoint always returns 200 with {valid,role} in this demo
      const info = await r.json();
      if (!info.valid) return res.status(401).json({ error: 'Unauthorized' });
      if (info.role !== 'admin') return res.status(403).json({ error: 'Forbidden' });
    } catch (e) {
      return res.status(502).json({ error: e.message });
    }

    const { id, prompt, options, answerIndex } = req.body || {};
    if (!prompt || !Array.isArray(options) || typeof answerIndex !== 'number') {
      return res.status(400).json({ error: 'prompt, options[], answerIndex are required' });
    }
    const qid = id || uuidv4();
    questions.set(qid, { id: qid, prompt, options, answerIndex });
    res.status(201).json(publicQuestion(questions.get(qid)));
  });

  // Health
  app.get('/healthz', (req, res) => res.json({ ok: true }));

  // Expose for tests
  app._store = questions;

  return app;
}

module.exports = { createApp };
