// Chronos Web - app shell: login, navigation, router, global AFK banner.
import { state, emit, on, get, post, h, ico, tierIcon, mount, clock, nowSec, dur, num, api } from '/static/core/core.js';
import { toast, errToast, loadingPage, errorBox, avatar, empty, modal } from '/static/core/ui.js';
import { connect, refreshSession, refreshMe, alertsOn, enableAlerts, disableAlerts } from '/static/core/live.js';

const appEl = document.getElementById('app');

// ------------------------------------------------------------ routes
const NAV = [
  { group: 'Study', items: [
    { path: '/', view: 'home', label: 'Home', icon: 'chrono_clock' },
    { path: '/live', view: 'live', label: 'Live', icon: 'focus_clock', badge: 'live' },
    { path: '/progress', view: 'progress', label: 'Progress', icon: 'study_book' },
    { path: '/notes', view: 'notes', label: 'Notes', icon: 'notes' },
    { path: '/trivia', view: 'trivia', label: 'JEE Trivia', icon: 'atom' },
  ] },
  { group: 'You', items: [
    { path: '/me', view: 'profile', label: 'Profile', icon: 'crown' },
    { path: '/achievements', view: 'achievements', label: 'Achievements', icon: 'achievement_trophy' },
    { path: '/rewards', view: 'rewards', label: 'Rewards', icon: 'chronocoin' },
    { path: '/bag', view: 'bag', label: 'Bag', icon: 'mystery_box' },
    { path: '/pets', view: 'pets', label: 'Pets', icon: 'sugar_rush' },
  ] },
  { group: 'Server', items: [
    { path: '/leaderboard', view: 'leaderboard', label: 'Leaderboard', icon: 'trophy' },
    { path: '/compare', view: 'compare', label: 'Compare & Fame', icon: 'compass' },
    { path: '/shop', view: 'shop', label: 'Shop', icon: 'title_scroll' },
    { path: '/halloween', view: 'halloween', label: 'Halloween', icon: 'halloween_candy' },
  ] },
  { group: 'More', items: [
    { path: '/admin', view: 'admin', label: 'Admin', icon: 'streak_freeze', manager: true },
    { path: '/help', view: 'help', label: 'Help', icon: 'grimoire' },
  ] },
];
const ROUTES = [
  ...NAV.flatMap((g) => g.items.map((i) => [i.path, i.view])),
  ['/u/:id', 'profile'], ['/progress/:subject', 'progress'], ['/trivia/:mode', 'trivia'],
];
function matchRoute(path) {
  for (const [pat, view] of ROUTES) {
    const a = pat.split('/'), b = path.split('/');
    if (a.length !== b.length) continue;
    const params = {};
    if (a.every((seg, i) => (seg.startsWith(':') ? ((params[seg.slice(1)] = decodeURIComponent(b[i])), true) : seg === b[i]))) return { view, params };
  }
  return null;
}

// ------------------------------------------------------------ boot
async function boot() {
  let me;
  try { me = await get('/api/me'); } catch (e) { return mount(appEl, h('div', { class: 'login' }, errorBox(e, () => location.reload()))); }
  if (!me.authed) return showLogin(me);
  state.me = me;
  if (me.no_guild) return showNoGuild(me);
  state.guild = me.guild;
  document.documentElement.dataset.tier = me.level?.tier_key || '';
  buildShell();
  connect();
  await refreshSession();
  startClocks();
  on('unauth', () => location.reload());
  on('data-changed', debounceFn(() => { refreshMe(); }, 600));
  on('me', paintMe);
  window.addEventListener('popstate', () => renderRoute());
  document.addEventListener('click', onLinkClick);
  renderRoute();
}

function showLogin(me) {
  const q = new URLSearchParams(location.search).get('login');
  const msg = { expired: 'That link expired or was already used. Run it again in Discord.', failed: 'Discord sign-in failed. Try again.',
    noguild: 'You need to be in a server that uses Chronos.', help: 'Discord sign-in isn\'t set up here yet. Use the command below.' }[q];
  const devForm = me.dev_mode ? h('form', { class: 'row', method: 'get', action: '/auth/dev' },
    h('input', { class: 'input', name: 'user', placeholder: 'Dev: Discord user id', required: true }), h('button', { class: 'btn' }, 'Dev sign-in')) : null;
  mount(appEl, h('div', { class: 'login' }, h('div', { class: 'panel card accent' },
    ico('chrono_clock', 96),
    h('div', h('h1', 'Chronos'), h('p', { class: 'mute', style: { marginTop: '8px' } }, 'Your study sessions, XP and rewards - the same account as the Discord bot.')),
    msg ? h('div', { class: 'err-box', style: { width: '100%' } }, msg) : null,
    me.oauth ? h('a', { class: 'btn primary lg block', href: '/auth/login' }, 'Continue with Discord') : null,
    h('div', { class: 'stack', style: { width: '100%' } },
      h('p', { class: 'mute' }, me.oauth ? 'Or sign in from Discord:' : 'Sign in from Discord:'),
      h('div', h('span', { class: 'code' }, `${me.prefix}weblogin`)),
      h('p', { class: 'faint', style: { fontSize: '.86rem' } }, 'The bot DMs you a private one-time link. It expires in 10 minutes.')),
    devForm)));
}
function showNoGuild(me) {
  mount(appEl, h('div', { class: 'login' }, h('div', { class: 'panel card' }, ico('compass', 64),
    h('h1', 'No server found'), h('p', { class: 'mute' }, 'You\'re signed in, but you aren\'t in a Discord server that uses Chronos. Join one, then reload.'),
    h('button', { class: 'btn', onClick: async () => { await post('/auth/logout'); location.reload(); } }, 'Sign out'))));
}

