import { h, get, mount, dur, num, state, ico, tierIcon, debounce, loadCss } from '/static/core/core.js';
import { avatar, tabs, pageHead, errorBox, loadingPage, empty, bar } from '/static/core/ui.js';

const fmt = { duration: dur, int: num, days: (v) => `${num(v)} day${v === 1 ? '' : 's'}`, coins: (v) => `${num(v)} coins` };

function picker(label, initial, onPick) {
  let current = initial;
  const shown = h('div', { class: 'row' });
  const input = h('input', { class: 'input', placeholder: 'Search members', 'aria-label': `${label}: search members`, autocomplete: 'off' });
  const results = h('div', { class: 'results hide' });
  const paintShown = () => mount(shown, current ? [avatar(current, 36), h('b', current.name)] : h('span', { class: 'faint' }, 'Nobody picked yet'));
  const search = debounce(async () => {
    const r = await get('/api/members', { q: input.value.trim(), limit: 8 }).catch(() => ({ members: [] }));
    mount(results, r.members.map((m) => h('button', { type: 'button', onClick: () => { current = m; paintShown(); results.classList.add('hide'); input.value = ''; onPick(m); } }, avatar(m, 28), m.name)));
    results.classList.toggle('hide', !r.members.length);
  }, 200);
  input.addEventListener('input', search); input.addEventListener('focus', search);
  input.addEventListener('blur', () => setTimeout(() => results.classList.add('hide'), 150));
  paintShown();
  const el = h('div', { class: 'panel tight stack' }, h('span', { class: 'faint' }, label), shown, h('div', { class: 'picker' }, input, results));
  el.set = (m) => { current = m; paintShown(); };
  return el;
}

export default async function compare(root, ctx) {
  loadCss('/static/views/stats.css');
  const me = state.me.user;
  let a = me, b = null, tab = ctx.query.tab || 'compare';
  const out = h('div', { class: 'stack lg' }), host = h('div', { class: 'stack lg' });
  const tabEl = tabs([{ id: 'compare', label: 'Head to head' }, { id: 'hof', label: 'Hall of fame' }], tab, (t) => { tab = t; show(); });
  mount(root, pageHead('Compare & fame', 'Stack yourself against anyone on the server, or see who holds the all-time records.'), tabEl, host);

  async function runCompare() {
    if (!b) return mount(out, empty({ icon: 'compass', title: 'Pick someone to compare with', text: 'Search for a member above. You\'ll see who wins each category.' }));
    mount(out, loadingPage(2));
    try {
      const d = await get('/api/compare', { a: a.id, b: b.id });
      const verdict = d.verdict === 'tie' ? `Dead even, ${d.wins.a} to ${d.wins.b}` : `${(d.verdict === 'a' ? d.a : d.b).name} wins ${Math.max(d.wins.a, d.wins.b)} to ${Math.min(d.wins.a, d.wins.b)}`;
      mount(out, h('div', { class: 'panel accent' },
        h('div', { class: 'vs' }, h('div', { class: 'row', style: { justifyContent: 'flex-end' } }, h('b', d.a.name), avatar(d.a, 52)), h('h2', 'vs'), h('div', { class: 'row' }, avatar(d.b, 52), h('b', d.b.name))),
        h('h2', { style: { textAlign: 'center' } }, verdict)),
        h('div', { class: 'panel' }, d.rows.map((r) => {
          const max = Math.max(r.a, r.b, 1);
          const side = (v, w, cls) => h('div', { class: `side ${cls} ${w ? 'win' : ''}` }, h('b', fmt[r.format](v)), bar(v / max, { color: w ? 'var(--accent)' : 'var(--faint)' }));
          return h('div', { class: 'vs-row' }, side(r.a, r.winner === 'a', 'a'), h('div', { class: 'lab' }, r.label), side(r.b, r.winner === 'b', 'b'));
        })));
    } catch (e) { mount(out, errorBox(e, runCompare)); }
  }

  async function hof() {
    mount(host, loadingPage(2));
    try {
      const d = await get('/api/halloffame');
      mount(host, h('div', { class: 'hof' }, d.records.map((r) => h('div', { class: 'rec' }, h('span', { class: 'mute' }, r.label),
        r.holder ? h('div', { class: 'row' }, avatar(r.holder, 40), h('div', h('b', r.holder.name), h('div', { class: 'v' }, fmt[r.format](r.value)))) : h('span', { class: 'faint' }, 'No record yet')))),
        h('div', { class: 'panel' }, h('div', { class: 'panel-head' }, h('h2', 'Top 3 daily perks'), ico('rank_crown', 32)),
          h('p', { class: 'mute' }, 'The three people with the most all-time study time get a perk on their first action of each day (resets at midnight IST). It works the same on the website and in Discord.'),
          d.top3.length ? h('div', { class: 'list' }, d.top3.map((t) => h('div', h('span', { class: 'rank' }, t.rank), avatar(t.holder, 36),
            h('div', { class: 'grow' }, h('b', t.holder.name), h('div', { class: 'faint' }, `${t.perk} · ${t.boost}`)), h('span', { class: 'tag' }, `+${t.coins} coins · ${t.item}`)))) : null));
    } catch (e) { mount(host, errorBox(e, hof)); }
  }

  function show() {
    if (tab === 'hof') return hof();
    const pa = picker('First person', me, (m) => { a = m; runCompare(); }), pb = picker('Second person', null, (m) => { b = m; runCompare(); });
    mount(host, h('div', { class: 'grid cols-2' }, pa, pb), out);
    runCompare();
  }
  if (ctx.query.b) { const r = await get('/api/members', { q: ctx.query.b, limit: 1 }).catch(() => null); b = r?.members?.[0] || null; }
  show();
}
