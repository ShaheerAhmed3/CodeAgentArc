(() => {
  const scenes = {
    intro: document.getElementById('intro'),
    menu: document.getElementById('mainMenu'),
    game: document.getElementById('game'),
    score: document.getElementById('scoreScene'),
    help: document.getElementById('helpSection'),
    admin: document.getElementById('admin'),
  };
  const els = {
    menuBtn: document.getElementById('menuBtn'),
    helpBtn: document.getElementById('helpBtn'),
    skipIntroBtn: document.getElementById('skipIntroBtn'),
    startBtn: document.getElementById('startBtn'),
    playBtn: document.getElementById('playBtn'),
    viewScoreBtn: document.getElementById('viewScoreBtn'),
    viewHelpBtn: document.getElementById('viewHelpBtn'),
    pauseBtn: document.getElementById('pauseBtn'),
    resumeBtn: document.getElementById('resumeBtn'),
    prompt: document.getElementById('prompt'),
    options: document.getElementById('options'),
    feedback: document.getElementById('feedback'),
    score: document.getElementById('score'),
    qnum: document.getElementById('qnum'),
    qtotal: document.getElementById('qtotal'),
    state: document.getElementById('state'),
    scoreText: document.getElementById('scoreText'),
    playAgainBtn: document.getElementById('playAgainBtn'),
    helpContent: document.getElementById('helpContent'),
    usernameInput: document.getElementById('usernameInput'),
    loginBtn: document.getElementById('loginBtn'),
    userStatus: document.getElementById('userStatus'),
    questionsJson: document.getElementById('questionsJson'),
    submitQuestionsBtn: document.getElementById('submitQuestionsBtn'),
    adminStatus: document.getElementById('adminStatus'),
  };

  let gameId = null;
  let gameTotal = 5;

  function show(scene) {
    Object.values(scenes).forEach(s => s.classList.add('hidden'));
    scenes[scene].classList.remove('hidden');
    document.getElementById('app').focus();
  }

  async function login(username) {
    const r = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username }) });
    const data = await r.json();
    els.userStatus.textContent = `Signed in as ${data.username}${data.isAdmin ? ' (admin)' : ''}`;
    if (data.isAdmin) {
      scenes.admin.classList.remove('hidden');
    } else {
      scenes.admin.classList.add('hidden');
    }
  }

  async function startGame() {
    const r = await fetch('/api/play');
    const data = await r.json();
    gameId = data.gameId;
    await nextQuestion();
    show('game');
  }

  async function updateState() {
    const r = await fetch(`/api/game/${gameId}/state`);
    const data = await r.json();
    els.state.textContent = data.state;
    els.score.textContent = data.score;
    els.qnum.textContent = String(Math.min(data.asked + 1, data.totalQuestions));
    els.qtotal.textContent = String(data.totalQuestions);
    gameTotal = data.totalQuestions;
  }

  async function nextQuestion() {
    const r = await fetch(`/api/game/${gameId}/next-question`);
    const data = await r.json();
    if (data.done) {
      endGame();
      return;
    }
    els.prompt.textContent = data.prompt;
    els.options.innerHTML = '';
    data.options.forEach((opt, idx) => {
      const li = document.createElement('li');
      li.tabIndex = 0;
      li.setAttribute('role', 'option');
      li.textContent = `${idx + 1}. ${opt}`;
      li.addEventListener('click', () => submitAnswer(data.questionId, idx));
      li.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); submitAnswer(data.questionId, idx); } });
      els.options.appendChild(li);
    });
    await updateState();
  }

  async function submitAnswer(questionId, answerIndex) {
    els.feedback.textContent = 'Checking...';
    const r = await fetch(`/api/game/${gameId}/answer`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ questionId, answer: answerIndex }) });
    const data = await r.json();
    if (data.state === 'GameOver') {
      endGame();
      return;
    }
    els.feedback.textContent = data.correct ? 'Correct!' : 'Incorrect';
    await nextQuestion();
  }

  async function pauseResume() {
    const state = els.state.textContent;
    if (state === 'Playing') {
      await fetch(`/api/game/${gameId}/pause`, { method: 'POST' });
      els.pauseBtn.classList.add('hidden');
      els.resumeBtn.classList.remove('hidden');
    } else if (state === 'Paused') {
      await fetch(`/api/game/${gameId}/resume`, { method: 'POST' });
      els.pauseBtn.classList.remove('hidden');
      els.resumeBtn.classList.add('hidden');
    }
    await updateState();
  }

  async function endGame() {
    if (gameId) await updateState();
    const r = await fetch('/api/score/current');
    const data = await r.json();
    if (data.hasGame) {
      els.scoreText.textContent = `Final score: ${data.score} / ${gameTotal}`;
    } else {
      els.scoreText.textContent = 'No game score available.';
    }
    show('score');
  }

  async function loadHelp() {
    const r = await fetch('/api/help');
    const data = await r.json();
    els.helpContent.innerHTML = `<h3>${data.title}</h3><ol>${data.steps.map(s => `<li>${s}</li>`).join('')}</ol>`;
  }

  // Intro animation (simple canvas spaceship)
  function startIntroAnimation() {
    const canvas = document.getElementById('introCanvas');
    if (!canvas || typeof canvas.getContext !== 'function') return; // environment (e.g., jsdom) may not support canvas
    let ctx;
    try {
      ctx = canvas.getContext('2d');
    } catch (e) {
      return; // silently skip animation if context is not available
    }
    if (!ctx) return;
    let x = -50; const y = canvas.height / 2; let frame = 0;
    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      // stars
      for (let i = 0; i < 60; i++) {
        ctx.fillStyle = '#88bcef';
        const sx = (i * 60 + frame * 2) % canvas.width;
        const sy = (i * 37) % canvas.height;
        ctx.fillRect(sx, sy, 2, 2);
      }
      // ship
      ctx.fillStyle = '#ffd54f';
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x - 30, y - 10);
      ctx.lineTo(x - 30, y + 10);
      ctx.closePath();
      ctx.fill();
      // title
      ctx.fillStyle = '#e6eef8';
      ctx.font = '24px sans-serif';
      ctx.fillText('Space Fractions', canvas.width / 2 - 100, 40);
      x += 2; frame++;
      if (x < canvas.width + 50) requestAnimationFrame(draw);
    }
    draw();
  }

  // Keyboard controls
  document.addEventListener('keydown', (e) => {
    if (scenes.game.classList.contains('hidden')) return;
    if (e.key.toLowerCase() === 'p') {
      pauseResume();
    }
    if (['1','2','3','4'].includes(e.key)) {
      const idx = parseInt(e.key, 10) - 1;
      const li = els.options.children[idx];
      if (li) li.click();
    }
  });

  // Wire up UI
  els.menuBtn.addEventListener('click', () => show('menu'));
  els.helpBtn.addEventListener('click', async () => { await loadHelp(); show('help'); });
  els.skipIntroBtn.addEventListener('click', () => show('menu'));
  els.startBtn.addEventListener('click', () => show('menu'));
  els.playBtn.addEventListener('click', () => startGame());
  els.viewScoreBtn.addEventListener('click', async () => { await endGame(); });
  els.viewHelpBtn.addEventListener('click', async () => { await loadHelp(); show('help'); });
  els.pauseBtn.addEventListener('click', pauseResume);
  els.resumeBtn.addEventListener('click', pauseResume);
  els.playAgainBtn.addEventListener('click', () => startGame());
  els.loginBtn.addEventListener('click', async () => { const u = els.usernameInput.value.trim(); if (u) await login(u); });
  els.submitQuestionsBtn.addEventListener('click', async () => {
    try {
      const questions = JSON.parse(els.questionsJson.value || '[]');
      const r = await fetch('/api/admin/questions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ questions }) });
      const data = await r.json();
      if (data.ok) { els.adminStatus.textContent = `Updated ${data.count} questions.`; }
      else { els.adminStatus.textContent = data.error || 'Failed.'; }
    } catch (e) {
      els.adminStatus.textContent = 'Invalid JSON';
    }
  });

  // Initialize
  startIntroAnimation();
  show('intro');
})();
