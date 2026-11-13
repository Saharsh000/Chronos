/**
 * Chronoweb: Client-side Single Page Application & Real-Time Sync Engine
 * Built for Chronos Study Companion (chronos.fadehost.app)
 */

// Custom Pixel-Art Assets Dictionary
const ASSETS = {
  logo: '/assets/icons/chrono_clock_64.png',
  clock: '/assets/icons/chrono_clock_64.png',
  focus: '/assets/icons/focus_clock_64.png',
  pomodoro: '/assets/discord_emojis/pomodoro.png',

  coin: '/assets/discord_emojis/chronocoin.png',
  coins: '/assets/discord_emojis/chronocoin.png',
  candy: '/assets/discord_emojis/halloween_candy.png',
  xp: '/assets/discord_emojis/chronos_xp.png',
  streak: '/assets/discord_emojis/chronos_streak.png',

  physics: '/assets/discord_emojis/physics.png',
  chemistry: '/assets/discord_emojis/chemistry.png',
  maths: '/assets/discord_emojis/maths.png',
  general: '/assets/icons/compass_24.png',

  crown: '/assets/icons/rank_crown_32.png',
  rank1: '/assets/icons/rank_1_32.png',
  rank2: '/assets/icons/rank_2_32.png',
  rank3: '/assets/icons/rank_3_32.png',
  trophy: '/assets/discord_emojis/trophy.png',

  mystery_box: '/assets/discord_emojis/mystery_box.png',
  streak_freeze: '/assets/discord_emojis/streak_freeze.png',
  xp_boost: '/assets/discord_emojis/xp_boost.png',
  coin_boost: '/assets/discord_emojis/coin_boost.png',
  sugar_rush: '/assets/discord_emojis/sugar_rush.png',
  sugarrush: '/assets/discord_emojis/sugar_rush.png',
  title_scroll: '/assets/discord_emojis/title_scroll.png',
  chalice: '/assets/icons/chalice_64.png',

  tier_iron: '/assets/icons/tiers/iron.png',
  tier_bronze: '/assets/icons/tiers/bronze.png',
  tier_silver: '/assets/icons/tiers/silver.png',
  tier_gold: '/assets/icons/tiers/gold.png',
  tier_platinum: '/assets/icons/tiers/platinum.png',
  tier_diamond: '/assets/icons/tiers/diamond.png',
  tier_ascendant: '/assets/icons/tiers/ascendant.png',
  tier_immortal: '/assets/icons/tiers/immortal.png',
  tier_radiant: '/assets/icons/tiers/radiant.png',
  tier_air1: '/assets/icons/tiers/air_1.png',
  tier_air_1: '/assets/icons/tiers/air_1.png',
};

function getItemIcon(itemId) {
  if (!itemId) return ASSETS.mystery_box;
  const key = itemId.toLowerCase().replace(/[^a-z0-9_]/g, '_');
  if (ASSETS[key]) return ASSETS[key];
  if (key.startsWith('tag_')) return ASSETS.title_scroll;
  if (key.includes('boost')) return ASSETS.xp_boost;
  if (key.includes('box')) return ASSETS.mystery_box;
  if (key.includes('candy')) return ASSETS.candy;
  return '/assets/discord_emojis/mystery_box.png';
}

function getTierIcon(tierName) {
  if (!tierName) return ASSETS.tier_iron;
  const key = 'tier_' + tierName.toLowerCase().replace(/[^a-z0-9]/g, '');
  return ASSETS[key] || ASSETS.tier_iron;
}

// Application State
const state = {
  user: null,
  activeSession: null,
  timerInterval: null,
  heartbeatInterval: null,
  currentSubject: 'all',
  currentTab: 'focus',
  currentPeriod: 'today',
  audioCtx: null,
  ambientNode: null,
  isAmbientPlaying: false,
};

// ===================================================================== //
// 1. Initialization & Auth
// ===================================================================== //

document.addEventListener('DOMContentLoaded', async () => {
  initNav();
  initAmbientAudio();
  await checkAuth();
  
  // Periodically refresh active studiers and server session status
  setInterval(refreshLiveMetrics, 15000);
});

async function checkAuth() {
  try {
    const res = await fetch('/api/auth/me');
    const data = await res.json();
    
    if (data.authenticated && data.user) {
      state.user = data.user;
      renderUserUI(data.user);
      document.getElementById('login-modal').classList.remove('active');
      
      // Check if session is already running
      if (data.user.active_session) {
        resumeActiveSession(data.user.active_session);
      }
      
      loadTabContent(state.currentTab);
    } else {
      showLoginModal(data.oauth_configured);
      // Still load public tabs so the app is not an empty skeleton
      loadTabContent(state.currentTab);
    }
  } catch (err) {
    console.error('Failed to authenticate:', err);
    showLoginModal(false);
    loadTabContent(state.currentTab);
  }
}

function showLoginModal(oauthConfigured) {
  const modal = document.getElementById('login-modal');
  modal.classList.add('active');
  
  const oauthBtn = document.getElementById('discord-oauth-btn');
  const oauthHint = document.getElementById('oauth-hint');
  
  if (!oauthConfigured) {
    oauthHint.style.display = 'block';
  } else {
    oauthHint.style.display = 'none';
  }
}

async function devLogin(userId) {
  try {
    const res = await fetch('/api/auth/dev-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId }),
    });
    const data = await res.json();
    if (data.status === 'ok') {
      window.location.reload();
    } else {
      alert(data.error || 'Login failed');
    }
  } catch (err) {
    alert('Dev login error');
  }
}

async function logout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.reload();
  } catch (e) {
    window.location.reload();
  }
}

function renderUserUI(user) {
  document.getElementById('topbar-user-avatar').src = user.avatar || 'https://cdn.discordapp.com/embed/avatars/0.png';
  document.getElementById('topbar-user-name').textContent = user.global_name || user.username;
  document.getElementById('topbar-user-level').innerHTML = `<img src="${getTierIcon(user.stats.tier)}" class="pixel-icon-xs" alt="" style="margin-right:4px;" /> Lv. ${user.stats.level} • ${user.stats.tier}`;
  document.getElementById('coins-counter').textContent = user.wallet.coins.toLocaleString();
  document.getElementById('candy-counter').textContent = user.wallet.candy.toLocaleString();
}

// ===================================================================== //
// 2. Navigation & Views
// ===================================================================== //

function initNav() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const tab = item.getAttribute('data-tab');
      switchTab(tab);
    });
  });
}

function toggleMobileSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (sidebar) {
    sidebar.classList.toggle('mobile-open');
  }
}

function switchTab(tabId) {
  state.currentTab = tabId;
  const sidebar = document.getElementById('sidebar');
  if (sidebar && sidebar.classList.contains('mobile-open')) {
    sidebar.classList.remove('mobile-open');
  }

  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.getAttribute('data-tab') === tabId);
  });
  
  document.querySelectorAll('.view-section').forEach(view => {
    view.classList.toggle('active', view.id === `view-${tabId}`);
  });

  loadTabContent(tabId);
}