// ------------------------------------------------------------ shell
let mainEl, railEl, afkEl, viewCleanup = [];
function buildShell() {
  const me = state.me;
  const guildPick = me.guilds.length > 1 ? h('select', { class: 'select guild-pick', 'aria-label': 'Server',
    onChange: async (e) => { await post('/api/guild', { id: e.target.value }); location.reload(); } },
    me.guilds.map((g) => h('option', { value: g.id, selected: g.id === state.guild }, g.name))) : null;

  const navEl = h('nav', { class: 'nav', 'aria-label': 'Main' }, NAV.map((g) => {
    const items = g.items.filter((i) => !i.manager || me.user.is_manager);
    return items.length ? [h('div', { class: 'nav-group' }, g.group), items.map((i) =>
      h('a', { href: i.path, dataset: { path: i.path } }, ico(i.icon, 22), h('span', i.label), i.badge ? h('span', { class: 'badge hide', id: `badge-${i.badge}` }) : null))] : null;
  }));
  const themeBtn = h('button', { class: 'icon-btn', title: 'Switch theme', 'aria-label': 'Switch theme', onClick: toggleTheme }, '◐');
  const bellBtn = h('button', { class: 'icon-btn', id: 'bell', title: 'Browser alerts', 'aria-label': 'Browser alerts', onClick: toggleAlerts }, alertsOn() ? '🔔' : '🔕');
  const outBtn = h('button', { class: 'icon-btn', title: 'Sign out', 'aria-label': 'Sign out', onClick: async () => { await post('/auth/logout'); location.reload(); } }, '⎋');
  railEl = h('aside', { class: 'rail', id: 'rail' },
    h('a', { class: 'brand', href: '/' }, ico('chrono_clock', 34), h('div', h('b', 'Chronos'), h('small', 'study, tracked'))),
    guildPick, navEl,
    h('div', { class: 'rail-foot' }, h('a', { class: 'me-card', href: '/me', id: 'me-card' }), h('div', { class: 'rail-tools' }, themeBtn, bellBtn, outBtn)));
  mainEl = h('main', { class: 'main', id: 'main' });
  afkEl = h('div', { class: 'afk hide', role: 'alert' });
  const top = h('header', { class: 'topbar' },
    h('button', { class: 'icon-btn', 'aria-label': 'Menu', onClick: () => railEl.classList.toggle('open') }, '☰'),
    h('a', { class: 'brand', href: '/' }, ico('chrono_clock', 28), h('b', 'Chronos')), h('span', { id: 'top-timer', class: 'tag accent hide num' }));
  const bottom = h('nav', { class: 'bottombar', 'aria-label': 'Quick' },
    [['/', 'Home', 'chrono_clock'], ['/live', 'Live', 'focus_clock'], ['/leaderboard', 'Rank', 'trophy'], ['/shop', 'Shop', 'title_scroll']].map(([p, l, i]) =>
      h('a', { href: p, dataset: { path: p } }, ico(i, 24), l)),
    h('a', { href: '#', onClick: (e) => { e.preventDefault(); railEl.classList.add('open'); } }, ico('compass', 24), 'More'));
  mount(appEl, h('div', { class: 'shell' }, railEl, h('div', { class: 'main-col' }, top, afkEl, mainEl)), bottom);
  railEl.addEventListener('click', (e) => { if (e.target.closest('a')) railEl.classList.remove('open'); });
  paintMe();
  setInterval(refreshLiveBadge, 60000); refreshLiveBadge();
}
function paintMe() {
  const c = document.getElementById('me-card'); if (!c) return;
  const u = state.me.user, l = state.me.level;
  mount(c, avatar(u, 38), h('div', { class: 'who' }, h('b', u.name), h('span', `Level ${l.level} · ${l.tier}`)), tierIcon(l.tier_key, 32));
}
async function refreshLiveBadge() {
  try { const a = await get('/api/active'); const b = document.getElementById('badge-live'); if (b) { b.textContent = a.people.length; b.classList.toggle('hide', !a.people.length); } } catch { /* ignore */ }
}
function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
  document.documentElement.dataset.theme = next; try { localStorage.setItem('chronos-theme', next); } catch { /* ignore */ }
}
async function toggleAlerts() {
  const b = document.getElementById('bell');
  if (alertsOn()) { disableAlerts(); b.textContent = '🔕'; toast('You\'ll only see alerts inside the page.', { title: 'Browser alerts off' }); return; }
  const ok = await enableAlerts(); b.textContent = ok ? '🔔' : '🔕';
  toast(ok ? 'We\'ll ping you when you\'re away from this tab: check-ins, breaks and level-ups.' : 'Your browser blocked notifications. Allow them in site settings.', { title: ok ? 'Browser alerts on' : 'Alerts blocked', kind: ok ? 'good' : 'warn' });
}

