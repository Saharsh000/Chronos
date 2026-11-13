import { h, get, mount, loadCss } from '/static/core/core.js';
import { pageHead, errorBox, loadingPage, empty } from '/static/core/ui.js';

/** Every bot command, grouped like `.help`, with the page that does the same thing on the web. */
const topics = (p, i) => [
  { id: 'sessions', title: 'Study sessions', page: ['/live', 'Live'], blurb: 'Start from the site or the bot: both log to the same session and show up in the check-in channel.', cmds: [
    [`start [subject]`, 'Begin a study session'], [`stop`, 'End your session'], [`session`, 'Your live session details'], [`active`, 'Everyone studying right now']] },
  { id: 'stats', title: 'Stats and leaderboards', page: ['/leaderboard', 'Leaderboard'], blurb: 'Profile cards, graphs, rankings and head-to-head comparisons.', cmds: [
    [`stats [@user]`, 'Profile with graphs (Profile page)'], [`rank [@user]`, 'Level, XP, tier and server rank'], [`subjects [@user]`, 'Physics, Chemistry, Maths split'],
    [`leaderboard [period] [subject]`, 'today, week, month or alltime (also lb, top)'], [`halloffame`, 'All-time server records (Compare & Fame)'], [`compare @user [@user2]`, 'Head to head (also vs)']] },
  { id: 'ach', title: 'Achievements', page: ['/achievements', 'Achievements'], blurb: 'Badges for milestones. Each one pays Chronocoins.', cmds: [[`achievements [@user | category]`, 'Browse unlocked and locked badges (badges, ach)']] },
  { id: 'jee', title: 'JEE progress, notes and trivia', page: ['/progress', 'Progress'], blurb: 'Log chapters, PYQs and revisions, keep notes, and grind trivia for coins and marks.', cmds: [
    [`syllabus [subject] [chapter]`, 'Browse the syllabus (syl)'], [`chapterdone <subject> <chapter>`, 'Log a chapter'], [`subtopicdone <subject> <chapter> <subtopic>`, 'Log a subtopic'],
    [`bookdone <book>`, 'Log a finished book'], [`pyq <year> [subject]`, 'Log PYQs'], [`revision <number> [subject]`, 'Log a revision pass'], [`progress [@user]`, 'Everything you logged'],
    [`notes`, 'Chronotes notebook: new, view, pin, delete, search, export (Notes page)'], [`trivia [r|p|c|m|lb|me]`, 'JEE theory trivia (Trivia page)']] },
  { id: 'eco', title: 'Chronocoin economy', page: ['/rewards', 'Rewards'], blurb: 'Earn while you study, spend in the shop, and don\'t break your streak.', cmds: [
    [`daily`, 'Daily reward and streak bonuses'], [`dailyperks`, 'Top 3 dawn perks (perks)'], [`work`, 'Quick task for coins and XP (grind)'], [`beg`, 'Scraps, 10 minute cooldown'], [`weekly`, 'Weekly reward plus a Mystery Box'],
    [`balance`, 'Your coins (bal, coins)'], [`shop`, 'Browse items (Shop page)'], [`buy <item> [qty]`, 'Buy something'], [`inventory`, 'What you own (Bag page, inv)'], [`use <item>`, 'Activate a boost'],
    [`openbox`, 'Open a Mystery Box'], [`settitle <title|none>`, 'Equip a profile title']] },
  { id: 'pets', title: 'Pets and food', page: ['/pets', 'Pets'], blurb: `Pets level up while you study. They unlock at level ${i.pet_unlock_level}.`, cmds: [
    [`petshop [tier]`, 'Buyable pets (pshop)'], [`buypet <name>`, 'Unlock a species'], [`pets [@user]`, 'Owned pets'], [`pet [name]`, 'One pet in detail'], [`equip <name>`, 'Set your active pet'],
    [`nickname <pet> <name>`, 'Rename (nick)'], [`foodshop [tier]`, 'Pet food (fshop)'], [`buyfood <name> [qty]`, 'Buy food'], [`feed <food> [qty]`, 'Feed your pet'], [`sellfood <name> [qty]`, 'Sell back at half price']] },
  { id: 'hw', title: 'Halloween event', page: ['/halloween', 'Halloween'], blurb: 'Carve your Jack-o\'-Lantern pass by studying, collect boxes and spend candy.', cmds: [
    [`pumpkin [claim]`, 'Pass progress and rewards (pass)'], [`boxes`, 'Your Hallo-Boxes'], [`openbox <tier> [qty]`, 'Open boxes (open)'], [`candyshop`, 'Candy shop (spookyshop)'], [`buycandy <item>`, 'Buy with candy'], [`event`, 'Drop rates and reward maths']] },
  { id: 'pomo', title: 'Pomodoro', page: ['/live', 'Live'], blurb: 'A shared focus and break cycle for your voice channel.', cmds: [[`pomodoro`, 'Check the cycle in your voice channel (pomo)']] },
  { id: 'custom', title: 'Tiers and tags', page: ['/admin', 'Admin'], blurb: 'See this server\'s tier names and purchasable titles.', cmds: [[`tiers`, 'This server\'s tier names'], [`tags`, 'Purchasable profile titles']] },
  ...(i.is_manager ? [{ id: 'admin', title: 'Server admin', page: ['/admin', 'Admin'], blurb: 'Needs the matching Discord permission.', cmds: [
    [`make`, 'Create study rooms (Administrator)'], [`setcheckin #channel`, 'Set the announcements channel (Manage Server)'], [`config`, 'Show server config (Manage Server)'],
    ...(i.is_dev ? [[`settier`, 'Rename a tier (developer)'], [`addtag`, 'Add a shop tag (developer)'], [`addxp / addcoins / addtime`, 'Grants and corrections (developer)']] : [])] }] : []),
];

