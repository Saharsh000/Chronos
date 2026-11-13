import { h, get, post, mount, ico, num, loadCss } from '/static/core/core.js';
import { pageHead, errorBox, loadingPage, toast, tabs, chips, empty, bar, avatar, modal } from '/static/core/ui.js';
import { round } from '/static/views/trivia_arena.js';
import { subKey } from '/static/views/trivia_ui.js';

const TABS = [{ id: 'play', label: 'Play' }, { id: 'stats', label: 'My stats' }, { id: 'leaderboard', label: 'Leaderboard' }, { id: 'vault', label: 'Question vault' }];
const SUB_ICON = { physics: 'subject_physics', chemistry: 'subject_chemistry', mathematics: 'subject_maths' };
const SUB_BLURB = { physics: 'Mechanics to modern physics', chemistry: 'Physical, organic and inorganic', mathematics: 'Algebra, calculus, vectors and more' };
const MEDAL = ['medal_1', 'medal_2', 'medal_3'];
const newSession = () => ({ attempted: 0, correct: 0, marks: 0, coins: 0, xp: 0, candy: 0, streak: 0, skipped: 0, timeouts: 0, started: Date.now() });

export default async function trivia(root, ctx) {
  loadCss('/static/views/economy.css'); loadCss('/static/views/trivia.css');
  let syl = null, me = null, tab = ['stats', 'leaderboard', 'vault'].includes(ctx.params?.mode) ? ctx.params.mode : 'play';
  let screen = 'hub', browse = null, filter = null, session = newSession(), cdUntil = 0, search = '';
  const head = h('div'), body = h('div', { class: 'tz' });
  mount(root, head, body); mount(body, loadingPage(3));
  const cooldownLeft = () => Math.max(0, cdUntil - Date.now() / 1000);

  async function load() {
    try {
      [syl, me] = await Promise.all([get('/api/trivia/syllabus'), get('/api/trivia/stats')]);
      cdUntil = Date.now() / 1000 + (me.cooldown || 0);
      paint();
    } catch (e) { mount(body, errorBox(e, load)); }
  }
  const subject = (id) => syl.subjects.find((s) => s.id === id);
  const chapterOf = (id) => syl.subjects.flatMap((s) => s.chapters.map((c) => ({ ...c, subject: s }))).find((c) => c.id === id);

  // ------------------------------------------------------------ starting questions
  async function start(f, btn) {
    const left = cooldownLeft();
    if (left > 0.3 && screen !== 'hub') { toast(`Next question unlocks in ${Math.ceil(left)}s.`, { kind: '', title: 'Cooling down' }); }
    btn?.classList.add('busy');
    try {
      const q = await post('/api/trivia/question', { subject: f.subject, chapter: f.chapter, topic: f.topic });
      filter = f; cdUntil = Date.now() / 1000 + syl.limits.cooldown;
      screen = 'arena'; paint(q);
    } catch (e) {
      if (e.code === 'cooldown') { cdUntil = Date.now() / 1000 + (e.data?.retry_after || 5); toast(`Give it ${Math.ceil(e.data?.retry_after || 5)} more seconds.`, { title: 'Slow down a little' }); }
      else toast(e.data?.suggestions?.length ? `${e.message} Try: ${e.data.suggestions.slice(0, 3).join(', ')}.` : e.message, { kind: 'bad', title: 'No question yet' });
    } finally { btn?.classList.remove('busy'); }
  }
  const labelOf = (f) => (f.topic ? 'this topic' : f.chapter ? chapterOf(f.chapter)?.name : f.subject ? subject(f.subject)?.name : 'random questions');

  // ------------------------------------------------------------ paint
  function paint(q) {
    if (screen === 'arena' && q) return paintArena(q);
    if (screen === 'summary') return paintSummary();
    mount(head, pageHead('JEE Trivia', 'Real JEE-style questions, graded by the Chronos question service. Marks, coins and XP are the same ones the bot shows.',
      h('span', { class: 'pill' }, ico('chronocoin', 18), num(me.coins))));
    const t = tabs(TABS, tab, (id) => { tab = id; browse = null; paintTab(); });
    mount(body, t, h('div', { class: 'tz-tab' }));
    paintTab();
  }
  function paintTab() {
    const box = body.querySelector('.tz-tab'); if (!box) return;
    ({ play: paintPlay, stats: paintStats, leaderboard: paintLb, vault: paintVault })[tab](box);
  }

  // ---- play hub
  function rankCard() {
    const s = me.stats, t = me.tier;
    return h('section', { class: 'tz-rank panel accent' },
      h('div', { class: 'who' }, ico('trophy', 48), h('div', h('h2', t.title), h('p', 'Your trivia rank'))),
      h('div', { class: 'nums' }, stat('Marks', num(s.marks)), stat('Rank', me.rank ? `#${me.rank}` : 'Unranked'), stat('Accuracy', s.attempted ? `${s.accuracy.toFixed(0)}%` : 'No data'), stat('Streak', s.streak)),
      h('div', { class: 'prog' }, bar(t.progress / 100), h('span', { class: 'faint' }, t.next_title ? `${num(t.needed)} more marks to ${t.next_title}` : 'Highest rank reached.')));
  }
  const stat = (k, v) => h('div', { class: 'st' }, h('b', String(v)), h('span', k));
  function paintPlay(box) {
    if (browse) return paintBrowse(box);
    const results = h('div', { class: 'tz-results' });
    const input = h('input', { class: 'input', type: 'search', placeholder: 'Search any chapter or topic, e.g. rotational, hybridisation, conics', 'aria-label': 'Search chapters and topics', value: search });
    input.addEventListener('input', () => { search = input.value; paintResults(results); });
    mount(box, rankCard(),
      h('div', { class: 'tz-quick' },
        h('button', { class: 'btn primary lg', type: 'button', onClick: (e) => start({}, e.currentTarget) }, ico('atom', 20), 'Random question'),
        h('span', { class: 'faint' }, 'Any subject, any chapter. Skips cost 15 Chronocoins.')),
      h('div', { class: 'tz-subjects' }, syl.subjects.map((s) => h('article', { class: 'tz-sub', style: { '--sc': `var(--${subKey(s.id)})` } },
        ico(SUB_ICON[s.id], 48), h('h3', s.name), h('p', SUB_BLURB[s.id]), h('span', { class: 'faint' }, `${s.chapters.length} chapters, ${s.chapters.reduce((n, c) => n + c.topics.length, 0)} topics`),
        h('div', { class: 'row' }, h('button', { class: 'btn primary', type: 'button', onClick: (e) => start({ subject: s.id }, e.currentTarget) }, `Random ${s.name}`),
          h('button', { class: 'btn', type: 'button', onClick: () => { browse = { id: s.id, section: 'all' }; paintTab(); } }, 'Browse chapters'))))),
      h('section', { class: 'tz-find' }, h('h3', 'Find a chapter or topic'), input, results));
    paintResults(results);
  }
  function paintResults(box) {
    const q = search.trim().toLowerCase();
    if (q.length < 2) return mount(box);
    const hits = [];
    for (const s of syl.subjects) for (const c of s.chapters) {
      const hay = `${c.name} ${(c.aliases || []).join(' ')}`.toLowerCase();
      if (hay.includes(q)) hits.push({ s, c, t: null });
      else for (const t of c.topics) if (t.name.toLowerCase().includes(q)) hits.push({ s, c, t });
      if (hits.length > 40) break;
    }
    if (!hits.length) return mount(box, h('p', { class: 'faint' }, 'Nothing matches that. Try a shorter word.'));
    mount(box, h('div', { class: 'tz-hits' }, hits.slice(0, 40).map(({ s, c, t }) => h('button', { class: 'hit', type: 'button', style: { '--sc': `var(--${subKey(s.id)})` },
      onClick: (e) => start({ subject: s.id, chapter: c.id, topic: t?.id }, e.currentTarget) },
    h('span', { class: 'dotc' }), h('b', t ? t.name : c.name), h('span', { class: 'faint' }, t ? `${c.name}, ${s.name}` : `${s.name}, ${c.topics.length} topics`)))));
  }

  // ---- subject browser
  function paintBrowse(box) {
    const s = subject(browse.id), sc = `var(--${subKey(s.id)})`;
    const list = h('div', { class: 'tz-chapters' });
    const paintList = () => mount(list, s.chapters.filter((c) => browse.section === 'all' || c.section === browse.section).map((c) => h('article', { class: 'tz-chap' },
      h('div', h('b', c.name), h('span', { class: 'faint' }, `${c.topics.length} topics`)),
      h('div', { class: 'tags' }, (c.exams || []).map((x) => h('span', { class: 'tag' }, x === 'advanced' ? 'Advanced' : 'Main'))),
      h('div', { class: 'row' }, h('button', { class: 'btn sm primary', type: 'button', onClick: (e) => start({ subject: s.id, chapter: c.id }, e.currentTarget) }, 'Random topic'),
        h('button', { class: 'btn sm', type: 'button', onClick: () => topicPicker(s, c) }, 'Pick a topic')))));
    const sec = chips([{ id: 'all', label: 'All sections' }, ...s.sections.map((x) => ({ id: x, label: x }))], browse.section, (id) => { browse.section = id; paintList(); });
    mount(box, h('div', { class: 'tz-browse', style: { '--sc': sc } },
      h('div', { class: 'row' }, h('button', { class: 'btn sm ghost', type: 'button', onClick: () => { browse = null; paintTab(); } }, 'All subjects'), h('h2', s.name),
        h('button', { class: 'btn sm primary', type: 'button', style: { marginLeft: 'auto' }, onClick: (e) => start({ subject: s.id }, e.currentTarget) }, `Random ${s.name}`)),
      sec, list));
    paintList();
  }
  function topicPicker(s, c) {
    const q = h('input', { class: 'input', type: 'search', placeholder: `Search ${c.topics.length} topics`, 'aria-label': 'Search topics' });
    const list = h('div', { class: 'tz-topics' });
    let m;
    const go = async (t, btn) => { await start({ subject: s.id, chapter: c.id, topic: t?.id }, btn); if (screen === 'arena') m.close(); };
    const paintT = () => mount(list, c.topics.filter((t) => t.name.toLowerCase().includes(q.value.trim().toLowerCase())).map((t) => h('button', { class: 'topic', type: 'button', onClick: (e) => go(t, e.currentTarget) }, t.name)));
    q.addEventListener('input', paintT); paintT();
    m = modal({ title: c.name, wide: true, cls: 'tz-modal', content: h('div', { class: 'stack' }, h('button', { class: 'btn primary', type: 'button', onClick: (e) => go(null, e.currentTarget) }, 'Any topic in this chapter'), q, list) });
  }

  // ---- arena + summary
  function paintArena(q) {
    const s = session;
    const strip = h('div', { class: 'tz-session' });
    const paintStrip = () => mount(strip, h('span', h('b', s.attempted), ' answered'), h('span', h('b', s.correct), ' correct'), h('span', h('b', `${s.marks > 0 ? '+' : ''}${s.marks}`), ' marks'),
      h('span', h('b', num(s.coins)), ' coins'), h('span', { class: 'faint' }, `Practising ${labelOf(filter)}`));
    paintStrip();
    mount(head);
    const r = round({ q, session, ctx, cooldownLeft, onResult: paintStrip,
      onNext: async (btn) => { await start(filter, btn); },
      onChange: () => { screen = 'hub'; reload(); },
      onStop: () => { screen = session.attempted + session.skipped + session.timeouts ? 'summary' : 'hub'; screen === 'summary' ? paint() : reload(); } });
    mount(body, strip, r.el);
    window.scrollTo({ top: 0 });
  }
  async function reload() {
    try { me = await get('/api/trivia/stats'); } catch { /* keep the old numbers */ }
    paint();
  }
  function paintSummary() {
    const s = session, mins = Math.max(1, Math.round((Date.now() - s.started) / 60000));
    mount(head, pageHead('Session summary', `${mins} min of practice.`));
    mount(body, h('section', { class: 'panel accent tz-summary' },
      h('div', { class: 'nums' }, stat('Answered', s.attempted), stat('Correct', s.correct), stat('Accuracy', s.attempted ? `${Math.round(s.correct / s.attempted * 100)}%` : 'No data'), stat('Net marks', `${s.marks > 0 ? '+' : ''}${s.marks}`),
        stat('Coins earned', num(s.coins)), stat('XP earned', num(s.xp)), s.skipped ? stat('Skipped', s.skipped) : null, s.timeouts ? stat('Timed out', s.timeouts) : null),
      h('div', { class: 'row' }, h('button', { class: 'btn primary lg', type: 'button', onClick: () => { session = newSession(); screen = 'hub'; reload(); } }, 'Back to trivia'),
        h('button', { class: 'btn lg', type: 'button', onClick: () => { tab = 'leaderboard'; session = newSession(); screen = 'hub'; reload(); } }, 'See the leaderboard'))));
  }

  // ---- my stats
  function paintStats(box) {
    const s = me.stats, t = me.tier;
    const ladder = me.ladder.map((r) => h('div', { class: `rung ${r.title === t.title ? 'now' : s.marks >= r.min ? 'got' : ''}` }, h('b', r.title), h('span', { class: 'faint' }, `${num(r.min)}+ marks`), h('i', r.badge || '')));
    mount(box, rankCard(),
      h('section', { class: 'panel' }, h('h3', 'Lifetime'), h('div', { class: 'nums big' }, stat('Attempted', num(s.attempted)), stat('Correct', num(s.correct)), stat('Best streak', s.best_streak), stat('Coins won', num(s.coins_won)))),
      h('section', { class: 'panel' }, h('h3', 'The rank ladder'), h('p', { class: 'faint' }, 'Each correct answer earns its marks (+4 on Main, more on Advanced). Wrong answers cost 1. Skipped and timed-out questions don\'t count.'), h('div', { class: 'tz-ladder' }, ladder)));
  }

  // ---- leaderboard
  async function paintLb(box) {
    mount(box, loadingPage(2));
    try {
      const d = await get('/api/trivia/leaderboard', { limit: 25 });
      if (!d.rows.length) return mount(box, empty({ icon: 'trophy', title: 'Nobody has played yet', text: 'Answer one question to take the first spot.' }));
      mount(box, h('div', { class: 'tz-lb' }, d.rows.map((r) => h('div', { class: `lbrow ${r.me ? 'me' : ''}` },
        r.rank <= 3 ? ico(MEDAL[r.rank - 1], 32) : h('b', { class: 'rk' }, `#${r.rank}`), avatar(r.user, 40),
        h('div', { class: 'who' }, h('b', r.user.name), h('span', { class: 'faint' }, r.tier)),
        h('div', { class: 'cells' }, h('span', h('b', num(r.marks)), ' marks'), h('span', h('b', `${r.accuracy.toFixed(0)}%`), ' accuracy'), h('span', h('b', r.attempted), ' played'), h('span', h('b', r.best_streak), ' best streak')))),
      d.you.rank && d.you.rank > d.rows.length ? h('div', { class: 'lbrow me' }, h('b', { class: 'rk' }, `#${d.you.rank}`), h('div', { class: 'who' }, h('b', 'You'), h('span', { class: 'faint' }, d.you.tier.title)), h('div', { class: 'cells' }, h('span', h('b', num(d.you.stats.marks)), ' marks'))) : null,
      h('p', { class: 'faint' }, `${d.players} player${d.players === 1 ? '' : 's'} ranked in this server.`)));
    } catch (e) { mount(box, errorBox(e, () => paintLb(box))); }
  }

  // ---- vault
  async function paintVault(box) {
    mount(box, loadingPage(1));
    try {
      const v = await get('/api/trivia/cache');
      mount(box, h('section', { class: 'panel' }, h('h3', 'Question vault'),
        h('p', { class: 'mute' }, 'Questions are pre-generated in the background so most picks load instantly. When a chapter has one waiting, you get it straight away.'),
        h('div', { class: 'nums big' }, stat('Ready now', num(v.total)), stat('Chapters covered', num(v.chapters)), stat('Topics covered', num(v.topics)),
          ...Object.entries(v.by_subject).map(([k, n]) => stat(k[0].toUpperCase() + k.slice(1), num(n)))),
        v.pregen ? h('p', { class: 'faint' }, v.pregen.paused ? `Generation is paused${v.pregen.reason ? `: ${v.pregen.reason}` : ''}.` : 'Generation is running.') : null));
    } catch (e) { mount(box, errorBox(e, () => paintVault(box))); }
  }

  await load();
}
