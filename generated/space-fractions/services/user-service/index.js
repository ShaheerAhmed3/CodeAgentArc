const express = require('express');
const { v4: uuidv4 } = require('uuid');

// Minimal user service with fake auth; OAuth2 deferred (source: Security Design)

async function startUserService(port) {
  const app = express();
  app.use(express.json());

  app.post('/api/login', (req, res) => {
    const { username } = req.body || {};
    if (!username || typeof username !== 'string') {
      return res.status(400).json({ error: 'username required' });
    }
    const isAdmin = username.toLowerCase() === 'admin';
    res.json({ userId: uuidv4(), username, isAdmin });
  });

  return new Promise((resolve) => {
    const server = app.listen(port, () => {
      console.log(`User service listening on ${server.address().port}`);
      resolve({ app, server });
    });
  });
}

module.exports = { startUserService };