function loadTabContent(tabId) {
  switch (tabId) {
    case 'focus':
      loadFocusHub();
      break;
    case 'stats':
      loadStatsView();
      break;
    case 'leaderboard':
      loadLeaderboardView(state.currentPeriod);
      break;
    case 'syllabus':
      loadSyllabusView();
      break;
    case 'pets':
      loadPetsView();
      break;
    case 'economy':
      loadEconomyView();
      break;
    case 'halloween':
      loadHalloweenView();
      break;
    case 'notes':
      loadNotesView();
      break;
    case 'trivia':
      loadTriviaQuestion();
      break;
    case 'achievements':
      loadAchievementsView();
      break;
  }
}

// ===================================================================== //
// 3. Live Study Timer & Session Sync
// ===================================================================== //

function selectSubject(subjKey) {
  state.currentSubject = subjKey;
  document.querySelectorAll('.subject-chip').forEach(chip => {
    chip.classList.toggle('active', chip.getAttribute('data-subject') === subjKey);
  });
}

async function startStudySession() {
  const btn = document.getElementById('btn-session-toggle');
  btn.disabled = true;

  try {
    const res = await fetch('/api/sessions/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ subject: state.currentSubject === 'all' ? null : state.currentSubject }),
    });
    const data = await res.json();
    
    if (res.ok && data.status === 'ok') {
      state.activeSession = {
        session_id: data.session_id,
        start_time: data.start_time,
        subject: data.subject,
      };
      playFocusChime(523.25); // High C tone
      beginTimerTicker(data.start_time);
    } else {
      alert(data.error || 'Failed to start session');
    }
  } catch (err) {
    alert('Network error starting session');
  } finally {
    btn.disabled = false;
  }
}

async function stopStudySession() {
  const btn = document.getElementById('btn-session-toggle');
  btn.disabled = true;

  try {
    const res = await fetch('/api/sessions/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await res.json();

    if (res.ok && data.status === 'ok') {
      endTimerTicker();
      playLevelUpFanfare();
      triggerConfetti();
      showCelebrationModal(data.summary, data.wallet);
    } else {
      alert(data.error || 'Failed to stop session');
    }
  } catch (err) {
    alert('Network error stopping session');
  } finally {
    btn.disabled = false;
  }
}

function resumeActiveSession(session) {
  state.activeSession = session;
  if (session.subject) {
    selectSubject(session.subject);
  }
  beginTimerTicker(session.start_time);
}

function beginTimerTicker(startTime) {
  clearInterval(state.timerInterval);
  clearInterval(state.heartbeatInterval);

  const btn = document.getElementById('btn-session-toggle');
  btn.innerHTML = '<img src="/assets/icons/chrono_clock_64.png" class="pixel-icon-sm" alt="" style="margin-right:8px;" /> End Session';
  btn.className = 'btn btn-danger btn-timer';
  btn.onclick = stopStudySession;

  const pill = document.getElementById('active-session-pill');
  pill.classList.add('visible');

  function tick() {
    const now = Math.floor(Date.now() / 1000);
    const elapsed = Math.max(0, now - startTime);

    const hrs = String(Math.floor(elapsed / 3600)).padStart(2, '0');
    const mins = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
    const secs = String(elapsed % 60).padStart(2, '0');
    const formatted = `${hrs}:${mins}:${secs}`;

    document.getElementById('timer-digits').textContent = formatted;
    document.getElementById('live-pill-text').textContent = formatted;

    // Update dial progress stroke
    const dial = document.getElementById('timer-dial-progress');
    if (dial) {
      const circleCircumference = 816;
      const progress = (elapsed % 3600) / 3600;
      dial.style.strokeDashoffset = circleCircumference - (progress * circleCircumference);
    }

    // Estimate live rolls
    const minutesCompleted = Math.floor(elapsed / 60);
    document.getElementById('live-xp-roll').textContent = `+${minutesCompleted * 10}`;
    document.getElementById('live-coins-roll').textContent = `+${minutesCompleted * 2}`;
  }

  tick();
  state.timerInterval = setInterval(tick, 1000);

  // Send periodic heartbeat every 30s
  state.heartbeatInterval = setInterval(async () => {
    try {
      await fetch('/api/sessions/heartbeat', { method: 'POST' });
    } catch (e) {}
  }, 30000);
}

function endTimerTicker() {
  clearInterval(state.timerInterval);
  clearInterval(state.heartbeatInterval);
  state.activeSession = null;

  const btn = document.getElementById('btn-session-toggle');
  btn.innerHTML = '<img src="/assets/icons/focus_clock_64.png" class="pixel-icon-sm" alt="" style="margin-right:8px;" /> Start Focus Session';
  btn.className = 'btn btn-primary btn-timer';
  btn.onclick = startStudySession;

  document.getElementById('timer-digits').textContent = '00:00:00';
  document.getElementById('active-session-pill').classList.remove('visible');
  document.getElementById('live-xp-roll').textContent = '+0';
  document.getElementById('live-coins-roll').textContent = '+0';
}

function showCelebrationModal(summary, wallet) {
  const modal = document.getElementById('celebration-modal');
  modal.classList.add('active');

  document.getElementById('celeb-duration').textContent = summary.formatted_duration;
  document.getElementById('celeb-xp').textContent = `+${summary.xp_earned} XP`;
  document.getElementById('celeb-coins').textContent = `+${summary.coins_earned}`;
  document.getElementById('celeb-streak').textContent = `${summary.current_streak} days`;

  const cardImg = document.getElementById('celeb-card-img');
  if (summary.card_image) {
    cardImg.src = summary.card_image;
    cardImg.style.display = 'block';
  } else {
    cardImg.style.display = 'none';
  }

  // Update wallet pills
  if (wallet) {
    document.getElementById('coins-counter').textContent = wallet.coins.toLocaleString();
    document.getElementById('candy-counter').textContent = wallet.candy.toLocaleString();
  }
}

async function refreshLiveMetrics() {
  // Refresh active studiers
  try {
    const res = await fetch('/api/sessions/server-active');
    const data = await res.json();
    const container = document.getElementById('studiers-list');
    if (!container) return;

    if (!data.studiers || data.studiers.length === 0) {
      container.innerHTML = `<div style="text-align:center; padding:20px; color:var(--text-dim); font-size:13px;">No one is studying right now. Be the first to start!</div>`;
      return;
    }

    container.innerHTML = data.studiers.map(s => `
      <div class="studier-row">
        <img class="studier-avatar" src="${s.avatar}" alt="${s.name}" />
        <div class="studier-info">
          <div class="studier-name">${s.name}</div>
          <div class="studier-subject">
            ${s.subject_info ? '<img src="' + (ASSETS[s.subject_info.key] || '/assets/icons/compass_24.png') + '" class="pixel-icon-xs" alt="" style="margin-right:4px;" /> ' + s.subject_info.label : 'General Focus'}
          </div>
        </div>
        <div class="studier-time">${s.formatted_elapsed}</div>
      </div>
    `).join('');
  } catch (e) {}

  // Refresh Pomodoro state
  try {
    const res = await fetch('/api/pomodoro/status');
    const pomo = await res.json();
    const pomoTitle = document.getElementById('pomo-phase-label');
    const pomoTimer = document.getElementById('pomo-time-display');
    if (pomoTitle && pomoTimer) {
      if (pomo.active) {
        pomoTitle.innerHTML = `<img src="/assets/discord_emojis/pomodoro.png" class="pixel-icon-xs" alt="" style="margin-right:4px;" /> ${pomo.phase === 'focus' ? 'Focus Phase' : 'Break Phase'}`;
        const mins = String(Math.floor(pomo.remaining_seconds / 60)).padStart(2, '0');
        const secs = String(pomo.remaining_seconds % 60).padStart(2, '0');
        pomoTimer.textContent = `${mins}:${secs}`;
      } else {
        pomoTitle.textContent = 'Voice Pomodoro Standby';
        pomoTimer.textContent = '25:00';
      }
    }
  } catch (e) {}
}

async function loadFocusHub() {
  await refreshLiveMetrics();
}

// ===================================================================== //
// 4. Stats & Analytics View
// ===================================================================== //

async function loadStatsView() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();

    document.getElementById('stats-total-time').textContent = data.stats.formatted_total;
    document.getElementById('stats-streak').textContent = `${data.stats.current_streak} Days`;
    document.getElementById('stats-longest-streak').textContent = `${data.stats.longest_streak} Days`;
    document.getElementById('stats-sessions-count').textContent = data.stats.sessions_count;
    document.getElementById('stats-level-val').textContent = data.stats.level;
    document.getElementById('stats-tier-name').innerHTML = `<img src="${getTierIcon(data.stats.tier)}" class="pixel-icon-sm" alt="" style="margin-right:6px;" /> ${data.stats.tier}`;
    document.getElementById('stats-xp-progress').textContent = `${data.stats.cur_xp.toLocaleString()} / ${data.stats.next_xp.toLocaleString()} XP`;
    document.getElementById('stats-xp-fill').style.width = `${data.stats.xp_percentage}%`;

    // Render Subject Distribution
    const subjContainer = document.getElementById('subject-bars-container');
    if (subjContainer) {
      subjContainer.innerHTML = data.subjects.map(s => `
        <div style="margin-bottom: 14px;">
          <div style="display:flex; justify-content:space-between; font-size:13px; font-weight:600; margin-bottom:4px;">
            <span style="display:flex; align-items:center; gap:6px;">
              <img src="${ASSETS[s.key] || ASSETS[s.subject] || '/assets/icons/compass_24.png'}" class="pixel-icon-sm" alt="" /> ${s.label}
            </span>
            <span style="color:var(--text-muted);">${s.formatted} (${s.percentage}%)</span>
          </div>
          <div style="height:8px; border-radius:999px; background:rgba(255,255,255,0.06); overflow:hidden;">
            <div style="height:100%; border-radius:999px; width:${s.percentage}%; background:linear-gradient(90deg, var(--accent-purple), var(--accent-cyan));"></div>
          </div>
        </div>
      `).join('');
    }

    // Render Session Log Table
    const tableBody = document.getElementById('session-history-tbody');
    if (tableBody) {
      if (!data.recent_sessions || data.recent_sessions.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-dim);">No study sessions recorded yet.</td></tr>`;
      } else {
        tableBody.innerHTML = data.recent_sessions.map(s => `
          <tr>
            <td>
              <div style="display:flex; align-items:center; gap:6px;">
                <img src="${s.subject_info ? (ASSETS[s.subject_info.key] || '/assets/icons/compass_24.png') : '/assets/icons/compass_24.png'}" class="pixel-icon-xs" alt="" />
                <span>${s.subject_info ? s.subject_info.label : 'General'}</span>
              </div>
            </td>
            <td><strong>${s.formatted_duration}</strong></td>
            <td><span style="color:var(--accent-purple); font-weight:700;">+${s.xp_earned} XP</span></td>
            <td>${new Date(s.end_time * 1000).toLocaleDateString()} ${new Date(s.end_time * 1000).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</td>
            <td><span style="font-size:11px; padding:3px 8px; border-radius:999px; background:rgba(255,255,255,0.06);">${s.end_reason}</span></td>
          </tr>
        `).join('');
      }
    }
  } catch (err) {
    console.error('Failed to load stats:', err);
  }
}

