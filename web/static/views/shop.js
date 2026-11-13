import { h, get, post, mount, num, ico, loadCss } from '/static/core/core.js';
import { clean } from '/static/views/lib.js';
import { pageHead, errorBox, loadingPage, act, toast, tabs, empty } from '/static/core/ui.js';

const CATS = [
  { id: 'all', label: 'Everything' },
  { id: 'boost', label: 'Boosts' },
  { id: 'consumable', label: 'Consumables' },
  { id: 'title', label: 'Titles' },
];

export default async function shop(root, ctx) {
  loadCss('/static/views/economy.css');
  let d = null, cat = 'all';
  const qty = {};                       // item id -> quantity in the stepper
  const head = h('div'), grid = h('div', { class: 'shop-grid' });
  mount(root, head, grid);

  async function load() {
    try { d = await get('/api/shop'); paint(); } catch (e) { mount(grid, errorBox(e, load)); }
  }

  async function buy(it, btn) {
    await act(btn, async () => {
      const q = it.type === 'title' ? 1 : qty[it.id] || 1;
      const r = await post('/api/shop/buy', { item: it.id, quantity: q });
      toast(`${r.quantity > 1 ? `${r.quantity} × ` : ''}${r.item.name} for ${num(r.total_price)} coins. You now have ${num(r.owned_qty)}.`, { kind: 'good', title: 'Bought', icon: it.icon });
      qty[it.id] = 1;
      await load();
    });
  }
  async function equip(it, btn) {
    await act(btn, async () => {
      const r = await post('/api/bag/title', { title: it.equipped ? null : it.title_text });
      toast(r.equipped_title ? `Now showing "${r.equipped_title}" on your profile.` : 'Title removed.', { kind: 'good' });
      await load();
    });
  }

  function stepper(it) {
    const input = h('input', { type: 'number', min: 1, max: 1000, value: qty[it.id] || 1, 'aria-label': `Quantity of ${it.name}`, inputmode: 'numeric' });
    const set = (v) => { v = Math.max(1, Math.min(1000, Math.floor(Number(v) || 1))); qty[it.id] = v; input.value = v; refresh(); };
    const total = h('span', { class: 'price' });
    const btn = h('button', { class: 'btn primary', onClick: (e) => buy(it, e.currentTarget) });
    function refresh() {
      const q = qty[it.id] || 1, cost = q * it.price, ok = cost <= d.coins;
      total.replaceChildren(ico('chronocoin', 20), num(cost));
      btn.disabled = !ok; btn.textContent = ok ? 'Buy' : `Need ${num(cost - d.coins)} more`;
    }
    input.addEventListener('input', () => set(input.value));
    const el = h('div', { class: 'row', style: { justifyContent: 'space-between' } },
      h('div', { class: 'stepper' },
        h('button', { type: 'button', 'aria-label': 'One fewer', onClick: () => set((qty[it.id] || 1) - 1) }, '−'), input,
        h('button', { type: 'button', 'aria-label': 'One more', onClick: () => set((qty[it.id] || 1) + 1) }, '+')),
      total);
    refresh();
    return h('div', { class: 'stack', style: { gap: '10px' } }, el, btn);
  }

  function titleAction(it) {
    if (it.owned) {
      return h('button', { class: `btn ${it.equipped ? '' : 'primary'}`, onClick: (e) => equip(it, e.currentTarget) }, it.equipped ? 'Unequip' : 'Equip');
    }
    const ok = it.price <= d.coins;
    return h('div', { class: 'stack', style: { gap: '10px' } },
      h('span', { class: 'price' }, ico('chronocoin', 20), num(it.price)),
      h('button', { class: 'btn primary', disabled: !ok, onClick: (e) => buy(it, e.currentTarget) }, ok ? 'Buy title' : `Need ${num(it.price - d.coins)} more`));
  }

  function item(it) {
    const meta = it.type === 'boost' ? `${it.multiplier}× for ${it.duration_minutes} min` : null;
    return h('div', { class: `sitem ${it.type === 'title' ? 'title' : ''}` },
      h('div', { class: 'top' }, ico(it.icon, 48),
        h('div', h('b', it.name), it.title_text && !it.name.endsWith(it.title_text) ? h('div', { class: 'tag accent', style: { marginTop: '4px' } }, it.title_text) : null,
          meta ? h('div', { class: 'faint' }, meta) : null)),
      h('p', { class: 'mute', style: { fontSize: '.9rem' } }, clean(it.desc)),
      it.type !== 'title' && it.owned_qty ? h('span', { class: 'faint' }, `You own ${num(it.owned_qty)}`) : null,
      it.server_role ? h('span', { class: 'faint' }, 'Server exclusive') : null,
      it.type === 'title' ? titleAction(it) : stepper(it));
  }

  function paint() {
    const switcher = tabs(CATS, cat, (id) => { cat = id; paintGrid(); });
    mount(head, pageHead('Shop', 'Spend Chronocoins on boosts, boxes and profile titles. Purchases land in your Bag, same as buying in Discord.',
      h('span', { class: 'wallet-bar' }, h('span', { class: 'big' }, ico('chronocoin', 30), num(d.coins)))), switcher);
    paintGrid();
  }
  function paintGrid() {
    const items = d.items.filter((i) => cat === 'all' || i.type === cat);
    mount(grid, items.length ? items.map(item) : empty({ icon: 'mystery_box', title: 'Nothing in this section', text: 'Try another category.' }));
  }

  mount(grid, loadingPage(2)); await load();
  ctx.onData(load);
}
