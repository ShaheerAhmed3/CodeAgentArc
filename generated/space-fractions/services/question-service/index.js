const express = require('express');

// Question store and format derived from ClassDiagram and SequenceDiagram
// Minimal in-memory persistence; implementation decision: provide default questions
let questions = [
  { id: 'q1', prompt: 'Which is greater: 1/2 or 2/3?', options: ['1/2', '2/3', 'equal', 'cannot tell'], answerIndex: 1 },
  { id: 'q2', prompt: 'Simplify: 4/8', options: ['1/4', '1/2', '2/3', '2/4'], answerIndex: 1 },
  { id: 'q3', prompt: 'Add: 1/3 + 1/6', options: ['1/2', '2/6', '1/9', '3/6'], answerIndex: 0 },
  { id: 'q4', prompt: 'Subtract: 3/4 - 1/2', options: ['1/4', '2/4', '1/2', '1/8'], answerIndex: 0 },
  { id: 'q5', prompt: 'Which is smaller: 5/8 or 3/4?', options: ['5/8', '3/4', 'equal', 'cannot tell'], answerIndex: 0 },
  { id: 'q6', prompt: 'Multiply: 2/3 * 3/4', options: ['6/12', '1/2', '6/7', '5/12'], answerIndex: 1 },
];

async function startQuestionService(port) {
  const app = express();
  app.use(express.json());

  // Get next by zero-based index
  app.get('/api/questions/next', (req, res) => {
    const idx = parseInt(req.query.index || '0', 10);
    const q = questions[idx % questions.length];
    res.json({ id: q.id, prompt: q.prompt, options: q.options });
  });

  app.post('/api/questions/check', (req, res) => {
    const { id, answer } = req.body || {};
    const q = questions.find((x) => x.id === id);
    if (!q) return res.status(404).json({ error: 'Question not found' });
    const ai = typeof answer === 'number' ? answer : parseInt(answer, 10);
    const correct = ai === q.answerIndex;
    res.json({ correct });
  });

  // Admin update
  app.post('/api/admin/questions', (req, res) => {
    const body = req.body;
    if (!body || !Array.isArray(body.questions)) {
      return res.status(400).json({ error: 'questions array required' });
    }
    // Basic validation
    const valid = body.questions.every((q) => q.id && q.prompt && Array.isArray(q.options) && typeof q.answerIndex === 'number');
    if (!valid) return res.status(400).json({ error: 'invalid question format' });
    questions = body.questions;
    res.json({ ok: true, count: questions.length });
  });

  return new Promise((resolve) => {
    const server = app.listen(port, () => {
      console.log(`Question service listening on ${server.address().port}`);
      resolve({ app, server });
    });
  });
}

module.exports = { startQuestionService };