// ===================================================================== //
// 5. Leaderboard View
// ===================================================================== //

async function loadLeaderboardView(period) {
  state.currentPeriod = period;
  document.querySelectorAll('.period-tab').forEach(tab => {
    tab.classList.toggle('active', tab.getAttribute('data-period') === period);
  });

  try {
    const res = await fetch(`/api/leaderboard?period=${period}`);
    const data = await res.json();

    // Render Podium
    const podiumEl = document.getElementById('leaderboard-podium');
    if (podiumEl) {
      const top3 = data.rankings.slice(0, 3);
      podiumEl.innerHTML = top3.map((u, idx) => `
        <div class="podium-card ${idx === 0 ? 'first' : ''}">
          <div class="podium-crown">${idx === 0 ? '👑' : idx === 1 ? '🥈' : '🥉'}</div>
          <img src="${u.avatar}" style="width:54px; height:54px; border-radius:50%; margin-bottom:8px; border:2px solid var(--accent-purple);" />
          <div style="font-weight:700; font-size:15px; color:#fff;">${u.name}</div>
          <div style="font-size:12px; color:var(--accent-cyan); font-weight:600;">Lv. ${u.level}</div>
          <div style="font-size:16px; font-weight:800; color:var(--accent-emerald); font-family:var(--font-mono); margin-top:6px;">${u.formatted_time}</div>
        </div>
      `).join('');
    }

    // Render Table
    const tbody = document.getElementById('leaderboard-tbody');
    if (tbody) {
      tbody.innerHTML = data.rankings.map(u => `
        <tr>
          <td><span style="font-weight:800; color:${u.rank <= 3 ? 'var(--accent-gold)' : 'var(--text-muted)'};">#${u.rank}</span></td>
          <td>
            <div style="display:flex; align-items:center; gap:10px;">
              <img src="${u.avatar}" style="width:28px; height:28px; border-radius:50%;" />
              <span style="font-weight:600;">${u.name}</span>
            </div>
          </td>
          <td><span style="font-weight:700; color:#fff;">Lv. ${u.level}</span></td>
          <td><span style="font-family:var(--font-mono); font-weight:700; color:var(--accent-emerald);">${u.formatted_time}</span></td>
          <td>🔥 ${u.streak}d</td>
        </tr>
      `).join('');
    }

    await loadHallOfFame();
  } catch (e) {
    console.error('Failed to load leaderboard:', e);
  }
}

