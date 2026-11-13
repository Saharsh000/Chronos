import { h, get, post, mount, clock, num, nowSec, ico, loadCss } from '/static/core/core.js';
import { pageHead, errorBox, loadingPage, modal, act, toast, bar, avatar } from '/static/core/ui.js';

function countUp(el, to, ms = 900) {
  const t0 = performance.now();
  const step = (t) => { const k = Math.min(1, (t - t0) / ms); el.textContent = num(Math.round(to * (1 - Math.pow(1 - k, 3)))); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
const hallo = (x) => x && h('div', { class: 'extra' }, h('b', `${x.box.emoji} ${x.box.name}`), h('div', { class: 'mute' }, `+${num(x.candy)} candy. Open it from your Bag.`));

export default async function rewards(root, ctx) {
  loadCss('/static/views/economy.css');
  let d = null;
  const head = h('div'), cards = h('div', { class: 'claims' }), perks = h('div');
  mount(root, head, cards, perks);

  async function load() {
    try { d = await get('/api/rewards'); paint(); } catch (e) { mount(cards, errorBox(e, load)); }
    loadPerks();
  }
  const left = (c) => Math.max(0, (c.ready_at ?? c.next_at) - nowSec());

  function reveal(title, lines, body) {
    const amt = h('span');
    modal({ title, content: h('div', { class: 'reveal' }, h('div', { class: 'amount' }, ico('chronocoin', 44), '+', amt), ...body), actions: [{ label: 'Nice', kind: 'primary', value: true }] });
    countUp(amt, lines);
  }

  async function claim(kind, btn) {
    await act(btn, async () => {
      const r = await post(`/api/rewards/${kind}`);
      const body = [];
      if (kind === 'daily') {
        body.push(h('div', { class: 'row', style: { justifyContent: 'center' } }, h('span', { class: 'tag' }, `Base +${num(r.base_coins)}`), h('span', { class: 'tag' }, `Streak bonus +${num(r.streak_bonus)}`), h('span', { class: 'tag accent' }, `+${r.xp} XP`), h('span', { class: 'tag good' }, `${r.daily_streak}-day streak`)));
        if (r.milestone) body.push(h('div', { class: 'extra' }, h('b', `${r.milestone.days}-day milestone`), h('div', { class: 'mute' }, `+${num(r.milestone.coins)} bonus coins${r.milestone.item ? ` and a free ${r.milestone.item.name}` : ''}.`)));
        else if (r.bonus_box) body.push(h('div', { class: 'extra' }, h('b', 'Bonus'), h('div', { class: 'mute' }, 'A free Mystery Box is in your Bag.')));
      } else if (kind === 'work') body.push(h('span', { class: 'tag accent' }, `+${r.xp} XP`));
      else if (kind === 'beg') {
        body.push(h('div', { class: 'story' }, h('b', `${r.scene.emoji} ${r.scene.npc}`), h('div', { class: 'faint' }, r.scene.role), h('p', { style: { marginTop: '6px' } }, r.scene.story), r.scene.quote ? h('p', { style: { marginTop: '6px', fontStyle: 'italic' } }, `"${r.scene.quote}"`) : null));
        if (!r.success) body.push(h('p', { class: 'warn' }, 'No coins this time.'));
      } else body.push(h('div', { class: 'extra' }, h('b', 'Free Mystery Box'), h('div', { class: 'mute' }, 'Added to your Bag.')));
      body.push(hallo(r.hallo));
      if (r.leveled_up) body.push(h('div', { class: 'extra' }, h('b', `Level up: ${r.old_level} to ${r.new_level}`)));
      (r.achievements || []).length && body.push(h('div', { class: 'extra' }, h('b', 'Achievement unlocked'), h('div', { class: 'mute' }, 'Check the Achievements page.')));
      reveal(r.success === false ? 'Empty-handed' : 'Claimed', r.coins ?? 0, body.filter(Boolean));
      await load();
    });
  }

  function card(kind, title, icon, c, blurb, extra) {
    const ready = c.available;
    const btn = h('button', { class: `btn ${ready ? 'primary' : ''}`, disabled: !ready, onClick: (e) => claim(kind, e.currentTarget) }, ready ? `Claim ${title.toLowerCase()}` : 'On cooldown');
    return h('div', { class: `claim ${ready ? 'ready' : ''}` }, h('div', { class: 'row' }, ico(icon, 36), h('h2', title)), h('p', { class: 'mute' }, blurb),
      h('div', { class: 'range' }, `${num(c.coins[0])} to ${num(c.coins[1])} coins${c.xp ? ` · ${c.xp[0]} to ${c.xp[1]} XP` : ''}${kind === 'beg' ? ` · ${Math.round(c.fail_chance * 100)}% chance of nothing` : ''}`),
      extra, ready ? h('div', { class: 'cd' }, 'Ready') : h('div', { class: 'cd', dataset: { at: c.ready_at ?? c.next_at } }, clock(left(c))), btn);
  }

  function paint() {
    const cur = d.wallet;
    mount(head, pageHead('Rewards', 'Claim what you\'ve earned. Cooldowns are the same as in Discord, so a claim here counts there too.'),
      h('div', { class: 'wallet-bar' }, h('span', { class: 'big' }, ico('chronocoin', 34), num(cur.coins)), h('span', { class: 'big' }, ico('candy', 34), num(cur.candy))));
    const dl = d.daily, streak = dl.streak, shown = Math.max(35, Math.ceil((streak + 1) / 7) * 7), ms = new Set(dl.milestones.map((m) => m.days));
    const dots = h('div', { class: 'streak-dots', 'aria-label': `Daily streak: ${streak} days` }, Array.from({ length: shown }, (_, i) => h('i', { class: `${i < streak ? 'on' : ''} ${ms.has(i + 1) ? 'ms' : ''}`, title: ms.has(i + 1) ? 'Milestone day' : '' }, i + 1)));
    const next = dl.milestones.find((m) => m.days > streak);
    mount(cards,
      card('daily', 'Daily', 'chronocoin', { ...dl, ready_at: dl.next_at }, `Once per day, resets at 00:00 IST. Streak ${streak} ${streak === 1 ? 'day' : 'days'} (+${dl.bonus_per_day} coins per day, capped at ${dl.bonus_cap_days}). A Mystery Box every ${dl.box_every} days.`,
        h('div', { class: 'stack' }, dots, next ? h('span', { class: 'faint' }, `Next milestone: day ${next.days}, +${num(next.coins)} coins`) : null)),
      card('work', 'Work', 'study_book', d.work, 'A quick task for coins and a little XP. Short cooldown, use it often.'),
      card('beg', 'Beg', 'candy', d.beg, 'Small payout, very short cooldown. A JEE legend might help, or you get nothing.'),
      card('weekly', 'Weekly', 'mystery_box', d.weekly, 'The big weekly haul, plus a free Mystery Box and a rare Hallo-Box.'));
  }

  async function loadPerks() {
    try {
      const p = await get('/api/perks');
      mount(perks, h('div', { class: 'panel' }, h('div', { class: 'panel-head' }, h('h2', 'Top 3 daily perks'), ico('rank_crown', 30)),
        h('p', { class: 'mute' }, 'The three biggest all-time studiers unlock a perk on their first action each IST day.'),
        h('div', { class: 'list' }, p.holders.map((r) => h('div', h('span', { class: 'rank' }, r.rank), r.holder ? avatar(r.holder, 34) : null,
          h('div', { class: 'grow' }, h('b', r.holder ? r.holder.name : 'Open slot'), h('div', { class: 'faint' }, `${r.title} · ${r.boost} · ${r.coins} coins · ${r.item}`)),
          r.holder ? h('span', { class: `tag ${r.claimed ? 'good' : ''}` }, r.claimed ? 'Claimed today' : 'Waiting') : null))),
        h('p', { class: p.status === 'outside' ? 'faint' : 'good' }, { outside: 'You\'re outside the top 3. Study more to climb.', claimed: `You're rank ${p.my_rank}. Today's perk is already active.`, activated: `You're rank ${p.my_rank}. ${p.perk?.perk_name} just activated.`, ready: `You're rank ${p.my_rank}. Your perk is ready.` }[p.status])));
    } catch { mount(perks); }
  }

  mount(cards, loadingPage(1)); await load();
  ctx.every(1000, () => {
    root.querySelectorAll('[data-at]').forEach((n) => { const s = Number(n.dataset.at) - nowSec(); n.textContent = clock(Math.max(0, s)); if (s <= 0) load(); });
  });
  ctx.onData(load);
}
