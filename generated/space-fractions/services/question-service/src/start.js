const { createApp } = require('./app');

const PORT = process.env.PORT || 3002;
const USER_BASE = process.env.USER_BASE || 'http://localhost:3003';

const app = createApp({ USER_BASE });
app.listen(PORT, () => {
  console.log(`question-service listening on ${PORT}, USER_BASE=${USER_BASE}`);
});