async function loadHallOfFame() {
  try {
    const res = await fetch('/api/leaderboard/hall-of-fame');
    const data = await res.json();

    const sessList = document.getElementById('hof-sessions-list');
    if (sessList) {
      if (!data.longest_sessions || data.longest_sessions.length === 0) {
        sessList.innerHTML = '<span style="color:var(--text-dim); font-size:12px;">No records yet</span>';
      } else {
        sessList.innerHTML = data.longest_sessions.slice(0, 5).map((r, i) => `
          <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:12px; font-weight:800; color:var(--accent-gold);">#${i+1}</span>
              <img src="${r.avatar}" style="width:22px; height:22px; border-radius:50%;" />
              <span style="font-size:13px; font-weight:600;">${r.name}</span>
            </div>
            <span style="font-family:var(--font-mono); font-size:12px; font-weight:700; color:var(--accent-cyan);">${r.formatted_time || r.duration_seconds + 's'}</span>
          </div>
        `).join('');
      }
    }

    const streakList = document.getElementById('hof-streaks-list');
    if (streakList) {
      if (!data.top_streaks || data.top_streaks.length === 0) {
        streakList.innerHTML = '<span style="color:var(--text-dim); font-size:12px;">No records yet</span>';
      } else {
        streakList.innerHTML = data.top_streaks.slice(0, 5).map((r, i) => `
          <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:12px; font-weight:800; color:var(--accent-gold);">#${i+1}</span>
              <img src="${r.avatar}" style="width:22px; height:22px; border-radius:50%;" />
              <span style="font-size:13px; font-weight:600;">${r.name}</span>
            </div>
            <span style="font-size:12px; font-weight:700; color:var(--accent-rose);">🔥 ${r.streak || r.streak_days || 0}d</span>
          </div>
        `).join('');
      }
    }

    const levelList = document.getElementById('hof-levels-list');
    if (levelList) {
      if (!data.top_levels || data.top_levels.length === 0) {
        levelList.innerHTML = '<span style="color:var(--text-dim); font-size:12px;">No records yet</span>';
      } else {
        levelList.innerHTML = data.top_levels.slice(0, 5).map((r, i) => `
          <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-size:12px; font-weight:800; color:var(--accent-gold);">#${i+1}</span>
              <img src="${r.avatar}" style="width:22px; height:22px; border-radius:50%;" />
              <span style="font-size:13px; font-weight:600;">${r.name}</span>
            </div>
            <span style="font-size:12px; font-weight:700; color:var(--accent-gold);">Lv. ${r.level || 0}</span>
          </div>
        `).join('');
      }
    }
  } catch (e) {
    console.error('Failed to load hall of fame:', e);
  }
}

// ===================================================================== //
// 6. JEE Syllabus Tracker View
// ===================================================================== //

async function loadSyllabusView() {
  try {
    const res = await fetch('/api/syllabus');
    const data = await res.json();

    document.getElementById('syllabus-overall-pct').textContent = `${data.progress_percentage}%`;
    document.getElementById('syllabus-completed-count').textContent = `${data.completed_chapters} / ${data.total_chapters} Chapters Completed`;

    ['physics', 'chemistry', 'maths'].forEach(subj => {
      const list = data.subjects[subj] || [];
      const container = document.getElementById(`syllabus-grid-${subj}`);
      if (!container) return;

      container.innerHTML = list.map(ch => `
        <div class="chapter-card ${ch.done ? 'completed' : ''}">
          <div class="chapter-header" onclick="toggleChapterDone('${ch.name.replace(/'/g, "\\'")}')">
            <div class="chapter-title">
              <span style="font-size:18px;">${ch.done ? '✅' : '⭕'}</span>
              <span>${ch.name}</span>
            </div>
            <span style="font-size:12px; color:var(--text-dim);">${ch.topics.filter(t=>t.done).length}/${ch.topics.length} topics</span>
          </div>
          <div class="chapter-actions">
            <button class="btn btn-outline" style="font-size:11px; padding:4px 10px;" onclick="logRevision('${ch.name.replace(/'/g, "\\'")}')">🔁 Revision (${ch.revisions})</button>
            <button class="btn btn-outline" style="font-size:11px; padding:4px 10px;" onclick="logPyq('${ch.name.replace(/'/g, "\\'")}')">📝 PYQs (${ch.pyqs})</button>
          </div>
        </div>
      `).join('');
    });
  } catch (err) {
    console.error('Failed to load syllabus:', err);
  }
}

async function toggleChapterDone(chapterName) {
  try {
    await fetch('/api/syllabus/chapter/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chapter_name: chapterName }),
    });
    playFocusChime(659.25);
    loadSyllabusView();
  } catch (e) {}
}

async function logRevision(chapterName) {
  try {
    const res = await fetch('/api/syllabus/revision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_type: 'revision', chapter_name: chapterName }),
    });
    const data = await res.json();
    playFocusChime(783.99);
    alert(`Revision logged for ${chapterName}! +${data.xp_awarded} XP, +${data.coins_awarded} Coins`);
    loadSyllabusView();
  } catch (e) {}
}

async function logPyq(chapterName) {
  try {
    const res = await fetch('/api/syllabus/revision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_type: 'pyq', chapter_name: chapterName }),
    });
    const data = await res.json();
    playFocusChime(880.00);
    alert(`PYQ practice logged for ${chapterName}! +${data.xp_awarded} XP, +${data.coins_awarded} Coins`);
    loadSyllabusView();
  } catch (e) {}
}

// ===================================================================== //
// 7. Pets & Companions Menagerie
// ===================================================================== //

async function loadPetsView() {
  try {
    const res = await fetch('/api/pets');
    const data = await res.json();

    const equipped = data.equipped_pet;
    const hero = document.getElementById('equipped-pet-hero');
    if (hero) {
      if (equipped) {
        hero.innerHTML = `
          <div class="equipped-pet-display">
            <img class="pet-sprite-large" src="${equipped.sprite}" alt="${equipped.nickname}" />
            <div class="pet-name-title">${equipped.nickname}</div>
            <div class="pet-stage-pill">${equipped.stage_name} (${equipped.badge})</div>
            <div style="margin-top:14px; font-weight:700; color:var(--text-main);">Level ${equipped.level}</div>
            <div class="xp-progress-container" style="max-width:280px; margin:8px auto;">
              <div class="xp-progress-labels">
                <span>XP Progress</span>
                <span>${equipped.xp} / ${equipped.next_level_xp}</span>
              </div>
              <div class="xp-bar-bg">
                <div class="xp-bar-fill" style="width: ${equipped.progress_pct}%;"></div>
              </div>
            </div>
            <div style="display:flex; justify-content:center; gap:10px; margin-top:16px;">
              <button class="btn btn-primary" onclick="openFeedModal()">🍎 Feed Treat</button>
              <button class="btn btn-outline" onclick="renamePrompt('${equipped.species_id}')">✏️ Rename</button>
            </div>
          </div>
        `;
      } else {
        hero.innerHTML = `
          <div style="text-align:center; padding:40px; color:var(--text-dim);">
            <div style="font-size:48px; margin-bottom:10px;">🐾</div>
            <h3>No Companion Equipped</h3>
            <p style="font-size:13px; margin-top:6px;">Adopt a Pokemon companion below to accompany you while studying!</p>
          </div>
        `;
      }
    }

    // Render Owned Pets Menagerie
    const grid = document.getElementById('owned-pets-grid');
    if (grid) {
      if (!data.owned_pets || data.owned_pets.length === 0) {
        grid.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding:30px; color:var(--text-dim);">You have not adopted any companions yet. Reach study level 10 to unlock!</div>`;
      } else {
        grid.innerHTML = data.owned_pets.map(p => `
          <div class="pet-card">
            <img class="pet-card-sprite" src="${p.sprite}" alt="${p.nickname}" />
            <div style="font-weight:700; margin-top:6px;">${p.nickname}</div>
            <div style="font-size:12px; color:var(--text-dim);">Lv. ${p.level} • ${p.stage_name}</div>
            <div style="margin-top:10px;">
              ${p.equipped 
                ? '<span style="font-size:11px; color:var(--accent-emerald); font-weight:700;">ACTIVE COMPANION</span>' 
                : `<button class="btn btn-outline" style="font-size:12px; padding:4px 12px;" onclick="equipPet('${p.species_id}')">Equip</button>`
              }
            </div>
          </div>
        `).join('');
      }
    }

    // Load Pet Adoption Shop & Treats Shop
    loadPetShopCatalog();
    loadPetFoodShopCatalog();
  } catch (err) {
    console.error('Failed to load pets:', err);
  }
}

