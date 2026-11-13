import { h, get, mount, clock, dur, nowSec, ico, SUBJECTS, loadCss } from '/static/core/core.js';
import { avatar, pageHead, empty, errorBox, loadingPage, ring } from '/static/core/ui.js';

export default async function live(root, ctx) {
  loadCss('/static/views/stats.css');
  const who = h('div', { class: 'grid auto' }), rooms = h('div', { class: 'grid cols-2' });
  const sub = h('p');
  mount(root, pageHead('Live', 'Who is studying right now. Timers tick in real time, whether the session started here or in Discord.'),
    h('div', { class: 'stack lg' }, h('h2', 'Studying now'), who, h('h2', 'Pomodoro rooms'), rooms, sub));
  let people = [], pomo = [], cfg = null, at = 0;

  function paint() {
    people.length ? mount(who, people.map((p) => {
      const sc = p.subject ? SUBJECTS[p.subject.key].color : 'var(--accent)';
      return h('a', { class: `person-card ${p.me ? 'me' : ''}`, href: p.me ? '/me' : `/u/${p.id}`, style: { '--sc': sc, color: 'inherit', textDecoration: 'none' } },
        avatar(p, 44), h('div', { style: { minWidth: 0 } }, h('b', p.name), h('div', { class: 'faint' }, [p.subject?.label || 'General', p.channel].filter(Boolean).join(' · '))),
        h('span', { class: 't', dataset: { since: p.start_time } }, clock(nowSec() - p.start_time)));
    })) : mount(who, h('div', { style: { gridColumn: '1 / -1' } }, empty({ icon: 'focus_clock', title: 'Quiet right now', text: 'Nobody is in a session. Start one from Home and you\'ll show up here.' })));
    pomo.length ? mount(rooms, pomo.map((r) => {
      const frac = r.phase_duration ? 1 - (r.remaining - (nowSec() - at)) / r.phase_duration : 0;
      return h('div', { class: 'panel' }, h('div', { class: 'room' },
        ring(Math.max(0, Math.min(1, frac)), { size: 96, color: r.phase === 'focus' ? 'var(--accent)' : 'var(--good)' }, h('b', { class: 'disp num', dataset: { rem: r.remaining, at } }, clock(r.remaining).slice(3))),
        h('div', { class: 'stack' }, h('h3', r.channel), h('span', { class: `tag ${r.phase === 'focus' ? 'accent' : 'good'}` }, `${r.phase.replace('_', ' ')} · cycle ${r.cycles + 1}`),
          h('div', { class: 'row', style: { gap: '4px' } }, r.members.slice(0, 8).map((m) => avatar(m, 28)), r.members.length ? h('span', { class: 'faint' }, `${r.members.length} in room`) : null))));
    })) : mount(rooms, h('div', { style: { gridColumn: '1 / -1' } }, empty({ icon: 'pomodoro', title: 'No Pomodoro running',
      text: cfg ? `Join a voice channel and a ${cfg.focus}/${cfg.break} focus cycle starts for the whole room. After ${cfg.cycles} focus blocks you get a ${cfg.long_break} minute break.` : 'Join a voice channel to start a focus cycle for the room.' })));
  }
  async function load() {
    try {
      const [a, p, s] = await Promise.all([get('/api/active'), get('/api/pomodoro'), cfg ? null : get('/api/session')]);
      people = a.people; pomo = p.rooms; at = nowSec(); if (s) cfg = s.config.pomodoro; paint();
    } catch (e) { mount(who, errorBox(e, load)); }
  }
  mount(who, loadingPage(1)); await load();
  ctx.every(1000, () => {
    root.querySelectorAll('[data-since]').forEach((n) => { n.textContent = clock(nowSec() - Number(n.dataset.since)); });
    root.querySelectorAll('[data-rem]').forEach((n) => { n.textContent = clock(Math.max(0, Number(n.dataset.rem) - (nowSec() - Number(n.dataset.at)))).slice(3); });
  });
  ctx.every(15000, load); ctx.onData(load); ctx.on('live', (m) => { if (['session_started', 'session_ended', 'pomodoro_phase'].includes(m.kind)) load(); });
}
