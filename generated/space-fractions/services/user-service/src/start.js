const { createApp } = require('./app');

const PORT = process.env.PORT || 3003;
const app = createApp();
app.listen(PORT, () => {
  console.log(`user-service listening on ${PORT}`);
});
