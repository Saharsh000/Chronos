import { h, get, post, mount, clock, num, nowSec, ico, loadCss } from '/static/core/core.js';
import { clean } from '/static/views/lib.js';
import { pageHead, errorBox, loadingPage, act, toast, modal, empty, avatar } from '/static/core/ui.js';

const lootLine = (icon, text, sub) => h('div', { class: 'l' }, typeof icon === 'string' ? ico(icon, 28) : icon, h('div', h('b', text), sub ? h('div', { class: 'faint' }, sub) : null));

function openingBody(o) {
  if (o.kind === 'mystery') {
    const r = o.reward;
    const line = r.kind === 'coins' ? lootLine('chronocoin', `+${num(r.amount)} coins`)
      : r.kind === 'xp' ? lootLine('chronos_xp', `+${num(r.amount)} XP`)
      : lootLine(r.item_id?.includes('xp') ? 'xp_boost' : r.item_id?.includes('coin') ? 'coin_boost' : 'streak_freeze', `${r.qty} × ${r.name}`);
    return h('div', { class: 'loot' }, line, o.leveled_up ? lootLine('rank_crown', `Level up: ${o.old_level} to ${o.new_level}`) : null);
  }
  return h('div', { class: 'loot' },
    h('div', { class: 'faint' }, `${o.box.name} × ${o.quantity}`),
    o.candy ? lootLine('candy', `+${num(o.candy)} candy`) : null,
    o.coins ? lootLine('chronocoin', `+${num(o.coins)} coins`) : null,
    ...o.pets.map((p) => lootLine('pets', p.new_pet ? `New pet: ${p.name}` : `Duplicate ${p.name}`, p.new_pet ? 'Find it on the Pets page.' : `+${num(p.pet_xp_bonus)} pet XP, +${num(p.coin_bonus)} coins instead`)),
    ...o.food.map((f) => lootLine(`food/${f.id}`, `${f.qty} × ${f.name}`)),
    ...o.items.map((i) => lootLine('mystery_box', `${i.qty} × ${i.name}`)));
}

