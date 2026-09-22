const { createApp } = require('./app');

const PORT = process.env.PORT || 3001;
const QUESTION_BASE = process.env.QUESTION_BASE || 'http://localhost:3002';

const app = createApp({ QUESTION_BASE });
app.listen(PORT, () => {
  console.log(`game-service listening on ${PORT}, QUESTION_BASE=${QUESTION_BASE}`);
});
