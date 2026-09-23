/**
 * jsdom-based UI logic tests: ensure app.js uses real service endpoints
 */
const fs = require('fs');
const path = require('path');
const request = require('supertest');
const { startGameService } = require('../../services/game-service');
const { startQuestionService } = require('../../services/question-service');
const { startUserService } = require('../../services/user-service');

const { JSDOM } = require('jsdom');

async function waitFor(condition, timeoutMs = 2000) {
  const deadline = Date.now() + timeoutMs;
  while (!condition()) {
    if (Date.now() >= deadline) throw new Error('Timed out waiting for UI state');
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
}

let gamePort = 0;
let questionPort = 0;
let userPort = 0;

let servers = {};
let baseUrl;
beforeAll(async () => {
  servers.q = await startQuestionService(questionPort);
  const qPort = servers.q.server.address().port;
  servers.u = await startUserService(userPort);
  const uPort = servers.u.server.address().port;
  servers.g = await startGameService({ port: gamePort, questionUrl: `http://localhost:${qPort}`, userUrl: `http://localhost:${uPort}` });
  const gPort = servers.g.server.address().port;
  baseUrl = `http://localhost:${gPort}`;
});

afterAll(async () => {
  await new Promise((r) => servers.g.server.close(r));
  await new Promise((r) => servers.q.server.close(r));
  await new Promise((r) => servers.u.server.close(r));
});

describe('Frontend screens and flows', () => {
  test('Intro → Menu → Play Game renders prompt and options from backend', async () => {
    // Load index.html
    const html = fs.readFileSync(path.join(__dirname, '../../frontend/public/index.html'), 'utf8');
    const dom = new JSDOM(html, {
      url: `${baseUrl}/`,
      runScripts: 'dangerously',
      resources: 'usable',
      pretendToBeVisual: true,
      beforeParse(window) {
        window.HTMLCanvasElement.prototype.getContext = () => null;
      },
    });

    // polyfill fetch for jsdom using Node's global fetch, resolving relative URLs against baseUrl
    dom.window.fetch = (url, opts) => {
      const absolute = new URL(url, baseUrl).toString();
      return global.fetch(absolute, opts);
    };

    // inject app.js as script content
    const scriptContent = fs.readFileSync(path.join(__dirname, '../../frontend/public/app.js'), 'utf8');
    const scriptEl = dom.window.document.createElement('script');
    scriptEl.textContent = scriptContent;
    dom.window.document.body.appendChild(scriptEl);

    // Wait for script to run
    await new Promise((r) => setTimeout(r, 200));

    // Jump to menu and start game
    dom.window.document.getElementById('skipIntroBtn').click();
    dom.window.document.getElementById('playBtn').click();

    // Allow network round-trips
    await new Promise((r) => setTimeout(r, 200));

    const prompt = dom.window.document.getElementById('prompt').textContent;
    expect(prompt.length).toBeGreaterThan(0);
    const options = dom.window.document.getElementById('options').children;
    expect(options.length).toBeGreaterThan(0);

    // The second option is correct for the first seeded question.
    options[1].click();
    await waitFor(() => dom.window.document.getElementById('qnum').textContent === '2');
    expect(dom.window.document.getElementById('score').textContent).toBe('1');
  });
});
