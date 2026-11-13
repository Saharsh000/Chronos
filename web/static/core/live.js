// Realtime: Server-Sent Events from /api/events + browser alerts. Works the same whether the
// action happened on the website or in Discord - the server publishes both to the same hub.
import { state, emit, get, h, ico, num, dur, nowSec } from '/static/core/core.js';
import { toast, celebrate } from '/static/core/ui.js';

let es = null, lastId = 0, titleTimer = null;
const baseTitle = 'Chronos';

export async function refreshSession() {
  try { state.session = await get('/api/session'); emit('session', state.session); } catch { /* offline */ }
  return state.session;
}
export async function refreshMe() {
  try { const m = await get('/api/me'); if (m.authed) { state.me = m; document.documentElement.dataset.tier = m.level?.tier_key || ''; emit('me', m); } } catch { /* ignore */ }
}

// ---- browser alerts (only when the tab is hidden, only if the user enabled them)
export const alertsOn = () => { try { return 'Notification' in window && Notification.permission === 'granted' && localStorage.getItem('chronos-alerts') !== '0'; } catch { return false; } };
export async function enableAlerts() {
  if (!('Notification' in window)) return false;
  const p = Notification.permission === 'granted' ? 'granted' : await Notification.requestPermission();
  try { localStorage.setItem('chronos-alerts', p === 'granted' ? '1' : '0'); } catch { /* private mode */ }
  return p === 'granted';
}
export function disableAlerts() { try { localStorage.setItem('chronos-alerts', '0'); } catch { /* ignore */ } }
export function notify(title, body, tag) {
  if (document.hidden && alertsOn()) {
    try { const n = new Notification(title, { body, tag, icon: '/assets/icons/chrono_clock_128.png' }); n.onclick = () => { window.focus(); n.close(); }; } catch { /* ignore */ }
  }
}
function beep() {
  try {
    const a = new (window.AudioContext || window.webkitAudioContext)(); const o = a.createOscillator(); const g = a.createGain();
    o.type = 'sine'; o.frequency.value = 880; g.gain.setValueAtTime(.001, a.currentTime); g.gain.exponentialRampToValueAtTime(.18, a.currentTime + .02); g.gain.exponentialRampToValueAtTime(.001, a.currentTime + .5);
    o.connect(g).connect(a.destination); o.start(); o.stop(a.currentTime + .55);
  } catch { /* autoplay blocked */ }
}
function blinkTitle(on) {
  clearInterval(titleTimer); document.title = baseTitle;
  if (!on) return;
  let t = false; titleTimer = setInterval(() => { document.title = (t = !t) ? '⏰ Still studying?' : baseTitle; }, 900);
}

const BOX_NAMES = { common: 'Common', uncommon: 'Uncommon', rare: 'Rare', epic: 'Epic', legendary: 'Legendary' };

const handlers = {
  afk_prompt() { refreshSession(); blinkTitle(true); beep(); notify('Still studying?', 'Confirm you\'re here or your session will end.', 'afk'); },
  afk_confirmed() { blinkTitle(false); refreshSession(); },
  session_started(d) { refreshSession(); if (d.source === 'discord') toast('Started from Discord - your timer is running here too.', { title: 'Session started', icon: 'chrono_clock', kind: 'good' }); },
  session_ended(d) {
    blinkTitle(false); refreshSession(); refreshMe();
    if (d.source === 'web') return;   // the Home page already shows its own summary
    const afk = d.reason === 'afk_timeout';
    toast(`${dur(d.duration)} · +${num(d.xp)} XP · +${num(d.coins)} coins`, { title: afk ? 'Session ended - no check-in' : 'Session complete', icon: 'chrono_clock', kind: afk ? 'warn' : 'good' });
    notify(afk ? 'Session ended' : 'Session complete', `${dur(d.duration)} focused`, 'end');
  },
  progress() { refreshSession(); },
  level_up(d) { refreshMe(); celebrate({ title: `Level ${d.new_level}`, sub: `You climbed from level ${d.old_level}.`, tier: state.me?.level?.tier_key, tierName: d.tier || state.me?.level?.tier }); notify('Level up!', `You reached level ${d.new_level}.`, 'lvl'); },
  streak_broken(d) { toast(`You lost a ${d.lost}-day streak. Study today to start a new one.`, { title: 'Streak lost', icon: 'chronos_streak', kind: 'bad' }); },
  achievement(d) { (d.items || []).forEach((a) => toast(a.description, { title: `${a.emoji || ''} ${a.name}${a.reward_coins ? ` · +${num(a.reward_coins)} coins` : ''}`, icon: 'achievement_trophy', kind: 'good' })); notify('Achievement unlocked', (d.items || []).map((a) => a.name).join(', '), 'ach'); },
  box_drop(d) { toast('A Halloween box dropped while you studied.', { title: `${BOX_NAMES[d.box_id] || ''} box`, icon: 'mystery_box' }); },
  pass_level(d) { toast(d.name || '', { title: `Pass level ${d.level}`, icon: 'halloween_candy' }); },
  pet_level_up(d) { toast(`${d.nickname} reached level ${d.new_level}.`, { title: 'Pet levelled up', icon: 'candy' }); },
  pet_evolved(d) { toast(`${d.nickname} evolved into ${d.new_stage}!`, { title: 'Evolution', icon: 'champion_crown', kind: 'good' }); notify('Your pet evolved!', `${d.nickname} is now ${d.new_stage}`, 'evo'); },
  top3_perk(d) { toast(`${d.perk_name} is active. +${num(d.coins)} coins.`, { title: 'Top 3 daily perk', icon: 'rank_crown', kind: 'good' }); },
  pomodoro_phase(d) { toast(`${d.minutes} min · ${d.channel || ''}`, { title: d.phase === 'focus' ? 'Focus time' : 'Break time', icon: 'pomodoro' }); notify(d.phase === 'focus' ? 'Focus time' : 'Break time', `${d.minutes} minutes`, 'pomo'); },
  refresh() { emit('data-changed', {}); refreshSession(); refreshMe(); },
};

export function connect() {
  if (es) return;
  const url = `/api/events${lastId ? `?last=${lastId}` : ''}`;
  es = new EventSource(url);
  es.onopen = () => { refreshSession(); };
  es.onerror = () => { /* the browser reconnects by itself and resends Last-Event-ID */ };
  es.onmessage = (ev) => {
    let msg; try { msg = JSON.parse(ev.data); } catch { return; }
    lastId = Math.max(lastId, msg.id || 0);
    if (msg.guild_id && state.guild && msg.guild_id !== String(state.guild)) return;   // another server
    handlers[msg.kind]?.(msg.data || {});
    emit('live', msg);
    if (msg.kind !== 'refresh' && msg.kind !== 'progress') emit('data-changed', { kind: msg.kind });
  };
}
export function disconnect() { es?.close(); es = null; }
