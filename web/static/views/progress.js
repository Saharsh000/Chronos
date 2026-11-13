import { h, get, post, mount, num, ago, ico, loadCss, SUBJECTS } from '/static/core/core.js';
import { pageHead, errorBox, loadingPage, act, toast, tabs, chips, ring, empty, floatText, field } from '/static/core/ui.js';

const SUBS = ['physics', 'chemistry', 'maths'];
const TYPE_ICON = { chapter: 'study_book', subtopic: 'notebook', book: 'study_book', pyq: 'compass', revision: 'pomodoro' };
const TYPE_WORD = { chapter: 'Chapter', subtopic: 'Subtopic', book: 'Book', pyq: 'PYQ year', revision: 'Revision pass' };
const ord = (n) => ({ 1: '1st', 2: '2nd', 3: '3rd' }[n] || `${n}th`);

export default async function progress(root, ctx) {
  loadCss('/static/views/economy.css'); loadCss('/static/views/progress.css');
  const viewing = ctx.query?.user || null;
  let d = null, syl = null, sub = ctx.params?.subject && SUBS.includes(ctx.params.subject) ? ctx.params.subject : 'physics';
  let tab = ctx.params?.subject ? 'syllabus' : 'syllabus', filter = '';
  const open = new Set();
  const head = h('div'), top = h('div'), body = h('div', { class: 'stack' });
  mount(root, head, top, body);

  async function load() {
    try {
      [d, syl] = await Promise.all([get('/api/progress', viewing ? { user: viewing } : {}), get('/api/syllabus', viewing ? { user: viewing } : {})]);
      paint();
    } catch (e) { mount(body, errorBox(e, load)); }
  }
  const rewardText = (r) => `+${num(r.coins)} Chronocoins, +${num(r.xp)} XP`;
  async function log(btn, path, payload, title, line) {
    await act(btn, async () => {
      const r = await post(path, payload);
      floatText(`+${r.xp} XP`, btn);
      toast(`${typeof line === 'function' ? line(r) : line} ${rewardText(r)}.`, { kind: 'good', title: typeof title === 'function' ? title(r) : title, icon: 'chronocoin' });
      if (r.leveled_up) toast(`You reached level ${r.new_level}.`, { kind: 'good', title: 'Level up' });
      await load();
    });
  }
  const chapterDone = (c, btn) => log(btn, '/api/progress/chapter', { subject: sub, chapter: String(c.number) },
    (r) => (r.revision ? 'Revision logged' : 'Chapter done'), (r) => (r.revision ? `${r.name} counted as a revision pass. ${r.done} of ${r.total} ${SUBJECTS[sub].label} chapters done.` : `${r.name}: ${r.done} of ${r.total} ${SUBJECTS[sub].label} chapters done.`));
  const topicDone = (c, t, btn) => log(btn, '/api/progress/subtopic', { subject: sub, chapter: String(c.number), subtopic: t.name }, 'Subtopic done', (r) => `${r.subtopic}.`);

  function ringFor(s) {
    const meta = SUBJECTS[s.key];
    return h('div', { class: 'r' }, ring(s.total ? s.done / s.total : 0, { size: 84, stroke: 8, color: meta.color }, h('b', `${Math.round(100 * s.done / Math.max(1, s.total))}%`)), h('span', `${meta.label} ${s.done}/${s.total}`));
  }
  function topBlock() {
    const c = d.counts, all = { done: d.total_done, total: d.total };
    return h('div', { class: 'jee-top' }, h('div', { class: 'rings' }, ring(all.done / Math.max(1, all.total), { size: 112, stroke: 10 }, h('div', { style: { textAlign: 'center' } }, h('b', { style: { font: '800 1.5rem var(--display)' } }, `${Math.round(100 * all.done / Math.max(1, all.total))}%`), h('div', { class: 'faint', style: { fontSize: '.75rem' } }, 'syllabus'))), d.subjects.map(ringFor)),
      h('div', { class: 'metrics' }, h('div', h('b', c.pyq_years), h('span', 'PYQ years')), h('div', h('b', c.max_revision ? `Pass ${c.max_revision}` : 'None yet'), h('span', 'Revision')), h('div', h('b', c.books), h('span', 'Books finished')), h('div', h('b', c.subtopics), h('span', 'Subtopics mastered'))));
  }

  // ---------------------------------------------------------------- syllabus tab
  function syllabusTab() {
    const data = syl.subjects.find((s) => s.key === sub);
    const q = filter.trim().toLowerCase();
    const list = data.chapters.filter((c) => !q || c.name.toLowerCase().includes(q) || c.topics.some((t) => t.name.toLowerCase().includes(q)));
    const search = h('input', { class: 'input', type: 'search', placeholder: 'Search chapters and topics', value: filter, 'aria-label': 'Search chapters and topics' });
    search.addEventListener('input', () => { filter = search.value; const pos = search.selectionStart; paintTab(); const n = body.querySelector('input[type=search]'); n?.focus(); n?.setSelectionRange(pos, pos); });
    return h('div', { class: 'stack' },
      h('div', { class: 'sub-tabs' }, SUBS.map((k) => h('button', { class: `chip ${k === sub ? 'on' : ''}`, style: { '--sc': SUBJECTS[k].color }, onClick: () => { sub = k; paintTab(); } }, ico(SUBJECTS[k].icon, 18), SUBJECTS[k].label)), h('div', { style: { flex: 1, minWidth: '200px' } }, search)),
      d.me ? h('p', { class: 'reward-note' }, `Mark a chapter: ${rewardText(d.rewards.chapter)}. A chapter you've already done counts as a revision (${rewardText(d.rewards.revision)}). Subtopic: ${rewardText(d.rewards.subtopic)}.`) : null,
      list.length ? h('div', { class: 'chap-list' }, list.map((c) => {
        const det = h('details', { class: `chap ${c.done ? 'done' : ''}`, open: open.has(c.name) || !!q }, h('summary', h('span', { class: 'no' }, c.number),
          h('div', h('div', { class: 'nm' }, c.name), h('div', { class: 'meta' }, `${c.topics.filter((t) => t.done).length} of ${c.topics.length} subtopics${c.done_at ? ` · done ${ago(c.done_at)}` : ''}`)),
          d.me ? h('button', { class: `btn ${c.done ? '' : 'primary'}`, onClick: (e) => { e.preventDefault(); e.stopPropagation(); chapterDone(c, e.currentTarget); } }, c.done ? 'Log revision' : 'Mark done') : (c.done ? h('span', { class: 'tag good' }, 'Done') : null)),
          h('div', { class: 'tp' }, c.topics.map((t) => h('div', { class: `t ${t.done ? 'done' : ''}` }, h('span', { class: 'box' }, t.done ? '✓' : ''),
            d.me && !t.done ? h('button', { class: 'l', title: `Mark "${t.name}" done`, onClick: (e) => topicDone(c, t, e.currentTarget) }, t.name) : h('span', { class: 'l' }, t.name)))));
        det.addEventListener('toggle', () => { det.open ? open.add(c.name) : open.delete(c.name); });
        return det;
      })) : empty({ icon: 'study_book', title: 'No chapter matches', text: 'Try a shorter search or another subject.' }));
  }

  // ---------------------------------------------------------------- PYQ / revision / books
  function pyqTab() {
    let subj = '';
    const yr = h('input', { class: 'input', type: 'number', min: 1990, max: 2100, placeholder: 'Other year', 'aria-label': 'Year' });
    const pick = chips([{ id: '', label: 'All subjects' }, ...SUBS.map((k) => ({ id: k, label: SUBJECTS[k].label }))], '', (id) => { subj = id; });
    const go = (year, btn) => log(btn, '/api/progress/pyq', { year: String(year), subject: subj }, 'PYQ year logged', (r) => `JEE Main ${r.year}${r.subject ? ` (${r.subject})` : ''} marked complete.`);
    return h('div', { class: 'log-grid' }, h('div', { class: 'panel stack' }, h('h2', 'PYQ years'), h('p', { class: 'mute' }, `Solved a full JEE Main paper? ${rewardText(d.rewards.pyq)}.`), pick,
      h('div', { class: 'yrs' }, [2025, 2024, 2023, 2022, 2021].map((y) => h('button', { class: 'btn primary', onClick: (e) => go(y, e.currentTarget) }, y))),
      h('div', { class: 'row' }, yr, h('button', { class: 'btn', onClick: (e) => go(yr.value, e.currentTarget) }, 'Log year'))), logFeed('pyq'));
  }
  function revisionTab() {
    let subj = '';
    const n = h('input', { class: 'input', type: 'number', min: 1, max: 99, placeholder: 'Pass number', 'aria-label': 'Pass number' });
    const pick = chips([{ id: '', label: 'All subjects' }, ...SUBS.map((k) => ({ id: k, label: SUBJECTS[k].label }))], '', (id) => { subj = id; });
    const go = (num_, btn) => log(btn, '/api/progress/revision', { number: String(num_), subject: subj }, 'Revision logged', (r) => `${ord(r.number)} complete revision${r.subject ? ` (${r.subject})` : ''}.`);
    return h('div', { class: 'log-grid' }, h('div', { class: 'panel stack' }, h('h2', 'Revision passes'), h('p', { class: 'mute' }, `Finished a full syllabus pass? ${rewardText(d.rewards.revision)}.`), pick,
      h('div', { class: 'yrs' }, [1, 2, 3, 4].map((p) => h('button', { class: 'btn primary', onClick: (e) => go(p, e.currentTarget) }, `${ord(p)} pass`))),
      h('div', { class: 'row' }, n, h('button', { class: 'btn', onClick: (e) => go(n.value, e.currentTarget) }, 'Log pass'))), logFeed('revision'));
  }
  function booksTab() {
    const name = h('input', { class: 'input', placeholder: 'Any other book', maxLength: 100, 'aria-label': 'Book name' });
    const go = (b, btn) => log(btn, '/api/progress/book', { book: b }, 'Book logged', (r) => `${r.book} finished.`);
    return h('div', { class: 'log-grid' }, h('div', { class: 'panel stack' }, h('h2', 'Finished a book'), h('p', { class: 'mute' }, `${rewardText(d.rewards.book)} each time.`),
      h('div', { class: 'row' }, name, h('button', { class: 'btn', onClick: (e) => go(name.value, e.currentTarget) }, 'Log book')),
      h('div', { class: 'stack', style: { gap: '6px' } }, syl.books.map((b) => h('button', { class: 'btn', style: { justifyContent: 'flex-start', textAlign: 'left', whiteSpace: 'normal' }, onClick: (e) => go(b.name, e.currentTarget) }, ico(SUBJECTS[b.subject].icon, 18), b.name)))), logFeed('book'));
  }
  function logFeed(only) {
    const rows = d.recent.filter((m) => !only || m.type === only);
    return h('div', { class: 'panel stack' }, h('h2', only ? `Recently logged ${TYPE_WORD[only].toLowerCase()}s` : 'Recently logged'),
      rows.length ? h('div', { class: 'feed' }, rows.map((m) => h('div', { class: 'f' }, ico(TYPE_ICON[m.type] || 'notebook', 22), h('div', h('b', m.label), h('div', { class: 'faint', style: { fontSize: '.8rem' } }, [TYPE_WORD[m.type], m.subject, m.chapter && m.chapter !== m.label ? m.chapter : null].filter(Boolean).join(' · '))), h('span', { class: 'faint' }, ago(m.logged_at)))))
        : h('p', { class: 'faint' }, 'Nothing logged yet. Your next entry shows up here.'));
  }

  const TABS = [{ id: 'syllabus', label: 'Syllabus' }, { id: 'pyq', label: 'PYQs' }, { id: 'revision', label: 'Revision' }, { id: 'books', label: 'Books' }, { id: 'recent', label: 'History' }];
  const tabsEl = tabs(viewing ? [TABS[0], TABS[4]] : TABS, tab, (id) => { tab = id; paintTab(); });
  function paintTab() { mount(body, tab === 'pyq' ? pyqTab() : tab === 'revision' ? revisionTab() : tab === 'books' ? booksTab() : tab === 'recent' ? logFeed(null) : syllabusTab()); }
  function paint() {
    mount(head, pageHead(d.me ? 'JEE progress' : `${d.user.name}'s JEE progress`, d.me ? 'Log chapters, subtopics, PYQs, revisions and books. Everything you log here counts in Discord too.' : 'Read-only view.'), tabsEl);
    mount(top, topBlock()); paintTab();
  }
  mount(body, loadingPage(3)); await load();
  ctx.onData(load);
}