export default async function bag(root, ctx) {
  loadCss('/static/views/economy.css');
  const viewing = ctx.params?.id || ctx.query?.user || null;
  let d = null, sel = null;
  const head = h('div'), boosts = h('div', { class: 'stack' }), body = h('div', { class: 'stack' });
  mount(root, head, boosts, body);

  async function load() {
    try { d = await get('/api/bag', viewing ? { user: viewing } : {}); paint(); } catch (e) { mount(body, errorBox(e, load)); }
  }
  const left = (e) => Math.max(0, e.expires_at - nowSec());

  async function openBox(arg, btn) {
    await act(btn, async () => {
      const chest = document.querySelector('.chest'); chest?.classList.add('opening');
      await new Promise((r) => setTimeout(r, chest ? 600 : 0));
      const r = await post('/api/bag/open', arg);
      modal({ title: r.openings.length > 1 ? 'Everything opened' : 'Opened', content: h('div', { class: 'reveal' }, ...r.openings.map(openingBody), r.achievements.length ? h('div', { class: 'extra' }, h('b', 'Achievement unlocked')) : null), actions: [{ label: 'Nice', kind: 'primary', value: true }] });
      sel = null; await load();
    });
  }
  async function useBoost(it, btn) {
    await act(btn, async () => {
      const r = await post('/api/bag/use', { item: it.id });
      toast(`${r.multiplier}× for ${r.duration_minutes} minutes. Anything you earn while it runs counts.`, { kind: 'good', title: `${r.item.name} active` });
      await load();
    });
  }
  async function setTitle(text, btn) {
    await act(btn, async () => {
      const r = await post('/api/bag/title', { title: text });
      toast(r.equipped_title ? `Showing "${r.equipped_title}" on your profile.` : 'Title removed.', { kind: 'good' }); await load();
    });
  }

  function detail(it) {
    if (!it) return h('div', { class: 'panel faint' }, 'Pick an item to see what it does.');
    const actions = [];
    if (d.me && it.usable) actions.push(h('button', { class: 'btn primary', onClick: (e) => useBoost(it, e.currentTarget) }, 'Use boost'));
    if (d.me && it.openable) actions.push(h('button', { class: 'btn primary', onClick: (e) => openBox({ box: it.tier || it.id, qty: 1 }, e.currentTarget) }, 'Open one'),
      it.qty > 1 ? h('button', { class: 'btn', onClick: (e) => openBox({ box: it.tier || it.id, qty: it.qty }, e.currentTarget) }, `Open all ${it.qty}`) : null);
    if (d.me && it.id === 'mystery_box') actions.push(h('button', { class: 'btn primary', onClick: (e) => openBox({ box: 'mystery', qty: 1 }, e.currentTarget) }, 'Open Mystery Box'));
    if (d.me && it.feedable) actions.push(h('a', { class: 'btn', href: '/pets', onClick: (e) => { e.preventDefault(); ctx.navigate('/pets'); } }, 'Feed a pet'));
    return h('div', { class: 'panel stack' }, h('div', { class: 'row' }, h('span', { class: `chest ${it.openable || it.id === 'mystery_box' ? '' : ''}` }, ico(it.icon, 64)),
      h('div', h('h2', it.name), h('div', { class: 'faint' }, `${it.kind} · you have ${num(it.qty)}`))),
      it.desc ? h('p', { class: 'mute' }, clean(it.desc)) : null, h('div', { class: 'row' }, actions));
  }

  function paint() {
    const boxCount = d.items.filter((i) => i.openable).reduce((s, i) => s + i.qty, 0);
    mount(head, pageHead(d.me ? 'Bag' : `${d.user.name}'s bag`, d.me ? 'Everything you own. Boosts and boxes work the same as in Discord.' : 'Read-only view.',
      d.me && boxCount > 1 ? h('button', { class: 'btn', onClick: (e) => openBox({ box: 'all', qty: 1 }, e.currentTarget) }, `Open all ${boxCount} Hallo-Boxes`) : null,
      h('span', { class: 'wallet-bar' }, h('span', { class: 'big' }, ico('chronocoin', 26), num(d.coins)), h('span', { class: 'big' }, ico('candy', 26), num(d.candy)))));
    mount(boosts, d.effects.map((e) => h('div', { class: 'boost' }, ico(e.id, 40), h('div', h('b', e.label), h('div', { class: 'faint' }, `${e.multiplier}× while it runs`)),
      h('span', { class: 't', dataset: { at: e.expires_at } }, clock(left(e))))));

    if (!d.items.length) { mount(body, empty({ icon: 'mystery_box', title: 'Your bag is empty', text: 'Claim your daily reward or buy something in the shop.', action: h('button', { class: 'btn primary', onClick: () => ctx.navigate('/shop') }, 'Open shop') })); return; }
    if (sel && !d.items.some((i) => i.id === sel)) sel = null;
    const info = h('div'), grid = h('div', { class: 'bag-grid' });
    const show = () => { mount(info, detail(d.items.find((i) => i.id === sel))); grid.querySelectorAll('.slot').forEach((s) => s.setAttribute('aria-pressed', String(s.dataset.id === sel))); };
    d.items.forEach((it) => grid.append(h('button', { class: 'slot', type: 'button', dataset: { id: it.id }, 'aria-pressed': 'false', onClick: () => { sel = it.id; show(); } }, ico(it.icon, 48), h('b', it.name), h('span', { class: 'faint' }, it.kind), h('span', { class: 'q' }, `×${num(it.qty)}`))));
    const titles = d.me && d.titles.length ? h('div', { class: 'panel stack' }, h('h2', 'Profile title'), h('p', { class: 'mute' }, 'Shown next to your name on your profile and the leaderboard.'),
      h('div', { class: 'row' }, d.titles.map((t) => h('button', { class: `chip ${d.equipped_title === t.text ? 'on' : ''}`, onClick: (e) => setTitle(d.equipped_title === t.text ? null : t.text, e.currentTarget) }, t.text)),
        d.equipped_title ? h('button', { class: 'btn', onClick: (e) => setTitle(null, e.currentTarget) }, 'Remove title') : null)) : null;
    mount(body, h('div', { class: 'faint' }, `${num(d.total_qty)} items`), grid, info, titles);
    show();
  }

  mount(body, loadingPage(2)); await load();
  ctx.every(1000, () => root.querySelectorAll('[data-at]').forEach((n) => { const s = Number(n.dataset.at) - nowSec(); n.textContent = clock(Math.max(0, s)); if (s <= 0) load(); }));
  ctx.onData(load);
}
