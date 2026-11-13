import { h, get, mount, num, fmtDate, ico, debounce, loadCss } from '/static/core/core.js';
import { tabs, chips, pageHead, errorBox, loadingPage, ring, empty, avatar } from '/static/core/ui.js';

export default async function achievements(root, ctx) {
  loadCss('/static/views/stats.css');
  const uid = ctx.query.user || '';
  let data, cat = 'All', filter = 'all', q = '';
  const head = h('div'), tabsHost = h('div'), grid = h('div', { class: 'ach-grid' });
  const search = h('input', { class: 'input', type: 'search', placeholder: 'Search achievements', 'aria-label': 'Search', style: { maxWidth: '280px' }, onInput: debounce((e) => { q = e.target.value.trim().toLowerCase(); paint(); }, 120) });
  const state = chips([['all', 'All'], ['unlocked', 'Unlocked'], ['locked', 'Locked']].map(([id, label]) => ({ id, label })), filter, (f) => { filter = f; paint(); });
  mount(root, head, h('div', { class: 'stack' }, tabsHost, h('div', { class: 'row between' }, state, search)), grid);

  function paint() {
    const f = data.categories.filter((c) => cat === 'All' || c.name === cat).flatMap((c) => c.items.map((i) => ({ ...i, cat: c.name })))
      .filter((i) => (filter === 'all' || (filter === 'unlocked') === i.unlocked) && (!q || `${i.name} ${i.description}`.toLowerCase().includes(q)));
    f.sort((a, b) => Number(b.unlocked) - Number(a.unlocked) || (b.unlocked_at || 0) - (a.unlocked_at || 0));
    mount(grid, f.length ? f.map((i) => h('div', { class: `ach ${i.unlocked ? '' : 'locked'}` }, h('span', { class: 'em', 'aria-hidden': 'true' }, i.emoji),
      h('b', i.name), h('span', { class: 'mute' }, i.description),
      h('div', { class: 'row' }, i.unlocked ? h('span', { class: 'tag good' }, `Unlocked ${fmtDate(i.unlocked_at)}`) : h('span', { class: 'tag' }, 'Locked'),
        i.reward_coins ? h('span', { class: 'pill' }, ico('chronocoin', 16), `+${num(i.reward_coins)}`) : null, cat === 'All' ? h('span', { class: 'faint' }, i.cat) : null)))
      : h('div', { style: { gridColumn: '1 / -1' } }, empty({ icon: 'achievement_trophy', title: 'No matches', text: 'Try another category or clear the search.' })));
  }
  async function load() {
    try {
      data = await get('/api/achievements', { user: uid });
      const pct = data.total ? data.unlocked / data.total : 0;
      mount(head, pageHead(uid ? `${data.user.name}'s achievements` : 'Achievements', 'Every badge pays out Chronocoins once, the moment you earn it.',
        h('div', { class: 'row' }, ring(pct, { size: 84 }, h('b', { class: 'disp' }, `${Math.round(pct * 100)}%`)), h('div', h('b', `${data.unlocked} / ${data.total}`), h('div', { class: 'faint' }, 'unlocked')))));
      tabsHost.replaceChildren(tabs([{ id: 'All', label: `All ${data.unlocked}` }, ...data.categories.map((c) => ({ id: c.name, label: `${c.name} ${c.unlocked}/${c.total}` }))], cat, (c) => { cat = c; paint(); }));
      paint();
    } catch (e) { mount(root, errorBox(e, () => { mount(root, head, tabsHost, grid); load(); })); }
  }
  mount(grid, loadingPage(2)); await load(); ctx.onData(load);
}
