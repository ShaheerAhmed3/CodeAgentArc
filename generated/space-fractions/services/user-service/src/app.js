// User Service - Express app
// Minimal token issuance and validation to stand in for OAuth2 flows in local runs

const express = require('express');

function createApp(config = {}) {
  const app = express();
  app.use(express.json());

  // Issue a trivial token for a requested role
  app.post('/token', (req, res) => {
    const { role } = req.body || {};
    if (!role || !['user', 'admin'].includes(role)) {
      return res.status(400).json({ error: 'role must be user|admin' });
    }
    const token = `${role}`; // intentionally simple; do NOT use in production
    res.json({ token, role });
  });

  // Validate Authorization: Bearer <token>
  app.get('/validate', (req, res) => {
    const auth = req.headers['authorization'] || '';
    const m = auth.match(/^Bearer\s+(.*)$/i);
    if (!m) return res.json({ valid: false });
    const token = m[1];
    if (token === 'admin') return res.json({ valid: true, role: 'admin' });
    if (token === 'user') return res.json({ valid: true, role: 'user' });
    return res.json({ valid: false });
  });

  // Health
  app.get('/healthz', (req, res) => res.json({ ok: true }));

  return app;
}

module.exports = { createApp };
