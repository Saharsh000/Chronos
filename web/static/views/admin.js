import { h, get, post, mount, ico, num, loadCss } from '/static/core/core.js';
import { pageHead, errorBox, loadingPage, toast, tabs, act, field, confirmBox, empty, avatar } from '/static/core/ui.js';

const KINDS = [
  { id: 'time', label: 'Study time', help: 'Adds time and the matching XP and coins, like a real session.' },
  { id: 'xp', label: 'XP', help: 'Raw XP. Levels follow.' },
  { id: 'coins', label: 'Chronocoins', help: 'Raw balance change. Never goes below zero.' },
  { id: 'candy', label: 'Candy', help: 'Seasonal Halloween currency.' },
  { id: 'box', label: 'Hallo-Boxes', help: 'Drops boxes straight into the bag.' },
  { id: 'passtime', label: 'Pass minutes', help: 'Credits Jack-o\'-Lantern pass study time.' },
];

export default async function admin(root, ctx) {
  loadCss('/static/views/economy.css'); loadCss('/static/views/admin.css');
  let cfg = null, tab = 'server';
  const me = ctx.state.me;
  const body = h('div', { class: 'adm' });
  mount(root, pageHead('Admin', 'Server settings for managers. Developer tools show up only for the bot developer.'), body);
  mount(body, loadingPage(2));
  try { cfg = await get('/api/admin/config'); } catch (e) { return mount(body, errorBox(e, () => ctx.navigate('/admin'))); }
  const items = [{ id: 'server', label: 'Server' }, { id: 'tiers', label: 'Tiers' }, { id: 'tags', label: 'Tags' }, ...(cfg.is_dev ? [{ id: 'grant', label: 'Grants' }, { id: 'diag', label: 'Diagnostics' }] : [])];
  const pane = h('div', { class: 'adm-pane' });
  const t = tabs(items, tab, (id) => { tab = id; paint(); });
  mount(body, t, pane);
  const paint = () => ({ server: paintServer, tiers: paintTiers, tags: paintTags, grant: paintGrant, diag: paintDiag })[tab](pane);

  // ---------------------------------------------------------------- server
  function paintServer(box) {
    const sel = h('select', { class: 'select', 'aria-label': 'Check-in channel' }, h('option', { value: '' }, 'Choose a channel'), cfg.text_channels.map((c) => h('option', { value: c.id, selected: cfg.checkin?.id === c.id }, `#${c.name}`)));
    const save = h('button', { class: 'btn primary', type: 'button', onClick: (e) => act(e.currentTarget, async () => {
      if (!sel.value) return toast('Pick a channel first.', { kind: 'bad' });
      const r = await post('/api/admin/checkin', { channel: sel.value });
      cfg.checkin = r.checkin; toast(`Announcements will go to #${r.checkin.name}.`, { kind: 'good', title: 'Check-in channel set' }); paint();
    }) }, 'Save channel');
    const rooms = cfg.rooms.map((r) => h('div', { class: 'room' }, ico(`subject_${r.key}`, 32), h('div', h('b', r.label), h('span', { class: r.channel ? 'faint' : 'warn' }, r.channel ? (r.channel.name ? `#${r.channel.name}` : 'Channel not found') : 'Not set'))));
    const make = h('button', { class: 'btn', type: 'button', disabled: !cfg.can_make_rooms, title: cfg.can_make_rooms ? '' : 'Needs the Administrator permission',
      onClick: async (e) => {
        if (!(await confirmBox('Chronos will create a Study Rooms category with Physics, Chemistry and Maths voice channels, and reuse any that already exist.', { title: 'Create study rooms?', confirm: 'Create rooms' }))) return;
        await act(e.currentTarget, async () => {
          const r = await post('/api/admin/rooms');
          toast([r.created.length ? `Created ${r.created.join(', ')}.` : null, r.reused.length ? `Already there: ${r.reused.join(', ')}.` : null].filter(Boolean).join(' '), { kind: 'good', title: 'Study rooms ready' });
          cfg = await get('/api/admin/config'); paint();
        });
      } }, 'Create study rooms');
    mount(box,
      h('section', { class: 'panel' }, h('h3', 'Check-in channel'), h('p', { class: 'mute' }, 'Where Chronos posts AFK prompts, session summaries, level-ups, Pomodoro updates and web session logs.'),
        h('div', { class: 'row' }, sel, save), cfg.checkin && !cfg.checkin.name ? h('p', { class: 'warn' }, 'The saved channel no longer exists. Pick a new one.') : null),
      h('section', { class: 'panel' }, h('h3', 'Study rooms'), h('p', { class: 'mute' }, 'Voice channels that count study time by subject. Joining one and starting a session gives subject-specific credit.'),
        h('div', { class: 'rooms' }, rooms), h('div', { class: 'row' }, make, cfg.can_make_rooms ? null : h('span', { class: 'faint' }, 'Administrator permission required.'))));
  }

  // ---------------------------------------------------------------- tiers
  async function paintTiers(box) {
    mount(box, loadingPage(1));
    const d = await get('/api/tiers');
    const rows = d.tiers.map((r) => {
      const input = h('input', { class: 'input', value: r.name, maxLength: 40, 'aria-label': `Name for level ${r.level}`, disabled: !d.can_edit });
      return h('div', { class: `tier-row ${r.renamed ? 'renamed' : ''}` }, h('b', { class: 'lv' }, `Lv. ${r.level}+`), h('div', { class: 'nm' }, d.can_edit ? input : h('span', r.name), r.renamed ? h('span', { class: 'faint' }, `Default: ${r.default}`) : null),
        d.can_edit ? h('div', { class: 'row' }, h('button', { class: 'btn sm primary', type: 'button', onClick: (e) => act(e.currentTarget, async () => { await post('/api/admin/tiers/set', { level: r.level, name: input.value }); toast(`Level ${r.level}+ is now ${input.value.trim()}.`, { kind: 'good', title: 'Tier renamed' }); paintTiers(box); }) }, 'Rename'),
          r.renamed ? h('button', { class: 'btn sm', type: 'button', onClick: (e) => act(e.currentTarget, async () => { await post('/api/admin/tiers/reset', { level: r.level }); paintTiers(box); }) }, 'Reset') : null) : null);
    });
    mount(box, h('section', { class: 'panel' }, h('h3', 'Tier names'), h('p', { class: 'mute' }, 'Only the names change here. The levels that unlock each tier stay the same.'), h('div', { class: 'tiers' }, rows),
      d.can_edit && d.tiers.some((x) => x.renamed) ? h('button', { class: 'btn', type: 'button', onClick: async (e) => { if (await confirmBox('Every tier goes back to its default name in this server.', { title: 'Reset all tiers?', confirm: 'Reset all', danger: true })) act(e.currentTarget, async () => { const r = await post('/api/admin/tiers/reset', {}); toast(`${r.reset} tier name${r.reset === 1 ? '' : 's'} reset.`, { kind: 'good' }); paintTiers(box); }); } }, 'Reset all tiers') : null));
  }

  // ---------------------------------------------------------------- tags
  async function paintTags(box) {
    mount(box, loadingPage(1));
    const d = await get('/api/tags');
    const title = h('input', { class: 'input', placeholder: 'Tag text, e.g. The Grinder', maxLength: 40, 'aria-label': 'Tag text' });
    const price = h('input', { class: 'input', type: 'number', min: 0, placeholder: 'Price', 'aria-label': 'Price in Chronocoins', style: { maxWidth: '140px' } });
    const add = d.can_edit ? h('div', { class: 'row' }, title, price, h('button', { class: 'btn primary', type: 'button', onClick: (e) => act(e.currentTarget, async () => {
      await post('/api/admin/tags/add', { title: title.value, price: price.value }); toast(`${title.value.trim()} is now in the shop.`, { kind: 'good', title: 'Tag added' }); paintTags(box);
    }) }, 'Add tag')) : null;
    const pill = (t, removable) => h('div', { class: 'tag-row' }, h('b', t.title), h('span', { class: 'pill' }, ico('chronocoin', 16), num(t.price)),
      removable && d.can_edit ? h('button', { class: 'btn sm danger', type: 'button', onClick: async (e) => { if (await confirmBox(`${t.title} will no longer be sold. People who already own it keep it.`, { title: 'Remove this tag?', confirm: 'Remove', danger: true })) act(e.currentTarget, async () => { await post('/api/admin/tags/remove', { tag: t.id }); paintTags(box); }); } }, 'Remove') : null);
    mount(box, d.can_edit ? h('section', { class: 'panel' }, h('h3', 'Add a custom tag'), add) : null,
      h('section', { class: 'panel' }, h('h3', 'Custom tags'), d.custom.length ? h('div', { class: 'tags-list' }, d.custom.map((t) => pill(t, true))) : h('p', { class: 'faint' }, 'No custom tags yet.')),
      h('section', { class: 'panel' }, h('h3', 'Built-in tags'), h('div', { class: 'tags-list' }, d.builtin.map((t) => pill(t, false)))));
  }

  // ---------------------------------------------------------------- developer grants
  async function paintGrant(box) {
    mount(box, loadingPage(1));
    const { members } = await get('/api/admin/members');
    if (!members.length) return mount(box, empty({ icon: 'study_book', title: 'No members yet', text: 'Members appear once they have stats in this server.' }));
    let kind = 'time', mode = 'add';
    const who = h('select', { class: 'select', 'aria-label': 'Member' }, members.map((m) => h('option', { value: m.id }, `${m.name} (level ${m.level})`)));
    const fields = h('div', { class: 'grant-fields' }), result = h('div', { class: 'grant-result', hidden: true });
    const inp = (name, attrs) => h('input', { class: 'input', 'aria-label': name, ...attrs });
    const f = { duration: inp('Duration', { placeholder: '3h, 45m or 1h30m' }), subject: h('select', { class: 'select', 'aria-label': 'Subject' }, [['', 'Any subject'], ['physics', 'Physics'], ['chemistry', 'Chemistry'], ['maths', 'Maths']].map(([v, l]) => h('option', { value: v }, l))),
      amount: inp('Amount', { type: 'number', placeholder: 'Amount', min: 1 }), box: h('select', { class: 'select', 'aria-label': 'Box tier' }, ['common', 'uncommon', 'rare', 'epic', 'legendary'].map((v) => h('option', { value: v }, v[0].toUpperCase() + v.slice(1)))),
      quantity: inp('Quantity', { type: 'number', value: 1, min: 1, max: 1000 }), minutes: inp('Minutes', { type: 'number', placeholder: 'Minutes', min: 1 }) };
    const modeTabs = h('div', { class: 'chips' }, ['add', 'remove'].map((m) => h('button', { class: `chip ${m === mode ? 'on' : ''}`, type: 'button', onClick: () => { mode = m; modeTabs.querySelectorAll('.chip').forEach((c, i) => c.classList.toggle('on', ['add', 'remove'][i] === mode)); } }, m === 'add' ? 'Add' : 'Remove')));
    const repaint = () => {
      const k = KINDS.find((x) => x.id === kind);
      modeTabs.hidden = kind === 'box' || kind === 'passtime'; if (modeTabs.hidden) { mode = 'add'; }
      mount(fields, h('p', { class: 'faint' }, k.help), kind === 'time' ? [field('Duration', f.duration), field('Subject', f.subject)] : kind === 'box' ? [field('Box tier', f.box), field('Quantity', f.quantity)] : kind === 'passtime' ? field('Minutes', f.minutes) : field('Amount', f.amount));
    };
    const kindSel = h('select', { class: 'select', 'aria-label': 'What to change', onChange: (e) => { kind = e.target.value; repaint(); } }, KINDS.map((k) => h('option', { value: k.id }, k.label)));
    const go = h('button', { class: 'btn primary', type: 'button', onClick: (e) => act(e.currentTarget, async () => {
      const m = members.find((x) => x.id === who.value);
      if (mode === 'remove' && !(await confirmBox(`This takes things away from ${m.name}. It can't be undone automatically.`, { title: 'Remove from this member?', confirm: 'Remove', danger: true }))) return;
      const payload = { user: who.value, kind, mode, duration: f.duration.value, subject: f.subject.value, amount: f.amount.value, box: f.box.value, quantity: f.quantity.value, minutes: f.minutes.value };
      const r = await post('/api/admin/grant', payload);
      result.hidden = false; mount(result, avatar(r.user, 32), h('div', h('b', r.user.name), h('p', r.text), r.level_changed ? h('p', { class: 'good' }, `Now level ${r.new_level}${r.tier ? `, ${r.tier}` : ''}.`) : null));
      toast(r.text, { kind: 'good', title: 'Done' });
    }) }, 'Apply');
    mount(box, h('section', { class: 'panel' }, h('h3', 'Grants and corrections'), h('p', { class: 'mute' }, 'The same as the bot\'s developer commands. Changes land in the shared database straight away.'),
      h('div', { class: 'grant' }, field('Member', who), field('What to change', kindSel), modeTabs, fields, h('div', { class: 'row' }, go)), result));
    repaint();
  }

  // ---------------------------------------------------------------- diagnostics
  async function paintDiag(box) {
    mount(box, loadingPage(1));
    const d = await get('/api/admin/diagnostics');
    mount(box, h('section', { class: 'panel' }, h('h3', 'Database'), h('p', { class: 'mute' }, `This server: ${d.guild}. Servers in the database: ${d.known_guilds.join(', ') || 'none'}.`),
      h('div', { class: 'diag' }, Object.entries(d.counts).map(([k, v]) => h('div', { class: 'st' }, h('b', typeof v === 'number' ? num(v) : v), h('span', k))))),
      h('section', { class: 'panel' }, h('h3', 'You in this server'), h('div', { class: 'diag' }, [['Level', d.you.level], ['XP', num(d.you.xp)], ['Chronocoins', num(d.you.coins)], ['Lifetime coins', num(d.you.lifetime)], ['Streak', `${d.you.streak} days`], ['Pets', d.you.pets.join(', ') || 'None']].map(([k, v]) => h('div', { class: 'st' }, h('b', String(v)), h('span', k)))),
        h('button', { class: 'btn', type: 'button', onClick: () => paintDiag(box) }, 'Refresh')));
  }

  paint();
}
