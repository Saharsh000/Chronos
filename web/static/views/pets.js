import { h, get, post, mount, num, ico, loadCss } from '/static/core/core.js';
import { pageHead, errorBox, loadingPage, act, toast, modal, askText, empty, tabs, chips, bar, floatText, avatar } from '/static/core/ui.js';

const sprite = (stage, size = 64, cls = '') => h('img', { class: `sprite ${cls}`, src: stage.sprite, width: size, height: size, alt: stage.name, loading: 'lazy' });
const coinPrice = (n, cls = 'price') => h('span', { class: cls }, ico('chronocoin', 18), num(n));

function stepper(get_, set_, max = 1000) {
  const out = h('span', {}, String(get_()));
  const upd = (v) => { v = Math.max(1, Math.min(max, v)); set_(v); out.textContent = v; };
  return Object.assign(h('div', { class: 'mini-stepper' }, h('button', { type: 'button', 'aria-label': 'One fewer', onClick: () => upd(get_() - 1) }, '−'), out,
    h('button', { type: 'button', 'aria-label': 'One more', onClick: () => upd(get_() + 1) }, '+')), { clamp: (m) => { if (get_() > m) upd(Math.max(1, m)); } });
}

export default async function pets(root, ctx) {
  loadCss('/static/views/economy.css'); loadCss('/static/views/pets.css');
  const viewing = ctx.params?.id || ctx.query?.user || null;
  let tab = ctx.query?.tab || 'mine', sel = null, shopTier = null, foodTier = 'snack';
  let d = null, shop = null, fshop = null;
  const qtyFeed = {}, qtyBuy = {};
  const head = h('div'), body = h('div', { class: 'stack' });
  mount(root, head, body);

  async function load() {
    try {
      d = await get('/api/pets', viewing ? { user: viewing } : {});
      if (!sel || !d.pets.some((p) => p.species_id === sel)) sel = (d.pets.find((p) => p.equipped) || d.pets[0])?.species_id || null;
      if (tab === 'pets' && !shop) shop = await get('/api/pets/shop');
      if (tab === 'food' && !fshop) fshop = await get('/api/pets/foodshop');
      paint();
    } catch (e) { mount(body, errorBox(e, load)); }
  }
  const refreshShops = async () => { shop = null; fshop = null; await load(); };
  const pet = () => d.pets.find((p) => p.species_id === sel);

  // ---------------------------------------------------------------- actions
  const evolveModal = (r) => modal({ title: `${r.nickname} evolved`, content: h('div', { class: 'stack', style: { justifyItems: 'center', textAlign: 'center' } },
    h('div', { class: 'evo-modal' }, h('div', sprite(r.old_stage, 96)), h('div', { class: 'arrow' }, '→'), h('div', { class: 'new' }, sprite(r.new_stage, 96))),
    h('b', `${r.old_stage.name} to ${r.new_stage.name}`), h('span', { class: 'mute' }, `Now level ${r.new_level}.`)), actions: [{ label: 'Nice', kind: 'primary', value: true }] });

  async function feed(f, btn) {
    await act(btn, async () => {
      const q = qtyFeed[f.id] || 1;
      const r = await post('/api/pets/feed', { food: f.id, quantity: q });
      const img = root.querySelector('.hero-pet .stage img'); img?.classList.remove('munch'); void img?.offsetWidth; img?.classList.add('munch');
      floatText(`+${num(r.xp_gained)} XP`, img || btn);
      qtyFeed[f.id] = 1;
      if (r.evolved) evolveModal(r); else if (r.leveled_up) toast(`${r.nickname} is now level ${r.new_level}.`, { kind: 'good', title: 'Level up' });
      await load();
    });
  }
  async function sell(f, btn) {
    await act(btn, async () => {
      const r = await post('/api/pets/food/sell', { food: f.id, quantity: qtyFeed[f.id] || 1 });
      toast(`Sold ${r.qty} × ${r.food.name} for ${num(r.refund)} coins.`, { kind: 'good', title: 'Sold' }); qtyFeed[f.id] = 1; await load();
    });
  }
  async function equip(p, btn) { await act(btn, async () => { await post('/api/pets/equip', { species: p.species_id }); toast(`${p.nickname} is now your active pet. It earns XP while you study.`, { kind: 'good', title: 'Equipped' }); await load(); }); }
  async function rename(p) {
    const name = await askText('Rename pet', { label: `New nickname for ${p.default_name} (32 characters max)`, value: p.nickname, max: 32, confirm: 'Rename' });
    if (!name) return;
    try { await post('/api/pets/nickname', { species: p.species_id, nickname: name }); toast(`${p.nickname} is now called ${name}.`, { kind: 'good', title: 'Renamed' }); await load(); } catch (e) { toast(e.message, { kind: 'bad' }); }
  }
  async function buyPet(sp, btn) {
    await act(btn, async () => {
      const r = await post('/api/pets/buy', { species: sp.species_id });
      toast(`${r.name} the ${r.archetype} is yours.${r.auto_equipped ? ' Equipped automatically, since it\'s your first pet.' : ''}`, { kind: 'good', title: 'Pet unlocked' });
      shop = null; tab = 'mine'; sel = sp.species_id; tabsEl.select?.('mine'); await load();
    });
  }
  async function buyFood(f, btn) {
    await act(btn, async () => {
      const r = await post('/api/pets/food/buy', { food: f.id, quantity: qtyBuy[f.id] || 1 });
      toast(`${r.qty} × ${r.food.name} for ${num(r.total_price)} coins. You have ${num(r.food.owned)}.`, { kind: 'good', title: 'Bought' });
      qtyBuy[f.id] = 1; fshop = null; await load();
    });
  }

  // ---------------------------------------------------------------- views
  function heroPet(p) {
    const tc = p.tier.color;
    const nodes = p.stages.map((s) => h('div', { class: `node ${p.level >= s.level ? 'reached' : ''} ${s.name === p.stage.name ? 'current' : ''}` }, sprite(s, 56), h('b', s.name), h('span', `Lv. ${s.level}`)));
    const nx = p.next_stage;
    return h('div', { class: 'hero-pet', style: { '--tc': tc } },
      h('div', { class: 'stage' }, sprite(p.stage, 160)),
      h('div', { class: 'stack', style: { gap: '4px' } },
        h('h2', p.nickname, p.equipped ? h('span', { class: 'tag good' }, 'Equipped') : null, h('span', { class: 'tag tier-tag' }, p.tier.label)),
        h('div', { class: 'mute' }, `${p.stage.name} · ${p.stage.badge_label} · ${p.archetype}`), p.desc ? h('div', { class: 'faint' }, p.desc) : null),
      h('div', { class: 'xp-line' }, h('div', { class: 'nums' }, h('b', `Level ${p.level}`), h('span', `${num(p.xp_into)} / ${num(p.xp_needed)} XP`)), bar(p.xp_into / p.xp_needed, { color: tc, lg: true }),
        h('div', { class: 'faint' }, nx ? `Next evolution: ${nx.name} at level ${nx.level}.` : 'Fully evolved.')),
      p.stages.length > 1 ? h('div', { class: 'evo', 'aria-label': 'Evolution line' }, nodes) : null,
      d.me ? h('div', { class: 'row' }, p.equipped ? null : h('button', { class: 'btn primary', onClick: (e) => equip(p, e.currentTarget) }, 'Equip'), h('button', { class: 'btn', onClick: () => rename(p) }, 'Rename')) : null);
  }

  function feedPanel() {
    const eq = d.pets.find((p) => p.equipped);
    return h('div', { class: 'panel stack' }, h('div', { class: 'panel-head' }, h('h2', 'Feed'), eq ? h('span', { class: 'faint' }, `Goes to ${eq.nickname}`) : null),
      !eq ? h('div', { class: 'lock-note' }, 'No pet equipped. Equip one to feed it.') : null,
      d.food.length ? h('div', { class: 'feed-list' }, d.food.map((f) => {
        qtyFeed[f.id] ||= 1;
        const st = stepper(() => qtyFeed[f.id], (v) => { qtyFeed[f.id] = v; }, f.owned);
        return h('div', { class: 'feed-row' }, ico(`food/${f.id}`, 40),
          h('div', h('b', f.name), h('div', { class: 'faint' }, `+${num(f.xp)} XP each · you have ${num(f.owned)}`)),
          d.me ? h('div', { class: 'acts' }, st, h('button', { class: 'btn primary', disabled: !eq, onClick: (e) => feed(f, e.currentTarget) }, 'Feed'),
            h('button', { class: 'btn', title: `Sell for ${num(f.sell)} coins each`, onClick: (e) => sell(f, e.currentTarget) }, `Sell ${num(f.sell)}`)) : null);
      })) : empty({ icon: 'food/cookies', title: 'No food yet', text: 'Buy some in the Food shop.', action: h('button', { class: 'btn primary', onClick: () => tabsEl.select('food') }, 'Open food shop') }));
  }

  function mine() {
    if (!d.pets.length) return empty({ icon: 'candy', title: d.me ? 'No pets yet' : `${d.user.name} has no pets`, text: d.me ? `Pets unlock at level ${d.unlock_level}. Pick one from the Pet shop.` : '',
      action: d.me ? h('button', { class: 'btn primary', onClick: () => tabsEl.select('pets') }, 'Browse pets') : null });
    const p = pet();
    return h('div', { class: 'stack' }, h('div', { class: 'den' }, heroPet(p), d.me ? feedPanel() : h('div')),
      h('div', { class: 'collection', role: 'list' }, d.pets.map((x) => h('button', { class: 'pcard', type: 'button', role: 'listitem', style: { '--tc': x.tier.color }, 'aria-pressed': String(x.species_id === sel), onClick: () => { sel = x.species_id; paint(); } },
        x.equipped ? h('span', { class: 'star tag good' }, 'Active') : null, sprite(x.stage, 64), h('b', x.nickname), h('span', `Lv. ${x.level}`)))));
  }

  function petShop() {
    if (!shop) return loadingPage(2);
    shopTier ||= shop.tiers[0].key;
    const t = shop.tiers.find((x) => x.key === shopTier);
    return h('div', { class: 'stack' },
      !shop.can_buy ? h('div', { class: 'lock-note' }, `You need to be level ${shop.unlock_level} to buy a pet. You're level ${shop.level}.`) : null,
      chips(shop.tiers.map((x) => ({ id: x.key, label: `${x.label} · ${num(x.pets.length)}` })), shopTier, (id) => { shopTier = id; paint(); }),
      h('div', { class: 'pet-shop' }, t.pets.map((sp) => {
        const ok = shop.can_buy && sp.affordable && !sp.owned;
        return h('div', { class: 'sp', style: { '--tc': t.color } },
          h('div', { class: 'previews' }, sp.stages.filter((s) => s.badge !== 'mega').map((s) => sprite(s, 56))),
          h('div', h('b', sp.name), h('span', { class: 'faint' }, ` the ${sp.archetype}`)), h('p', { class: 'mute', style: { fontSize: '.9rem' } }, sp.desc),
          h('div', { class: 'row', style: { justifyContent: 'space-between' } }, coinPrice(sp.price),
            sp.owned ? h('span', { class: 'tag good' }, 'Owned') : h('button', { class: 'btn primary', disabled: !ok, onClick: (e) => buyPet(sp, e.currentTarget) }, !shop.can_buy ? `Level ${shop.unlock_level} needed` : sp.affordable ? 'Buy' : `Need ${num(sp.price - shop.coins)} more`)));
      })));
  }

  function foodShop() {
    if (!fshop) return loadingPage(2);
    const t = fshop.tiers.find((x) => x.key === foodTier) || fshop.tiers[0];
    return h('div', { class: 'stack' },
      chips(fshop.tiers.map((x) => ({ id: x.key, label: x.label })), t.key, (id) => { foodTier = id; paint(); }),
      h('div', { class: 'food-grid' }, t.foods.map((f) => {
        qtyBuy[f.id] ||= 1;
        const st = stepper(() => qtyBuy[f.id], (v) => { qtyBuy[f.id] = v; });
        return h('div', { class: 'fd' }, h('div', { class: 'top' }, ico(`food/${f.id}`, 44), h('div', h('b', f.name), h('div', { class: 'faint' }, `+${num(f.xp)} pet XP`))),
          h('div', { class: 'row', style: { justifyContent: 'space-between', width: '100%' } }, coinPrice(f.cost), f.owned ? h('span', { class: 'tag' }, `${num(f.owned)} owned`) : null),
          d.me ? h('div', { class: 'row' }, st, h('button', { class: 'btn primary', disabled: f.cost > fshop.coins, onClick: (e) => buyFood(f, e.currentTarget) }, 'Buy')) : null);
      })));
  }

  const TABS = [{ id: 'mine', label: 'My pets' }, { id: 'pets', label: 'Pet shop' }, { id: 'food', label: 'Food shop' }];
  const tabsEl = tabs(viewing ? TABS.slice(0, 1) : TABS, tab, async (id) => { tab = id; if (id === 'pets' && !shop) shop = await get('/api/pets/shop').catch(() => null); if (id === 'food' && !fshop) fshop = await get('/api/pets/foodshop').catch(() => null); paint(); });
  function paint() {
    mount(head, pageHead(d.me ? 'Pets' : `${d.user.name}'s pets`, d.me ? 'Your equipped pet earns XP while you study. Feed it to level it up and evolve it.' : 'Read-only view.',
      h('span', { class: 'wallet-bar' }, h('span', { class: 'big' }, ico('chronocoin', 26), num(d.coins)))), viewing ? null : tabsEl);
    mount(body, tab === 'pets' ? petShop() : tab === 'food' ? foodShop() : mine());
  }

  mount(body, loadingPage(2)); await load();
  ctx.onData(async () => { if (tab === 'mine') await load(); });
}
