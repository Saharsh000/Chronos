import { h, svg, get, post, mount, num, dur, ico, loadCss } from '/static/core/core.js';
import { pageHead, errorBox, loadingPage, act, toast, modal, tabs, bar, empty } from '/static/core/ui.js';
import { clean } from '/static/views/lib.js';

const hrs = (s) => (s === 0 ? 'Unlocked from the start' : `${dur(s)} of study`);

/** The Jack-o'-Lantern: one drawing, five carving stages (1 raw gourd … 5 the Great Pumpkin). */
function jack(stage) {
  const lit = stage >= 2, face = stage >= 3, haunted = stage >= 4, crown = stage >= 5;
  const g = svg('svg', { class: 'jack', viewBox: '0 0 200 200', role: 'img', 'aria-label': `Jack-o'-Lantern, carving stage ${stage} of 5` });
  const body = haunted ? '#c2410c' : '#e8730c';
  g.append(
    svg('ellipse', { cx: 100, cy: 124, rx: 78, ry: 62, fill: body }),
    svg('path', { d: 'M100 62 C60 70 40 110 46 150 M100 62 C140 70 160 110 154 150 M100 62 C84 80 80 120 86 184 M100 62 C116 80 120 120 114 184', stroke: 'rgba(0,0,0,.22)', 'stroke-width': 3, fill: 'none', 'stroke-linecap': 'round' }),
    svg('rect', { x: 92, y: 40, width: 16, height: 28, rx: 5, fill: '#4d6b2a' }));
  if (lit) {
    g.append(svg('g', { class: 'flame' }, svg('path', { d: 'M100 112 C86 130 90 150 100 156 C110 150 114 130 100 112Z', fill: '#ffd34d' }), svg('path', { d: 'M100 128 C94 138 96 148 100 152 C104 148 106 138 100 128Z', fill: '#fff4c2' })));
  }
  if (face) {
    const dark = lit ? '#2b0f00' : '#5b2a08';
    g.append(svg('path', { d: 'M62 96 L88 96 L75 74Z', fill: lit ? '#ffb02e' : dark }), svg('path', { d: 'M112 96 L138 96 L125 74Z', fill: lit ? '#ffb02e' : dark }),
      svg('path', { d: haunted ? 'M60 142 L74 160 L88 144 L100 164 L112 144 L126 160 L140 142 L128 134 L100 146 L72 134Z' : 'M64 138 Q100 176 136 138 Q100 156 64 138Z', fill: lit ? '#ffb02e' : dark }));
  }
  if (haunted) g.append(svg('path', { d: 'M40 100 L52 112 M160 100 L148 112', stroke: '#2b0f00', 'stroke-width': 4, 'stroke-linecap': 'round' }));
  if (crown) g.append(svg('path', { d: 'M62 46 L72 22 L88 38 L100 14 L112 38 L128 22 L138 46Z', fill: '#f5c518', stroke: '#a16207', 'stroke-width': 3, 'stroke-linejoin': 'round' }));
  return g;
}

const rewardRows = (r) => [
  r.candy ? h('div', ico('candy', 16), `${num(r.candy)} candy`) : null,
  r.coins ? h('div', ico('chronocoin', 16), `${num(r.coins)} coins`) : null,
  ...r.boxes.map((b) => h('div', ico('mystery_box', 16), `${b.qty} × ${b.name}`)),
  ...r.items.map((i) => h('div', ico(i.id === 'sugar_rush' ? 'sugar_rush' : 'mystery_box', 16), `${i.qty} × ${i.name}`)),
  r.title ? h('div', ico('title_scroll', 16), `Title: ${r.title}`) : null];