async function loadPetFoodShopCatalog() {
  try {
    const res = await fetch('/api/pets/food-catalog');
    const data = await res.json();
    const container = document.getElementById('pet-food-shop-catalog');
    if (!container) return;

    container.innerHTML = data.foods.map(f => `
      <div class="pet-card">
        ${f.sprite ? `<img src="${f.sprite}" style="width:40px; height:40px; margin:0 auto 6px; display:block; image-rendering:pixelated;" alt="${f.name}" />` : `<div style="font-size:36px; margin-bottom:6px;">${f.emoji}</div>`}
        <div style="font-weight:700; color:#fff;">${f.name}</div>
        <div style="font-size:11px; color:var(--accent-purple); font-weight:700; margin:4px 0;">+${f.xp_yield} Pet XP</div>
        <div style="font-size:11px; color:var(--text-dim); margin-bottom:10px;">${f.description || 'Nutritious companion food'}</div>
        <button class="btn btn-primary" style="font-size:12px; padding:6px 14px; width:100%;" onclick="buyPetFood('${f.id}')">🪙 Buy (${f.price})</button>
      </div>
    `).join('');
  } catch (e) {}
}

async function buyPetFood(foodId) {
  try {
    const res = await fetch('/api/pets/food-buy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ food_id: foodId, count: 1 }),
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      playFocusChime(659.25);
      alert(data.message || 'Treat purchased successfully!');
      const userRes = await fetch('/api/auth/me');
      const userData = await userRes.json();
      if (userData.user) renderUserUI(userData.user);
      loadPetsView();
    } else {
      alert(data.error || 'Failed to purchase treat');
    }
  } catch (e) {
    alert('Network error purchasing treat');
  }
}

async function loadPetShopCatalog() {
  try {
    const res = await fetch('/api/pets/catalog');
    const data = await res.json();
    const container = document.getElementById('pet-shop-catalog');
    if (!container) return;

    let html = '';
    for (const [tierKey, tierData] of Object.entries(data.catalog)) {
      html += `
        <div style="grid-column: 1/-1; margin-top:16px;">
          <h4 style="font-size:16px; color:#fff; display:flex; align-items:center; gap:8px;">
            ${tierData.emoji} ${tierData.label} Tier • <span style="color:var(--accent-gold); font-size:14px;">${tierData.base_price.toLocaleString()} Coins</span>
          </h4>
        </div>
      `;
      tierData.pets.forEach(p => {
        html += `
          <div class="pet-card">
            <img class="pet-card-sprite" src="${p.sprite}" alt="${p.name}" />
            <div style="font-weight:700; margin-top:6px;">${p.name}</div>
            <div style="font-size:12px; color:var(--text-dim); margin-bottom:8px;">${p.description}</div>
            <button class="btn btn-primary" style="font-size:12px; padding:6px 14px;" onclick="buyPet('${p.species_id}')">🪙 Adopt (${p.price})</button>
          </div>
        `;
      });
    }
    container.innerHTML = html;
  } catch (e) {}
}

async function buyPet(speciesId) {
  if (!confirm(`Adopt ${speciesId}?`)) return;
  try {
    const res = await fetch('/api/pets/buy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ species_id: speciesId }),
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      triggerConfetti();
      playLevelUpFanfare();
      alert(data.message);
      loadPetsView();
    } else {
      alert(data.error || 'Failed to adopt pet');
    }
  } catch (e) {}
}

async function equipPet(speciesId) {
  try {
    const res = await fetch('/api/pets/equip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ species_id: speciesId }),
    });
    const data = await res.json();
    if (res.ok) {
      loadPetsView();
    } else {
      alert(data.error || 'Failed to equip');
    }
  } catch (e) {}
}

async function renamePrompt(speciesId) {
  const newName = prompt('Enter new nickname for your pet:');
  if (!newName) return;
  try {
    const res = await fetch('/api/pets/rename', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ species_id: speciesId, nickname: newName }),
    });
    if (res.ok) {
      loadPetsView();
    }
  } catch (e) {}
}

async function openFeedModal() {
  const [foodRes, petRes] = await Promise.all([
    fetch('/api/pets/food-catalog'),
    fetch('/api/pets')
  ]);
  const foodData = await foodRes.json();
  const petData = await petRes.json();
  const inv = petData.food_inventory || {};

  const select = document.getElementById('feed-food-select');
  select.innerHTML = foodData.foods.map(f => `
    <option value="${f.id}">${f.emoji} ${f.name} (+${f.xp_yield} Pet XP) [Owned: ${inv[f.id] || 0}]</option>
  `).join('');
  document.getElementById('feed-modal').classList.add('active');
}

async function submitFeed() {
  const foodId = document.getElementById('feed-food-select').value;
  const count = parseInt(document.getElementById('feed-food-count').value) || 1;
  try {
    const res = await fetch('/api/pets/feed', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ food_id: foodId, count: count }),
    });
    const data = await res.json();
    document.getElementById('feed-modal').classList.remove('active');
    if (res.ok && data.status === 'ok') {
      playFocusChime(783.99);
      if (data.result.evolved) {
        triggerConfetti();
        playLevelUpFanfare();
        alert(`✨ EVOLUTION! Your companion evolved into ${data.result.new_stage.name}!`);
      } else {
        alert(`Fed companion! Gained +${data.result.xp_gained} Pet XP.`);
      }
      loadPetsView();
    } else {
      alert(data.error || 'Feeding failed. Do you have enough food in your satchel?');
    }
  } catch (e) {}
}