export default async function help(root, ctx) {
  loadCss('/static/views/help.css');
  mount(root, loadingPage(2));
  let info;
  try { info = await get('/api/help'); } catch (e) { return mount(root, errorBox(e, () => ctx.navigate('/help'))); }
  const p = info.prefix, all = topics(p, info);
  let q = '';
  const list = h('div', { class: 'hp-list' });
  const input = h('input', { class: 'input', type: 'search', placeholder: 'Search commands, e.g. daily, feed, leaderboard', 'aria-label': 'Search help' });
  input.addEventListener('input', () => { q = input.value.trim().toLowerCase(); paint(); });
  function paint() {
    const shown = all.map((t) => ({ ...t, cmds: !q || t.title.toLowerCase().includes(q) || t.blurb.toLowerCase().includes(q) ? t.cmds : t.cmds.filter(([c, d]) => `${c} ${d}`.toLowerCase().includes(q)) })).filter((t) => t.cmds.length);
    mount(list, shown.length ? shown.map((t) => h('section', { class: 'panel hp-topic', id: t.id },
      h('div', { class: 'hd' }, h('h3', t.title), h('a', { class: 'btn sm', href: t.page[0] }, `Open ${t.page[1]}`)), h('p', { class: 'mute' }, t.blurb),
      h('div', { class: 'cmds' }, t.cmds.map(([c, d]) => h('div', { class: 'cmd' }, h('code', `${p}${c}`), h('span', d)))))) : empty({ icon: 'grimoire', title: 'No commands match', text: 'Try a shorter word.' }));
  }
  const how = h('section', { class: 'panel hp-how' }, h('h3', 'How it works'), h('ul', [
    'This site and the Discord bot share one database. Whatever you do in one shows up in the other straight away.',
    'XP and Chronocoins are earned per minute while your session runs, and update live, not only when you stop.',
    `Every ${info.checkin_minutes} minutes of inactivity you get an "are you still here?" check. Answer within ${info.afk_grace_minutes} minutes or the session ends. On the site, the banner at the top does the same job.`,
    'Day boundaries (streaks, daily rewards, leaderboards) use IST, UTC+5:30.',
    'Consecutive study days build a streak. A Streak Freeze from the shop protects one missed day. Breaking a streak costs Chronocoins.',
    'Your equipped pet earns XP passively while you study, plus whatever you feed it.',
    `Trivia has a ${info.trivia_cooldown} second cooldown between questions, shared with the bot.`,
    'Subject shorthands work everywhere: phy / p, chem / c, math / m. Unlocking an achievement also pays Chronocoins.'].map((t) => h('li', t))));
  mount(root, pageHead('Help', `Every bot command, and where to do the same thing on the website. The bot's prefix is ${p}`), input, list, how);
  paint();
}
