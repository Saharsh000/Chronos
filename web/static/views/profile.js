import { h, get, mount, dur, num, ago, fmtDate, timeRange, state, ico, tierIcon, SUBJECTS, loadCss, clock, nowSec } from '/static/core/core.js';
import { avatar, pageHead, errorBox, loadingPage, empty, bar, ring, modal, tabs } from '/static/core/ui.js';

function heat(days, max) {
  const cells = [], pad = days.length ? days[0].weekday : 0;
  for (let i = 0; i < pad; i++) cells.push(h('i', { class: 'pad' }));
  days.forEach((d) => {
    const l = !d.seconds ? '' : `l${Math.min(4, Math.max(1, Math.ceil((d.seconds / Math.max(1, max)) * 4)))}`;
    cells.push(h('i', { class: l, title: `${fmtDate(Date.parse(d.date) / 1000)}: ${d.seconds ? dur(d.seconds) : 'no study'}` }));
  });
  return h('div', { class: 'heat', role: 'img', 'aria-label': 'Study heat map, last 17 weeks' }, cells);
}
const reasonTag = (r) => (r === 'afk_timeout' ? h('span', { class: 'tag warn' }, 'No check-in') : null);

export default async function profile(root, ctx) {
  loadCss('/static/views/stats.css');
  const other = ctx.params.id && ctx.params.id !== state.me.user.id ? ctx.params.id : null;
  const q = other ? { user: other } : {};
  const host = h('div', { class: 'stack lg' });
  mount(root, host, loadingPage(3));
  let sessions = [], next = null, liveEl = null, p = null;

  async function load() {
    try {
      const [prof, hm, hist, ach] = await Promise.all([get(other ? `/api/users/${other}` : '/api/profile'), get('/api/heatmap', { ...q, days: 119 }),
        get('/api/sessions/history', { ...q, limit: 8 }), get('/api/achievements', q)]);
      p = prof; sessions = hist.sessions; next = hist.next; paint(hm, ach);
    } catch (e) { mount(root, errorBox(e, () => { mount(root, host); load(); })); }
  }

  function paint(hm, ach) {
    const L = p.level, u = p.user;
    const hero = h('div', { class: 'panel accent hero' },
      avatar(u, 92), h('div', { class: 'nm' }, h('h1', u.name),
        p.equipped_title ? h('span', { class: 'tag accent' }, p.equipped_title) : null,
        h('div', { class: 'row' }, tierIcon(L.tier_key, 28), h('b', `${L.tier} · Level ${L.level}`), p.rank_position ? h('span', { class: 'tag' }, `#${p.rank_position} on the server`) : null,
          p.in_session_seconds != null ? h('span', { class: 'tag good' }, h('i', { class: 'studying-dot' }), `Studying ${p.in_session_subject ? `${p.in_session_subject.label} ` : ''}for `, h('span', { class: 'num', dataset: { since: nowSec() - p.in_session_seconds } }, clock(p.in_session_seconds))) : null),
        h('div', { class: 'stack', style: { gap: '6px', maxWidth: '420px' } }, bar(L.into / L.needed, { lg: true }), h('span', { class: 'faint num' }, `${num(L.into)} / ${num(L.needed)} XP to level ${L.level + 1}`))),
      h('div', { class: 'stack' }, h('button', { class: 'btn', onClick: share }, 'Share card'), !other ? null : h('a', { class: 'btn ghost', href: `/compare?b=${u.id}` }, 'Compare with me')));

    const strip = h('div', { class: 'stat-strip' },
      [['Total time', dur(p.total_seconds)], ['Today', dur(p.today_seconds)], ['This week', dur(p.week_seconds)], ['Sessions', num(p.sessions_count)], ['Streak', `${p.streak.current}d`, `best ${p.streak.longest}d`]]
        .map(([l, v, s]) => h('div', { class: 'stat' }, h('div', { class: 'v' }, v), h('div', { class: 'l' }, s ? `${l} · ${s}` : l))));

    const wk = p.weekly, maxD = Math.max(...wk.days.map((d) => d.seconds), 1);
    const weekPanel = h('div', { class: 'panel' }, h('div', { class: 'panel-head' }, h('h2', 'This week'), h('span', { class: 'faint' }, `${dur(wk.total_week_seconds)} · avg ${dur(wk.daily_avg_seconds)}/day`)),
      h('div', { class: 'bars' }, wk.days.map((d) => h('div', { class: d.is_today ? 'today' : '', title: `${d.date_str}: ${dur(d.seconds)}` }, h('span', { class: 'faint num', style: { fontSize: '.72rem' } }, d.seconds ? dur(d.seconds) : ''),
        h('div', { class: `col ${d.seconds ? 'on' : ''}`, style: { height: `${Math.max(4, (d.seconds / maxD) * 92)}px` } }), h('span', { class: 'faint', style: { fontSize: '.74rem' } }, d.day_name.slice(0, 1) + d.day_name.slice(1).toLowerCase())))),
      wk.peak_day_seconds ? h('p', { class: 'faint' }, `Best day: ${wk.peak_day_name.slice(0, 1) + wk.peak_day_name.slice(1).toLowerCase()} · ${dur(wk.peak_day_seconds)} · ${wk.active_days_count}/7 days active`) : h('p', { class: 'faint' }, 'No study logged this week yet.'));

    const wd = p.analytics.weekdays, maxW = Math.max(...wd.map((d) => d.seconds), 1);
    const habit = h('div', { class: 'panel' }, h('div', { class: 'panel-head' }, h('h2', 'When you study'), p.analytics.sessions_logged ? h('span', { class: 'faint' }, `avg session ${dur(p.analytics.avg_session_seconds)} · longest ${dur(p.analytics.longest_session_seconds)}`) : null),
      h('div', { class: 'bars', style: { height: '110px' } }, wd.map((d) => h('div', { title: `${d.day}: ${dur(d.seconds)}` }, h('div', { class: `col ${d.seconds ? 'on' : ''}`, style: { height: `${Math.max(4, (d.seconds / maxW) * 62)}px`, opacity: d.seconds ? 0.35 + 0.65 * (d.seconds / maxW) : 1 } }), h('span', { class: 'faint', style: { fontSize: '.74rem' } }, d.short)))),
      p.analytics.favorite_subject ? h('p', { class: 'faint' }, `Favourite subject: ${p.analytics.favorite_subject.label}`) : null);

    const heatPanel = h('div', { class: 'panel' }, h('div', { class: 'panel-head' }, h('h2', 'Last 17 weeks'), h('span', { class: 'faint' }, `${hm.days.filter((d) => d.seconds).length} active days`)), heat(hm.days, hm.max));

    const total = Math.max(1, p.subjects.reduce((a, s) => a + s.seconds, 0));
    const subj = h('div', { class: 'panel' }, h('h2', 'Subjects'), p.subjects.map((s) => h('div', { class: 'subj-row' }, ico(SUBJECTS[s.key].icon, 32), h('div', h('b', s.label), h('div', { class: 'faint' }, s.sessions ? `${s.sessions} sessions · avg ${dur(s.avg_seconds)}` : 'No tagged sessions')),
      h('b', { class: 'num' }, dur(s.seconds)), bar(s.seconds / total, { color: SUBJECTS[s.key].color }))));

    const t = p.trivia;
    const trivia = h('div', { class: 'panel' }, h('div', { class: 'panel-head' }, h('h2', 'JEE trivia'), h('a', { href: '/trivia' }, 'Play')),
      t.attempted ? [h('div', { class: 'row' }, h('span', { class: 'tag accent' }, t.title), h('span', { class: 'faint' }, `rank ${t.rank} of ${t.players}`)),
        h('div', { class: 'kv' }, h('span', 'Marks'), h('b', num(t.marks))), h('div', { class: 'kv' }, h('span', 'Correct'), h('b', `${num(t.correct)} / ${num(t.attempted)}`)),
        t.next_title ? [bar((t.marks - t.min_marks) / Math.max(1, t.next_marks - t.min_marks)), h('span', { class: 'faint' }, `${num(Math.max(0, t.next_marks - t.marks))} marks to ${t.next_title}`)] : null]
        : h('p', { class: 'mute' }, 'No trivia answered yet.'));

    const achPanel = h('div', { class: 'panel' }, h('div', { class: 'panel-head' }, h('h2', 'Achievements'), h('a', { href: other ? `/achievements?user=${u.id}` : '/achievements' }, 'View all')),
      h('div', { class: 'row' }, ring(ach.unlocked / ach.total, { size: 64, stroke: 7 }, h('b', { class: 'num' }, ach.unlocked)), h('span', { class: 'mute' }, `of ${ach.total} unlocked`)),
      ach.recent.length ? h('div', { class: 'list' }, ach.recent.slice(0, 3).map((r) => h('div', h('span', { 'aria-hidden': 'true' }, r.emoji), h('b', { class: 'grow' }, r.name), h('span', { class: 'faint' }, ago(r.at))))) : null);

    const wallet = h('div', { class: 'panel' }, h('h2', 'Wallet & pet'), h('div', { class: 'kv' }, h('span', 'Chronocoins'), h('b', { class: 'pill' }, ico('chronocoin', 18), num(p.wallet.coins))),
      h('div', { class: 'kv' }, h('span', 'Lifetime earned'), h('b', num(p.wallet.lifetime_earned))), h('div', { class: 'kv' }, h('span', 'Candy'), h('b', { class: 'pill' }, ico('candy', 18), num(p.wallet.candy))),
      p.equipped_pet ? h('div', { class: 'kv' }, h('span', 'Pet'), h('b', `${p.equipped_pet.nickname || p.equipped_pet.species_id} · Lv ${p.equipped_pet.level}`)) : null);

    const hist = h('div', { class: 'panel' }, h('h2', 'Recent sessions'), h('div', { class: 'list', id: 'hist' }), h('div', { id: 'more' }));
    mount(host, hero, strip, h('div', { class: 'grid split' }, h('div', { class: 'stack lg' }, weekPanel, heatPanel, habit, hist), h('div', { class: 'stack lg' }, subj, achPanel, trivia, wallet)));
    paintHist();
  }

  function paintHist() {
    const list = document.getElementById('hist'), more = document.getElementById('more'); if (!list) return;
    sessions.length ? mount(list, sessions.map((s) => h('div', s.subject ? ico(SUBJECTS[s.subject.key].icon, 28) : ico('chrono_clock', 28),
      h('div', { class: 'grow' }, h('b', timeRange(s.start, s.end)), h('div', { class: 'faint' }, `${fmtDate(s.start)} · ${s.subject?.label || 'General'}`)), reasonTag(s.reason), h('div', { style: { textAlign: 'right' } }, h('b', dur(s.duration)), h('div', { class: 'faint' }, `+${num(s.xp)} XP`)))))
      : mount(list, empty({ icon: 'focus_clock', title: 'No finished sessions yet', text: 'Completed sessions show up here with their start and end times.' }));
    mount(more, next ? h('button', { class: 'btn sm', onClick: async (e) => { e.currentTarget.classList.add('busy'); const r = await get('/api/sessions/history', { ...q, limit: 8, before: next }); sessions = sessions.concat(r.sessions); next = r.next; paintHist(); } }, 'Show older') : null);
  }

  function share() {
    let page = 'overview';
    const img = h('img', { class: 'card-img', alt: 'Stats card' }), dl = h('a', { class: 'btn', download: 'chronos-stats.png' }, 'Download image');
    const set = (pg) => { page = pg; const url = `/api/stats/card.png?page=${pg}${other ? `&user=${other}` : ''}`; img.src = url; dl.href = url; };
    modal({ title: 'Share your stats', wide: true, content: h('div', { class: 'stack' }, tabs([['overview', 'Overview'], ['weekly', 'Weekly'], ['subjects', 'Subjects'], ['trivia', 'Trivia']].map(([id, label]) => ({ id, label })), page, set), img, h('div', dl)),
      actions: [{ label: 'Close', value: true }] });
    set(page);
  }

  await load();
  ctx.every(1000, () => document.querySelectorAll('[data-since]').forEach((n) => { n.textContent = clock(nowSec() - Number(n.dataset.since)); }));
  ctx.onData(load);
}
