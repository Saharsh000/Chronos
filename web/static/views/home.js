// Home: the Chrono dial (live session timer) + today at a glance.
import { state, h, svg, get, post, mount, clock, dur, num, nowSec, ico, tierIcon, SUBJECTS, on, fmtDate } from '/static/core/core.js';
import { avatar, coins, xpPill, bar, empty, errToast, act, modal, celebrate, pageHead, floatText } from '/static/core/ui.js';
import { refreshSession, refreshMe } from '/static/core/live.js';

const CX = 200, TICKS = 60;

function buildDial() {
  const ticks = Array.from({ length: TICKS }, (_, i) => {
    const a = (i / TICKS) * Math.PI * 2 - Math.PI / 2, major = i % 5 === 0;
    const r1 = major ? 168 : 176, r2 = 190;
    return svg('line', { class: 'tick', x1: CX + Math.cos(a) * r1, y1: CX + Math.sin(a) * r1, x2: CX + Math.cos(a) * r2, y2: CX + Math.sin(a) * r2 });
  });
  const R = 146, C = 2 * Math.PI * R;
  const arc = svg('circle', { class: 'arc', cx: CX, cy: CX, r: R, 'stroke-dasharray': C, 'stroke-dashoffset': C, transform: `rotate(-90 ${CX} ${CX})` });
  const digits = h('div', { class: 'digits num' });
  const sub = h('div', { class: 'sub' });
  const label = h('div', { class: 'sub', style: { fontWeight: 700, color: 'var(--c)' } });
  const el = h('div', { class: 'dial idle', role: 'timer', 'aria-label': 'Session timer' },
    svg('svg', { viewBox: '0 0 400 400', 'aria-hidden': 'true' }, ...ticks, svg('circle', { class: 'track', cx: CX, cy: CX, r: R }), arc),
    h('div', { class: 'face' }, label, digits, sub));
  const set = ({ text, frac, lit, subtext, labeltext, subject, active }) => {
    el.className = `dial ${active ? 'active' : 'idle'} ${subject || ''}`;
    if (digits.dataset.t !== text) {
      digits.dataset.t = text;
      digits.replaceChildren(...[...text].map((ch) => h('span', { class: ch === ':' ? 'c' + (active ? ' blink' : '') : 'd' }, ch)));
    }
    arc.style.strokeDashoffset = C * (1 - Math.max(0, Math.min(1, frac)));
    ticks.forEach((t, i) => t.classList.toggle('lit', i <= lit));
    sub.textContent = subtext || ''; label.textContent = labeltext || '';
  };
  return { el, set };
}