// ===================================================================== //
// 8. Economy, Shop & Mini-Games
// ===================================================================== //

async function loadEconomyView() {
  try {
    const res = await fetch('/api/economy/overview');
    const data = await res.json();

    document.getElementById('eco-coins-val').textContent = data.wallet.coins.toLocaleString();
    document.getElementById('eco-candy-val').textContent = data.wallet.candy.toLocaleString();
    document.getElementById('eco-lifetime-val').textContent = data.wallet.lifetime_earned.toLocaleString();

    // Satchel / Inventory
    const invGrid = document.getElementById('inventory-grid');
    if (invGrid) {
      const items = Object.entries(data.inventory);
      if (items.length === 0) {
        invGrid.innerHTML = `<div style="grid-column:1/-1; text-align:center; padding:20px; color:var(--text-dim);">Satchel is empty. Visit the shop below to buy boosts and mystery boxes!</div>`;
      } else {
        invGrid.innerHTML = items.map(([itemId, qty]) => `
          <div class="glass-card" style="padding:16px; display:flex; align-items:center; justify-content:space-between;">
            <div>
              <div style="font-weight:700;">${itemId.replace(/_/g, ' ').toUpperCase()}</div>
              <div style="font-size:12px; color:var(--text-dim);">Quantity: x${qty}</div>
            </div>
            <button class="btn btn-outline" style="font-size:12px; padding:4px 12px;" onclick="useItem('${itemId}')">Use</button>
          </div>
        `).join('');
      }
    }

    // Mini-game buttons
    const btnDaily = document.getElementById('btn-claim-daily');
    if (btnDaily) {
      if (data.cooldowns.daily.claimed_today) {
        btnDaily.disabled = true;
        btnDaily.textContent = '✅ Claimed Today';
      } else {
        btnDaily.disabled = false;
        btnDaily.textContent = '🎁 Claim Daily Streak';
      }
    }

    // Shop Catalog
    loadShopCatalog();
  } catch (err) {
    console.error('Failed to load economy:', err);
  }
}

async function loadShopCatalog() {
  try {
    const res = await fetch('/api/economy/shop');
    const data = await res.json();
    const container = document.getElementById('shop-items-grid');
    if (!container) return;

    container.innerHTML = data.shop_items.map(item => `
      <div class="glass-card" style="display:flex; flex-direction:column; justify-content:space-between;">
        <div>
          <div style="font-size:28px; margin-bottom:8px;">${item.emoji}</div>
          <div style="font-size:16px; font-weight:700; color:#fff;">${item.name}</div>
          <div style="font-size:12px; color:var(--text-dim); margin-top:4px;">${item.description}</div>
        </div>
        <div style="margin-top:16px; display:flex; align-items:center; justify-content:space-between;">
          <span style="font-weight:700; color:var(--accent-gold); font-size:15px;">🪙 ${item.price}</span>
          <button class="btn btn-primary" style="font-size:12px; padding:6px 14px;" onclick="buyShopItem('${item.id}')">Buy</button>
        </div>
      </div>
    `).join('');
  } catch (e) {}
}

async function buyShopItem(itemId) {
  try {
    const res = await fetch('/api/economy/buy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: itemId, qty: 1 }),
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      playFocusChime(659.25);
      alert(data.message);
      loadEconomyView();
    } else {
      alert(data.error || 'Purchase failed');
    }
  } catch (e) {}
}

async function useItem(itemId) {
  try {
    const res = await fetch('/api/economy/use', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: itemId }),
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      triggerConfetti();
      playLevelUpFanfare();
      if (data.type === 'mystery_box') {
        alert(`🎁 Mystery Box Opened! Result: ${JSON.stringify(data.reward)}`);
      } else {
        alert(`⚡ Boost activated!`);
      }
      loadEconomyView();
    } else {
      alert(data.error || 'Failed to use item');
    }
  } catch (e) {}
}

async function claimDaily() {
  try {
    const res = await fetch('/api/economy/daily', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      triggerConfetti();
      playLevelUpFanfare();
      alert(`🎉 Daily Claimed! +${data.daily.coins} Coins! Streak: ${data.daily.streak} days.`);
      loadEconomyView();
    } else {
      alert(data.error || 'Daily reward not ready');
    }
  } catch (e) {}
}

async function claimWork() {
  try {
    const res = await fetch('/api/economy/work', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      playFocusChime(659.25);
      alert(`💼 Work Task Complete!\nScenario: "${data.work.job}"\nEarned: +${data.work.coins} Coins, +${data.work.xp} XP`);
      loadEconomyView();
    } else {
      alert(data.error || 'Work is on cooldown.');
    }
  } catch (e) {}
}

async function claimBeg() {
  try {
    const res = await fetch('/api/economy/beg', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      playFocusChime(523.25);
      alert(`📜 ${data.beg.scenario}\nResult: +${data.beg.coins} Coins`);
      loadEconomyView();
    } else {
      alert(data.error || 'Beg is on cooldown.');
    }
  } catch (e) {}
}

async function claimWeekly() {
  try {
    const res = await fetch('/api/economy/weekly', { method: 'POST' });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      triggerConfetti();
      playLevelUpFanfare();
      alert(`💰 Weekly Jackpot Claimed! +${data.weekly.coins} Coins!`);
      loadEconomyView();
    } else {
      alert(data.error || 'Weekly reward is on cooldown.');
    }
  } catch (e) {}
}

// ===================================================================== //
// 9. Halloween Seasonal Hub
// ===================================================================== //

async function loadHalloweenView() {
  try {
    const res = await fetch('/api/halloween/status');
    const data = await res.json();

    const curLvl = data.pass.current_level;
    document.getElementById('pumpkin-pass-stage').textContent = `${curLvl.emoji} ${curLvl.stage_name} — Level ${curLvl.level}: ${curLvl.level_name}`;
    document.getElementById('pumpkin-pass-xp').textContent = `${data.pass.study_minutes} mins tracked`;

    // Render Hallo-Boxes
    const boxesGrid = document.getElementById('hallo-boxes-grid');
    if (boxesGrid) {
      boxesGrid.innerHTML = Object.values(data.boxes).map(b => `
        <div class="box-card" onclick="openHalloBox('${b.id}')">
          <div class="box-emoji">${b.emoji}</div>
          <div style="font-weight:700; color:#fff;">${b.name}</div>
          <div style="font-size:12px; color:var(--text-dim); margin-top:4px;">Owned: x${b.count}</div>
          <button class="btn btn-primary" style="margin-top:12px; font-size:12px; padding:4px 14px;" ${b.count <= 0 ? 'disabled' : ''}>Instant Open</button>
        </div>
      `).join('');
    }

    // Render Candy Shop
    const candyGrid = document.getElementById('candy-shop-grid');
    if (candyGrid) {
      candyGrid.innerHTML = data.candy_shop.map(item => `
        <div class="glass-card">
          <div style="font-size:28px;">${item.emoji}</div>
          <div style="font-weight:700; margin-top:6px;">${item.name}</div>
          <div style="font-size:12px; color:var(--text-dim);">${item.description}</div>
          <div style="margin-top:14px; display:flex; justify-content:space-between; align-items:center;">
            <span style="color:var(--accent-pumpkin); font-weight:700;">🍬 ${item.candy_price} Candy</span>
            <button class="btn btn-outline" style="font-size:12px; padding:4px 12px;" onclick="buyCandyItem('${item.id}')">Buy</button>
          </div>
        </div>
      `).join('');
    }
  } catch (err) {
    console.error('Failed to load halloween:', err);
  }
}

