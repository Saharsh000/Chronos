import { h, get, mount, dur, num, nowSec, tierIcon, ico, SUBJECTS, loadCss } from '/static/core/core.js';
import { avatar, tabs, chips, pageHead, empty, errorBox, loadingPage } from '/static/core/ui.js';

export default async function leaderboard(root, ctx) {
  loadCss('/static/views/stats.css');
  let period = ctx.query.period || 'alltime', subject = ctx.query.subject || '', data = null;
  const body = h('div', { class: 'stack lg' });
  const periodTabs = tabs([['today', 'Today'], ['week', 'This week'], ['month', 'This month'], ['alltime', 'All time']].map(([id, label]) => ({ id, label })), period, (p) => { period = p; load(); });
  const subjChips = chips([{ id: '', label: 'All subjects' }, ...Object.entries(SUBJECTS).map(([k, v]) => ({ id: k, label: v.label, icon: v.icon }))], subject, (s) => { subject = s; load(); });
  mount(root, pageHead('Leaderboard', 'Live rankings for this server. People in a session keep climbing while you watch.'),
    h('div', { class: 'stack' }, periodTabs, subjChips), body);

  const shown = (e) => e.seconds + (e.studying_since ? Math.max(0, nowSec() - data.now) : 0);
  const time = (e) => h('span', { class: 't', dataset: { base: e.seconds, live: e.studying_since ? '1' : '' } }, dur(shown(e)));

  function paint() {
    const es = data.entries;
    if (!es.length) return mount(body, empty({ icon: 'trophy', title: 'Nobody on the board yet', text: 'No study time has been logged for this filter. Start a session to take first place.' }));
    const spot = (e, cls) => e && h('a', { class: `spot ${cls} ${e.me ? 'me' : ''}`, href: e.me ? '/me' : `/u/${e.id}` },
      avatar(e, cls === 'first' ? 64 : 52), h('b', e.name), h('span', { class: 'row nowrap', style: { gap: '6px' } }, tierIcon(e.tier_key, 20), h('span', { class: 'faint' }, `Lv ${e.level}`)),
      time(e), e.studying_since ? h('span', { class: 'tag good' }, h('i', { class: 'studying-dot' }), 'studying') : null,
      h('div', { class: 'plinth' }, e.rank));
    const rest = es.slice(3).map((e) => h('a', { class: `lb-row ${e.me ? 'me-row' : ''}`, href: e.me ? '/me' : `/u/${e.id}`, style: { color: 'inherit' } },
      h('span', { class: 'rank num faint', style: { font: '700 .95rem var(--display)' } }, e.rank), avatar(e, 40),
      h('div', { class: 'nm' }, h('b', e.name), h('span', { class: 'faint' }, `Level ${e.level} · ${e.tier}`)),
      h('div', { class: 'row nowrap' }, e.studying_since ? h('i', { class: 'studying-dot', title: 'Studying now' }) : null, time(e))));
    const meOut = data.me.rank && data.me.rank > es.length;
    mount(body, h('div', { class: 'podium' }, spot(es[1], 'second'), spot(es[0], 'first'), spot(es[2], 'third')),
      rest.length ? h('div', { class: 'panel tight' }, rest) : null,
      meOut ? h('div', { class: 'panel tight pin accent row between' }, h('b', `Your rank: #${data.me.rank}`), h('span', { class: 'disp' }, dur(data.me.seconds))) : null,
      !data.me.rank ? h('p', { class: 'faint' }, 'You\'re not on this board yet. Study to claim a spot.') : null,
      h('p', { class: 'faint' }, `${num(data.total)} ranked · ${data.period_label}${data.subject ? ` · ${data.subject.label}` : ''}`));
  }
  async function load() {
    try { data = await get('/api/leaderboard', { period, subject }); paint(); } catch (e) { mount(body, errorBox(e, load)); }
  }
  mount(body, loadingPage(2)); await load();
  ctx.every(1000, () => body.querySelectorAll('[data-live="1"]').forEach((n) => { n.textContent = dur(Number(n.dataset.base) + Math.max(0, nowSec() - data.now)); }));
  ctx.every(30000, load); ctx.onData(load);
}