export default async function home(root, ctx) {
  let pick = null;   // subject override (null = auto from voice channel)
  let people = [], dash = null, rooms = [];
  const dial = buildDial();
  const side = h('div', { class: 'stack lg' });
  const strip = h('div'), lower = h('div', { class: 'grid cols-2' });

  const load = async () => {
    await refreshSession();
    const [a, d, p] = await Promise.all([get('/api/active').catch(() => ({ people: [] })), get('/api/dashboard').catch(() => null), get('/api/pomodoro').catch(() => ({ rooms: [] }))]);
    people = a.people; dash = d; rooms = p.rooms;
    paintSide(); paintLower(); tick();
  };

  function paintSide() {
    const S = state.session, sess = S.session, L = S.level;
    const effects = S.effects.map((e) => h('span', { class: 'tag accent' }, ico(e.id === 'xp_boost' ? 'xp_boost' : 'coin_boost', 16), `${e.label} ×${e.multiplier} · ${dur(e.remaining)} left`));
    if (!sess) {
      const subjBtns = [
        ...Object.entries(SUBJECTS).map(([k, v]) => h('button', { class: 'subj', type: 'button', 'aria-pressed': String(pick === k), style: { '--sc': v.color }, dataset: { k },
          onClick: () => { pick = pick === k ? null : k; side.querySelectorAll('.subj').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.k === pick))); } }, ico(v.icon, 32), v.label)),
      ];
      const start = h('button', { class: 'btn primary lg', onClick: (e) => act(e.currentTarget, async () => {
        await post('/api/session/start', { subject: pick || undefined }); await refreshSession(); await load();
      }) }, ico('focus_clock', 22), 'Start session');
      mount(side,
        h('div', h('h1', 'Lock in.'), h('p', { class: 'mute', style: { marginTop: '8px', maxWidth: '44ch' } },
          'Pick a subject and start. It posts to your Discord check-in channel exactly like a bot session, and the bot keeps crediting XP while you\'re away from this tab.')),
        h('div', { class: 'subject-pick' }, subjBtns),
        S.voice ? h('p', { class: 'faint' }, `You\'re in the voice room "${S.voice}" - the subject is picked from it unless you choose one.`) : h('p', { class: 'faint' }, 'No subject chosen: it\'s tagged General.'),
        h('div', { class: 'row' }, start, effects));
    } else {
      const xpNode = h('span', { class: 'pill' }, ico('chronos_xp', 26), h('span', { id: 'g-xp' }, num(sess.credited_xp)));
      const coinNode = h('span', { class: 'pill' }, ico('chronocoin', 26), h('span', { id: 'g-coin' }, num(sess.credited_coins)));
      const stop = h('button', { class: 'btn danger lg', onClick: (e) => act(e.currentTarget, () => stopSession()) }, 'Stop session');
      const checkin = sess.afk.pending ? h('button', { class: 'btn primary lg', onClick: (e) => act(e.currentTarget, async () => { await post('/api/session/checkin'); await refreshSession(); }) }, 'I\'m here') : null;
      mount(side,
        h('div', h('h1', sess.subject ? `${sess.subject.label} session` : 'Session running'),
          h('p', { class: 'mute', style: { marginTop: '8px' } }, sess.channel ? `In ${sess.channel}. ` : '', 'Safe to close this tab - the bot keeps tracking.')),
        h('div', { class: 'live-gain' }, xpNode, coinNode),
        h('div', { class: 'row' }, checkin, stop, effects));
    }
  }

  function paintLower() {
    const S = state.session, L = S.level;
    mount(strip, h('div', { class: 'stat-strip' },
      h('div', { class: 'stat' }, h('div', { class: 'v' }, dur(S.today_seconds + (S.session ? 0 : 0))), h('div', { class: 'l' }, 'Studied today')),
      h('div', { class: 'stat' }, h('div', { class: 'v' }, dash ? dur(dash.week_seconds) : '-'), h('div', { class: 'l' }, 'This week')),
      h('div', { class: 'stat' }, h('div', { class: 'v' }, `${S.streak.current}d`), h('div', { class: 'l' }, `Streak · best ${S.streak.longest}d`)),
      h('div', { class: 'stat' }, h('div', { class: 'v row nowrap', style: { gap: '8px' } }, tierIcon(L.tier_key, 28), `Lv ${L.level}`), h('div', { class: 'l' }, `${L.tier} · ${num(L.into)}/${num(L.needed)} XP`)),
      dash ? h('div', { class: 'stat' }, h('div', { class: 'v row nowrap', style: { gap: '8px' } }, ico('chronocoin', 26), num(dash.coins)), h('div', { class: 'l' }, 'Chronocoins')) : null));

    const who = h('div', { class: 'panel' }, h('div', { class: 'panel-head' }, h('h2', 'Studying now'), h('a', { href: '/live' }, 'See all')),
      people.length ? h('div', { class: 'list' }, people.slice(0, 6).map((p) => h('div', { class: p.me ? 'me-row' : '' }, avatar(p, 32), h('div', { class: 'grow' }, h('b', p.name), h('div', { class: 'faint' }, p.subject ? p.subject.label : 'General')),
        h('span', { class: 'num mute', dataset: { since: p.start_time } }, clock(nowSec() - p.start_time)))))
        : empty({ icon: 'focus_clock', title: 'Quiet right now', text: 'Nobody is in a session. Be the first.' }));

    const week = dash?.days?.length ? (() => {
      const max = Math.max(...dash.days.map((d) => d.seconds), 1);
      return h('div', { class: 'panel' }, h('div', { class: 'panel-head' }, h('h2', 'Last 7 days'), h('span', { class: 'faint' }, `${dur(dash.days.reduce((a, d) => a + d.seconds, 0))} total`)),
        h('div', { class: 'row nowrap', style: { alignItems: 'flex-end', gap: '10px', height: '150px' } }, dash.days.map((d) =>
          h('div', { style: { flex: 1, display: 'grid', gap: '6px', justifyItems: 'center', alignContent: 'end', height: '100%' }, title: `${fmtDate(d.ts)}: ${dur(d.seconds)}` },
            h('span', { class: 'faint num', style: { fontSize: '.72rem' } }, d.seconds ? dur(d.seconds) : ''),
            h('div', { style: { width: '100%', height: `${Math.max(4, (d.seconds / max) * 100)}px`, background: d.seconds ? 'var(--accent)' : 'var(--s3)', borderRadius: '6px' } }),
            h('span', { class: 'faint', style: { fontSize: '.74rem' } }, d.label)))));
    })() : null;

    const pomo = rooms.length ? h('div', { class: 'panel' }, h('h2', 'Pomodoro rooms'), h('div', { class: 'list' }, rooms.map((r) =>
      h('div', ico('pomodoro', 28), h('div', { class: 'grow' }, h('b', r.channel), h('div', { class: 'faint' }, `${r.members.length} in room · cycle ${r.cycles + 1}`)),
        h('span', { class: `tag ${r.phase === 'focus' ? 'accent' : 'good'}` }, `${r.phase.replace('_', ' ')} · ${dur(r.remaining)}`))))) : null;
    mount(lower, who, week || pomo, week ? pomo : null);
  }

  async function stopSession() {
    const out = await post('/api/session/stop'); const r = out.result;
    await Promise.all([refreshSession(), refreshMe(), load()]);
    const ach = r.achievements.map((a) => h('div', { class: 'row' }, ico('achievement_trophy', 22), h('span', `${a.name}`), a.reward_coins ? h('span', { class: 'tag good' }, `+${num(a.reward_coins)} coins`) : null));
    modal({ title: 'Session complete', content: h('div', { class: 'stack' },
      h('div', { class: 'stat-strip' }, h('div', { class: 'stat' }, h('div', { class: 'v' }, dur(r.duration)), h('div', { class: 'l' }, r.subject?.label || 'Focus time')),
        h('div', { class: 'stat' }, h('div', { class: 'v' }, `+${num(r.xp)}`), h('div', { class: 'l' }, 'XP')), h('div', { class: 'stat' }, h('div', { class: 'v' }, `+${num(r.coins)}`), h('div', { class: 'l' }, 'Chronocoins'))),
      r.streak_broken_from ? h('div', { class: 'err-box' }, `Your ${r.streak_broken_from}-day streak ended. A new one starts today.`) : h('p', { class: 'mute' }, `${r.streak}-day streak. Level ${r.level.level} · ${num(r.level.into)}/${num(r.level.needed)} XP.`),
      ach.length ? h('div', { class: 'stack' }, h('h3', 'Unlocked'), ach) : null),
      actions: [{ label: 'Done', kind: 'primary', value: true }],
      onClose: () => { if (r.leveled_up) celebrate({ title: `Level ${r.new_level}`, sub: `Welcome to ${r.tier}.`, tier: r.level.tier_key, tierName: r.tier }); } });
  }

  // ---- the ticking dial (client-side; server timestamps keep it honest)
  function tick() {
    const S = state.session; if (!S) return;
    const sess = S.session, L = S.level;
    if (!sess) {
      dial.set({ text: clock(S.today_seconds), frac: L.into / Math.max(1, L.needed), lit: -1, active: false, labeltext: 'today', subtext: `Level ${L.level} · ${num(L.into)}/${num(L.needed)} XP` });
    } else {
      const now = nowSec(), el = now - sess.start_time, subj = sess.subject?.key;
      let frac, subtext;
      if (sess.afk.pending) { const left = Math.max(0, sess.afk.deadline - now); frac = left / sess.afk.grace_seconds; subtext = `Confirm in ${clock(left).slice(3)}`; }
      else { const span = sess.next_checkin_at - sess.last_checkin, left = Math.max(0, sess.next_checkin_at - now); frac = 1 - left / Math.max(1, span); subtext = `Check-in in ${clock(left).slice(3)}`; }
      dial.set({ text: clock(el), frac, lit: el % 60, active: true, subject: subj, labeltext: sess.subject?.label || 'focus', subtext });
    }
    document.querySelectorAll('[data-since]').forEach((n) => { n.textContent = clock(nowSec() - Number(n.dataset.since)); });
  }

  mount(root,
    h('div', { class: 'dial-wrap' }, dial.el, side),
    strip, lower);
  await load();
  ctx.every(1000, tick); tick();
  ctx.on('session', () => { paintSide(); paintLower(); tick(); });
  ctx.on('live', (m) => {
    if (m.kind === 'progress') { const d = m.data; const g = document.getElementById('g-xp'); if (g) floatText(`+${d.xp} XP`, g); }
  });
  ctx.onData(load);
}