async function openHalloBox(boxId) {
  try {
    const res = await fetch('/api/halloween/open-box', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier: boxId }),
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      triggerConfetti();
      playLevelUpFanfare();
      const loot = data.loot;
      alert(`🎃 Box Opened!\n🍬 +${loot.candy} Candy\n🪙 +${loot.coins} Coins\n${loot.item ? '🎁 Item: ' + loot.item : ''}`);
      loadHalloweenView();
    } else {
      alert(data.error || 'Failed to open box');
    }
  } catch (e) {}
}

async function buyCandyItem(itemId) {
  try {
    const res = await fetch('/api/halloween/candy-buy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_id: itemId }),
    });
    const data = await res.json();
    if (res.ok && data.status === 'ok') {
      playFocusChime(659.25);
      alert(data.message);
      loadHalloweenView();
    } else {
      alert(data.error || 'Candy purchase failed');
    }
  } catch (e) {}
}

// ===================================================================== //
// 10. Chronotes Notebook
// ===================================================================== //

async function loadNotesView() {
  try {
    const res = await fetch('/api/notes');
    const data = await res.json();
    const container = document.getElementById('notes-grid');
    if (!container) return;

    if (!data.notes || data.notes.length === 0) {
      container.innerHTML = `<div style="grid-column:1/-1; text-align:center; padding:40px; color:var(--text-dim);">No notes found. Click '+ New Note' to create study reminders and formula sheets!</div>`;
      return;
    }

    container.innerHTML = data.notes.map(n => `
      <div class="glass-card" style="display:flex; flex-direction:column; justify-content:space-between;">
        <div>
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:11px; padding:2px 8px; border-radius:999px; background:rgba(139,92,246,0.2); color:var(--accent-purple); font-weight:700;">${n.subject}</span>
            <button onclick="deleteNote(${n.note_id})" style="background:none; border:none; color:var(--text-dim); cursor:pointer;">🗑️</button>
          </div>
          <h4 style="font-size:16px; font-weight:700; margin:10px 0 6px; color:#fff;">${n.title}</h4>
          <p style="font-size:13px; color:var(--text-muted); white-space:pre-wrap; max-height:160px; overflow-y:auto;">${n.content}</p>
        </div>
        <div style="font-size:11px; color:var(--text-dim); margin-top:14px;">Last updated ${n.updated_at ? (typeof n.updated_at === 'number' ? new Date(n.updated_at * 1000).toLocaleDateString() : new Date(n.updated_at).toLocaleDateString()) : 'Recently'}</div>
      </div>
    `).join('');
  } catch (err) {
    console.error('Failed to load notes:', err);
  }
}

function openCreateNoteModal() {
  document.getElementById('create-note-modal').classList.add('active');
}

async function submitCreateNote() {
  const title = document.getElementById('note-title-input').value;
  const subject = document.getElementById('note-subject-input').value;
  const content = document.getElementById('note-content-input').value;

  if (!title) {
    alert('Please provide a title');
    return;
  }

  try {
    const res = await fetch('/api/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, subject, content }),
    });
    if (res.ok) {
      document.getElementById('create-note-modal').classList.remove('active');
      document.getElementById('note-title-input').value = '';
      document.getElementById('note-content-input').value = '';
      loadNotesView();
    }
  } catch (e) {}
}

async function deleteNote(noteId) {
  if (!confirm('Delete this note?')) return;
  try {
    await fetch(`/api/notes/${noteId}`, { method: 'DELETE' });
    loadNotesView();
  } catch (e) {}
}

// ===================================================================== //
// 11. JEE Trivia & Practice Hub
// ===================================================================== //

let activeTriviaQuestion = null;

async function loadTriviaQuestion() {
  try {
    const container = document.getElementById('trivia-card-content');
    container.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-dim);">Loading JEE question...</div>`;

    const res = await fetch('/api/trivia/question');
    const data = await res.json();
    const q = data.question;
    activeTriviaQuestion = q;

    container.innerHTML = `
      <div style="font-size:12px; color:var(--accent-cyan); font-weight:700; text-transform:uppercase;">${q.subject} • ${q.chapter || 'JEE Practice'}</div>
      <div style="font-size:17px; font-weight:700; color:#fff; margin:14px 0 20px; line-height:1.5;">${q.question}</div>
      <div style="display:flex; flex-direction:column; gap:10px;">
        ${q.options.map((opt, idx) => `
          <button class="btn btn-outline" style="justify-content:flex-start; text-align:left; padding:12px 18px;" onclick="submitTriviaOption(${idx})">
            <strong>${String.fromCharCode(65 + idx)}.</strong>&nbsp; ${opt}
          </button>
        `).join('')}
      </div>
    `;
  } catch (e) {
    console.error('Failed to load trivia:', e);
  }
}

async function submitTriviaOption(selectedIndex) {
  if (!activeTriviaQuestion) return;
  try {
    const res = await fetch('/api/trivia/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question_id: activeTriviaQuestion.id,
        selected_index: selectedIndex,
        correct_index: activeTriviaQuestion.correct_index,
      }),
    });
    const data = await res.json();
    
    if (data.is_correct) {
      triggerConfetti();
      playLevelUpFanfare();
    } else {
      playFocusChime(300);
    }

    const container = document.getElementById('trivia-card-content');
    container.innerHTML = `
      <div style="text-align:center; padding:20px;">
        <div style="font-size:48px; margin-bottom:10px;">${data.is_correct ? '🎯' : '❌'}</div>
        <h3 style="font-size:22px; color:#fff;">${data.is_correct ? 'Correct! (+4 Marks)' : 'Incorrect (-1 Mark)'}</h3>
        <p style="color:var(--text-muted); margin-top:8px;">${data.explanation || activeTriviaQuestion.explanation || 'Practice makes perfect!'}</p>
        <div style="display:flex; justify-content:center; gap:14px; margin-top:20px;">
          <span style="color:var(--accent-gold); font-weight:700;">+${data.coins_awarded} Coins</span>
          <span style="color:var(--accent-purple); font-weight:700;">+${data.xp_awarded} XP</span>
        </div>
        <button class="btn btn-primary" style="margin-top:24px;" onclick="loadTriviaQuestion()">Next Question ➔</button>
      </div>
    `;
  } catch (e) {}
}

// ===================================================================== //
// 12. Achievements & Badges View
// ===================================================================== //

let achievementsData = null;
let currentAchCategory = 'ALL';