export default async function halloween(root, ctx) {
  loadCss('/static/views/economy.css'); loadCss('/static/views/halloween.css');
  let d = null, tab = 'pass';
  const head = h('div'), body = h('div', { class: 'stack hw' });
  mount(root, head, body);

  async function load() {
    try { d = await get('/api/halloween'); paint(); } catch (e) { mount(body, errorBox(e, load)); }
  }

  async function claim(btn) {
    await act(btn, async () => {
      const r = await post('/api/halloween/claim', {});
      const lines = [r.candy ? h('div', { class: 'l' }, ico('candy', 28), h('b', `+${num(r.candy)} candy`)) : null, r.coins ? h('div', { class: 'l' }, ico('chronocoin', 28), h('b', `+${num(r.coins)} coins`)) : null,
        ...r.boxes.map((b) => h('div', { class: 'l' }, ico('mystery_box', 28), h('b', `${b.qty} × ${b.name}`))), ...r.items.map((i) => h('div', { class: 'l' }, ico(i.id === 'sugar_rush' ? 'sugar_rush' : 'mystery_box', 28), h('b', `${i.qty} × ${i.name}`))),
        ...r.titles.map((t) => h('div', { class: 'l' }, ico('title_scroll', 28), h('b', `Title unlocked: ${t}`)))];
      modal({ title: r.from_level === r.new_claimed_level ? `Level ${r.new_claimed_level} claimed` : `Levels ${r.from_level} to ${r.new_claimed_level} claimed`, content: h('div', { class: 'reveal' }, h('div', { class: 'loot' }, lines)), actions: [{ label: 'Nice', kind: 'primary', value: true }] });
      await load();
    });
  }
  async function openBox(arg, btn) {
    await act(btn, async () => {
      const r = await post('/api/bag/open', arg);
      const body_ = r.openings.map((o) => h('div', { class: 'loot' }, h('div', { class: 'faint' }, `${o.box?.name || 'Mystery Box'}${o.quantity > 1 ? ` × ${o.quantity}` : ''}`),
        o.candy ? h('div', { class: 'l' }, ico('candy', 28), h('b', `+${num(o.candy)} candy`)) : null, o.coins ? h('div', { class: 'l' }, ico('chronocoin', 28), h('b', `+${num(o.coins)} coins`)) : null,
        ...(o.pets || []).map((p) => h('div', { class: 'l' }, ico('candy', 28), h('b', p.new_pet ? `New pet: ${p.name}` : `Duplicate ${p.name}`))),
        ...(o.food || []).map((f) => h('div', { class: 'l' }, ico(`food/${f.id}`, 28), h('b', `${f.qty} × ${f.name}`))), ...(o.items || []).map((i) => h('div', { class: 'l' }, ico('mystery_box', 28), h('b', `${i.qty} × ${i.name}`)))));
      modal({ title: 'Opened', content: h('div', { class: 'reveal' }, body_), actions: [{ label: 'Nice', kind: 'primary', value: true }] }); await load();
    });
  }
  async function buy(it, btn, qty = 1) {
    await act(btn, async () => {
      const r = await post('/api/halloween/buy', { item: it.id, quantity: qty });
      toast(it.type === 'pet' ? `${r.item.name} is yours.${r.auto_equipped ? ' Equipped as your active pet.' : ' Equip it from the Pets page.'}` : it.type === 'title' ? `Unlocked "${r.title_text}". Equip it from your Bag.` : `${r.quantity} × ${r.item.name} added to your Bag.`, { kind: 'good', title: 'Bought' });
      await load();
    });
  }

  function hero() {
    const p = d.pass, cur = p.current, nx = p.next;
    const frac = nx ? Math.max(0, Math.min(1, (p.study_seconds - cur.required_seconds) / Math.max(1, nx.required_seconds - cur.required_seconds))) : 1;
    const box = h('div', { class: 'hw-hero', style: { '--glow': String(0.15 + cur.stage * 0.17) } }, jack(cur.stage),
      h('div', { class: 'stack' }, h('div', h('h2', cur.stage_name), h('div', { class: 'mute' }, `${cur.level_name} · ${cur.desc}`)),
        h('div', { class: 'stats' }, h('div', h('b', `${p.level} / ${p.max_level}`), h('span', 'Pass level')), h('div', h('b', dur(p.study_seconds)), h('span', 'Halloween study')), h('div', h('b', ico('candy', 22), num(d.candy)), h('span', 'Candy'))),
        h('div', { class: 'stack', style: { gap: '6px' } }, bar(frac, { lg: true }),
          h('div', { class: 'faint' }, nx ? `${dur(Math.max(0, nx.required_seconds - p.study_seconds))} to go until level ${nx.level}, ${nx.level_name}.` : 'Pass complete. The Great Pumpkin approves.')),
        h('div', { class: 'row' }, p.unclaimed ? h('button', { class: 'btn primary', onClick: (e) => claim(e.currentTarget) }, p.unclaimed === 1 ? `Claim level ${p.claimed_level + 1}` : `Claim levels ${p.claimed_level + 1} to ${p.level}`) : h('button', { class: 'btn', disabled: true }, 'All unlocked rewards claimed'),
          nx ? h('span', { class: 'faint' }, 'Next: ', ...rewardRows(nx.rewards).filter(Boolean).slice(0, 3).map((n) => h('span', { style: { marginRight: '10px' } }, n.textContent))) : null)));
    return box;
  }

  const passTab = () => h('div', { class: 'stack' }, hero(), h('h2', 'Milestones'),
    h('div', { class: 'track' }, d.pass.levels.map((l) => h('div', { class: `lv ${l.status}` }, h('div', { class: 'n' }, `Lv. ${l.level}`, h('span', { class: `tag ${l.status === 'ready' ? 'accent' : l.status === 'claimed' ? 'good' : ''}` }, l.status === 'ready' ? 'Ready' : l.status === 'claimed' ? 'Claimed' : 'Locked')),
      h('div', { class: 'nm' }, l.level_name), h('div', { class: 'req' }, hrs(l.required_seconds)), h('div', { class: 'rw' }, rewardRows(l.rewards))))));

  const boxesTab = () => h('div', { class: 'stack' },
    h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('p', { class: 'mute' }, 'Hallo-Boxes open instantly. No timers.'),
      d.total_boxes ? h('button', { class: 'btn primary', onClick: (e) => openBox({ box: 'all', qty: 1 }, e.currentTarget) }, `Open all ${d.total_boxes}`) : null),
    h('div', { class: 'hw-boxes' }, d.boxes.map((b) => h('div', { class: 'hbox', style: { '--tc': b.color } }, ico('mystery_box', 48), h('b', b.name), h('div', { class: 'q' }, `×${num(b.qty)}`), h('div', { class: 'faint', style: { fontSize: '.8rem' } }, clean(b.desc).replace(' Opens instantly!', '')),
      h('div', { class: 'row' }, h('button', { class: 'btn', disabled: !b.qty, onClick: (e) => openBox({ box: b.id, qty: 1 }, e.currentTarget) }, 'Open one'), b.qty > 1 ? h('button', { class: 'btn', onClick: (e) => openBox({ box: b.id, qty: b.qty }, e.currentTarget) }, `All ${b.qty}`) : null)))),
    d.mystery_boxes ? h('div', { class: 'panel row', style: { justifyContent: 'space-between' } }, h('div', { class: 'row' }, ico('mystery_box', 40), h('div', h('b', 'Mystery Box'), h('div', { class: 'faint' }, `×${d.mystery_boxes} in your bag`))), h('button', { class: 'btn primary', onClick: (e) => openBox({ box: 'mystery', qty: 1 }, e.currentTarget) }, 'Open Mystery Box')) : null);

  const shopTab = () => h('div', { class: 'stack' }, h('p', { class: 'mute' }, 'Event-only. Candy comes from studying, daily rewards and every box.'),
    h('div', { class: 'hw-shop' }, d.shop.map((it) => {
      const hrsLeft = d.info.shop_hours[it.id];
      return h('div', { class: 'hw-item' }, h('div', { class: 'row' }, it.sprite ? h('img', { class: 'sprite', src: it.sprite, alt: '' }) : ico(it.type === 'boost' ? 'sugar_rush' : 'title_scroll', 48), h('div', h('b', it.name), h('div', { class: 'faint' }, `about ${dur(hrsLeft * 3600)} of study`))),
        h('p', { class: 'mute', style: { fontSize: '.9rem' } }, it.desc),
        h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('span', { class: 'price' }, ico('candy', 20), num(it.price)),
          it.owned ? h('span', { class: 'tag good' }, 'Owned') : h('button', { class: 'btn primary', disabled: !it.affordable, onClick: (e) => buy(it, e.currentTarget) }, it.affordable ? 'Buy' : `Need ${num(it.price - d.candy)} more`)),
        it.type === 'boost' && it.owned_qty ? h('span', { class: 'faint' }, `You own ${it.owned_qty}. Use it from your Bag for 2× XP for an hour.`) : null);
    })));

  const infoTab = () => {
    const i = d.info, hr = i.hourly;
    return h('div', { class: 'stack' },
      h('div', { class: 'panel stack' }, h('h2', 'Where boxes come from'), h('p', { class: 'mute' }, `Studying drops about ${hr.boxes.toFixed(1)} boxes an hour. Daily, work, beg, weekly and pass milestones add more.`),
        h('div', { class: 'odds' }, i.drop_table.map((t) => h('div', { class: 'o' }, h('span', t.name.replace(' Hallo-Box', '')), bar(t.chance, { color: t.color }), h('span', { class: 'faint' }, `${(t.chance * 100).toFixed(0)}%`)))),
        h('p', { class: 'faint' }, `A box averages about ${i.per_box.candy.toFixed(0)} candy and ${num(Math.round(i.per_box.coins))} coins. ${(i.per_box.pet * 100).toFixed(0)}% roll a pet, ${(i.per_box.food * 100).toFixed(0)}% roll food, ${(i.per_box.item * 100).toFixed(1)}% roll a boost or mystery box.`)),
      h('div', { class: 'panel stack' }, h('h2', 'The maths per hour of study'), h('div', { class: 'stat-strip' },
        h('div', h('b', `${hr.boxes.toFixed(1)}`), h('span', 'boxes')), h('div', h('b', `~${hr.candy_total.toFixed(0)}`), h('span', 'candy')), h('div', h('b', `~${num(Math.round(hr.coins_boxes))}`), h('span', 'coins from boxes'))),
        h('p', { class: 'mute' }, `Maxing the pass takes ${i.pace_hours.toFixed(0)} hours. That's about ${(i.pace_hours / 10).toFixed(1)} hours a day over the 10 days. The full pass pays ${num(i.totals.candy)} candy and ${num(i.totals.coins)} coins${i.totals.titles.length ? `, plus the "${i.totals.titles[0]}" title` : ''}.`)));
  };

  const TABS = [{ id: 'pass', label: 'Pass' }, { id: 'boxes', label: 'Boxes' }, { id: 'shop', label: 'Candy shop' }, { id: 'info', label: 'How it works' }];
  const tabsEl = tabs(TABS, tab, (id) => { tab = id; paintBody(); });
  function paintBody() { mount(body, tab === 'boxes' ? boxesTab() : tab === 'shop' ? shopTab() : tab === 'info' ? infoTab() : passTab()); }
  function paint() {
    mount(head, pageHead('Halloween', 'Carve your Jack-o\'-Lantern by studying, open boxes, spend candy before the event ends.',
      h('span', { class: 'wallet-bar' }, h('span', { class: 'big' }, ico('candy', 26), num(d.candy)))), tabsEl);
    paintBody();
  }
  mount(body, loadingPage(2)); await load();
  ctx.onData(load);
}