// ------------------------------------------------------------ global AFK banner + top timer
let tickT;
function startClocks() {
  const paint = () => {
    const s = state.session; const sess = s?.session;
    const topT = document.getElementById('top-timer');
    if (sess) { topT.classList.remove('hide'); topT.textContent = clock(nowSec() - sess.start_time); } else topT?.classList.add('hide');
    if (sess?.afk?.pending) {
      const left = Math.max(0, sess.afk.deadline - nowSec());
      afkEl.classList.remove('hide');
      mount(afkEl, h('span', 'Still studying? Confirm now or your session ends.'), h('span', { class: 't' }, clock(left).slice(3)),
        h('button', { class: 'btn', onClick: async (e) => { e.currentTarget.classList.add('busy'); try { await post('/api/session/checkin'); await refreshSession(); } catch (err) { errToast(err); } } }, 'I\'m here'));
    } else afkEl.classList.add('hide');
  };
  paint(); on('session', paint); tickT = setInterval(paint, 1000);
}

// ------------------------------------------------------------ router
function onLinkClick(e) {
  const a = e.target.closest('a[href]');
  if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || a.target || a.hasAttribute('download')) return;
  const u = new URL(a.href, location.href);
  if (u.origin !== location.origin || u.pathname.startsWith('/auth/') || u.pathname.startsWith('/api/')) return;
  if (u.hash === '#') return;
  e.preventDefault(); navigate(u.pathname + u.search + u.hash);
}
export function navigate(to) { history.pushState({}, '', to); renderRoute(); }
function debounceFn(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

async function renderRoute() {
  viewCleanup.forEach((f) => { try { f(); } catch { /* ignore */ } }); viewCleanup = [];
  const path = location.pathname.replace(/\/+$/, '') || '/';
  document.querySelectorAll('.nav a, .bottombar a').forEach((a) => {
    const p = a.dataset.path; const cur = p && (p === '/' ? path === '/' : path === p || path.startsWith(`${p}/`));
    if (cur) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  const m = matchRoute(path);
  const root = h('div', { class: 'page' });
  mount(mainEl, root); window.scrollTo(0, 0);
  if (!m) { document.title = 'Not found · Chronos'; return mount(root, empty({ icon: 'compass', title: 'Page not found', text: 'That page doesn\'t exist.', action: h('a', { class: 'btn primary', href: '/' }, 'Back home') })); }
  const nav = NAV.flatMap((g) => g.items).find((i) => i.view === m.view);
  document.title = `${nav?.label || 'Chronos'} · Chronos`;
  mount(root, loadingPage());
  let mod;
  try { mod = await import(`/static/views/${m.view}.js`); }
  catch (e) { console.error(e); return mount(root, empty({ icon: 'streak_freeze', title: 'This page is still loading in', text: 'It isn\'t available yet. Try again in a bit.' })); }
  const token = {}; renderRoute.token = token;
  const cleanups = [];
  const reg = (f) => { cleanups.push(f); return f; };
  const ctx = {
    params: m.params, query: Object.fromEntries(new URLSearchParams(location.search)), navigate, state, root,
    on: (name, fn) => reg(on(name, fn)),
    onData: (fn) => reg(on('data-changed', debounceFn(fn, 500))),
    every: (ms, fn) => { const t = setInterval(() => { if (!document.hidden) fn(); }, ms); reg(() => clearInterval(t)); return t; },
    cleanup: reg,
  };
  viewCleanup.push(() => cleanups.forEach((f) => f()));
  try {
    mount(root);
    const out = await mod.default(root, ctx);
    if (typeof out === 'function') viewCleanup.push(out);
  } catch (e) {
    console.error(e);
    if (renderRoute.token === token) mount(root, errorBox(e, () => renderRoute()));
  }
}

boot();