async function loadAchievementsView() {
  try {
    const res = await fetch('/api/achievements');
    achievementsData = await res.json();

    const pctEl = document.getElementById('achievements-pct');
    const barEl = document.getElementById('achievements-progress-bar');
    const countEl = document.getElementById('achievements-count-label');
    const summaryEl = document.getElementById('achievements-summary-text');

    if (pctEl) pctEl.textContent = `${achievementsData.completion_percentage}%`;
    if (barEl) barEl.style.width = `${achievementsData.completion_percentage}%`;
    if (countEl) countEl.textContent = `${achievementsData.unlocked_count} / ${achievementsData.total_count} Unlocked`;
    if (summaryEl) summaryEl.textContent = `You have completed ${achievementsData.unlocked_count} out of ${achievementsData.total_count} achievements across all study domains.`;

    // Render Category Filter Tabs
    const tabsContainer = document.getElementById('achievements-cat-tabs');
    if (tabsContainer) {
      const cats = ['ALL', ...Object.keys(achievementsData.categories)];
      tabsContainer.innerHTML = cats.map(cat => `
        <button class="cat-tab-pill ${currentAchCategory === cat ? 'active' : ''}" onclick="filterAchievementCategory('${cat}')">
          ${cat}
        </button>
      `).join('');
    }

    renderAchievementsList();
  } catch (e) {
    console.error('Failed to load achievements:', e);
  }
}

function filterAchievementCategory(cat) {
  currentAchCategory = cat;
  document.querySelectorAll('.cat-tab-pill').forEach(btn => {
    btn.classList.toggle('active', btn.textContent.trim() === cat);
  });
  renderAchievementsList();
}

function renderAchievementsList() {
  const container = document.getElementById('achievements-grid');
  if (!container || !achievementsData) return;

  let list = [];
  if (currentAchCategory === 'ALL') {
    for (const [catName, achs] of Object.entries(achievementsData.categories)) {
      list.push(...achs);
    }
  } else {
    list = achievementsData.categories[currentAchCategory] || [];
  }

  // Sort unlocked first, then by name
  list.sort((a, b) => (b.unlocked ? 1 : 0) - (a.unlocked ? 1 : 0));

  container.innerHTML = list.map(a => `
    <div class="achievement-card ${a.unlocked ? 'unlocked' : 'locked'}">
      <div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <span style="font-size:28px;">${a.emoji || '🏅'}</span>
          ${a.unlocked 
            ? '<span style="font-size:11px; padding:3px 8px; border-radius:999px; background:rgba(16,185,129,0.2); color:var(--accent-emerald); font-weight:700;">✓ UNLOCKED</span>' 
            : '<span style="font-size:11px; padding:3px 8px; border-radius:999px; background:rgba(255,255,255,0.06); color:var(--text-dim); font-weight:600;">🔒 LOCKED</span>'
          }
        </div>
        <div style="font-weight:700; font-size:15px; color:#fff; margin-bottom:4px;">${a.name}</div>
        <div style="font-size:12px; color:var(--text-muted); line-height:1.4;">${a.description}</div>
      </div>
      <div style="margin-top:14px; padding-top:10px; border-top:1px solid rgba(255,255,255,0.06); display:flex; justify-content:space-between; align-items:center;">
        <span style="font-size:12px; font-weight:700; color:var(--accent-gold);">🪙 +${a.reward_coins} Coins</span>
        ${a.unlocked && a.unlocked_at ? `<span style="font-size:10px; color:var(--text-dim);">${new Date(a.unlocked_at * 1000).toLocaleDateString()}</span>` : ''}
      </div>
    </div>
  `).join('');
}

// ===================================================================== //
// 13. Audio Synthesizer (Chimes, Fanfares & Ambient Noise)
// ===================================================================== //

function initAmbientAudio() {
  const btn = document.getElementById('audio-toggle-btn');
  if (btn) {
    btn.onclick = toggleAmbientAudio;
  }
}

function getAudioContext() {
  if (!state.audioCtx) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    state.audioCtx = new AudioContext();
  }
  if (state.audioCtx.state === 'suspended') {
    state.audioCtx.resume();
  }
  return state.audioCtx;
}

function playFocusChime(freq = 523.25) {
  try {
    const ctx = getAudioContext();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = 'sine';
    osc.frequency.setValueAtTime(freq, ctx.currentTime);

    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 1.2);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + 1.2);
  } catch (e) {}
}

function playLevelUpFanfare() {
  try {
    const ctx = getAudioContext();
    const notes = [523.25, 659.25, 783.99, 1046.50]; // C5, E5, G5, C6
    notes.forEach((freq, idx) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(freq, ctx.currentTime + (idx * 0.12));
      gain.gain.setValueAtTime(0.25, ctx.currentTime + (idx * 0.12));
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + (idx * 0.12) + 0.4);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(ctx.currentTime + (idx * 0.12));
      osc.stop(ctx.currentTime + (idx * 0.12) + 0.45);
    });
  } catch (e) {}
}

function toggleAmbientAudio() {
  const btn = document.getElementById('audio-toggle-btn');
  if (state.isAmbientPlaying) {
    stopAmbientAudio();
    btn.classList.remove('playing');
    btn.innerHTML = '🎧 Ambient: Off';
  } else {
    startRainNoise();
    btn.classList.add('playing');
    btn.innerHTML = '🌧️ Rain Ambient';
  }
}

function startRainNoise() {
  try {
    const ctx = getAudioContext();
    const bufferSize = ctx.sampleRate * 2;
    const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
    const output = noiseBuffer.getChannelData(0);
    let b0 = 0, b1 = 0, b2 = 0;
    for (let i = 0; i < bufferSize; i++) {
      const white = Math.random() * 2 - 1;
      b0 = 0.99886 * b0 + white * 0.0555179;
      b1 = 0.99332 * b1 + white * 0.0750759;
      b2 = 0.96900 * b2 + white * 0.1538520;
      output[i] = (b0 + b1 + b2) * 0.04;
    }

    const whiteNoise = ctx.createBufferSource();
    whiteNoise.buffer = noiseBuffer;
    whiteNoise.loop = true;

    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.setValueAtTime(1000, ctx.currentTime);

    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.15, ctx.currentTime);

    whiteNoise.connect(filter);
    filter.connect(gain);
    gain.connect(ctx.destination);

    whiteNoise.start();
    state.ambientNode = { source: whiteNoise, gain: gain };
    state.isAmbientPlaying = true;
  } catch (e) {}
}

function stopAmbientAudio() {
  if (state.ambientNode) {
    state.ambientNode.source.stop();
    state.ambientNode = null;
  }
  state.isAmbientPlaying = false;
}

function triggerConfetti() {
  if (window.confetti) {
    window.confetti({
      particleCount: 80,
      spread: 70,
      origin: { y: 0.6 },
      colors: ['#8b5cf6', '#06b6d4', '#f59e0b', '#10b981'],
    });
  }
}

function closeModal(id) {
  document.getElementById(id).classList.remove('active');
}
