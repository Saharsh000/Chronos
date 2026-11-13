import { h, get, post, patch, del, mount, ico, loadCss, debounce, fmtDate } from '/static/core/core.js';
import { pageHead, errorBox, loadingPage, act, toast, confirmBox, empty, chips } from '/static/core/ui.js';
import { markdown } from '/static/views/lib.js';

const ACCENTS = { physics: '#5aa9ff', chemistry: '#3ddc97', mathematics: '#ff9f5a', maths: '#ff9f5a', formulas: '#f4c542', revision: '#c58bff', general: '#8b93ff' };
const accentOf = (s = '') => ACCENTS[s.toLowerCase()] || ACCENTS[Object.keys(ACCENTS).find((k) => s.toLowerCase().includes(k.slice(0, 4)))] || ACCENTS.general;
const plain = (t) => t.replace(/\$\$?/g, '').replace(/^#+\s*|\s#+\s/g, ' ').replace(/[*`>{}]/g, '').replace(/\\(?=[a-zA-Z])/g, '').replace(/\s+-\s+/g, ' · ').trim();
const STARTER = 'Write in Markdown. Use $E = mc^2$ for inline formulas and $$ ... $$ for display ones.\n\n## Key points\n- ';

export default async function notes(root, ctx) {
  loadCss('/static/views/notes.css');
  let hub = null, sel = null, editing = null, q = '', subject = 'all', pinnedOnly = false, mobileDetail = false;
  const head = h('div'), shell = h('div', { class: 'nb' }), listCol = h('aside', { class: 'nb-list' }), pane = h('section', { class: 'nb-pane' });
  shell.append(listCol, pane);
  mount(root, head, shell);
  mount(pane, loadingPage(2));

  async function load(keepSel = true) {
    try {
      hub = await get('/api/notes', { q: q || undefined, subject: subject === 'all' ? undefined : subject, pinned: pinnedOnly ? 1 : undefined });
      if (keepSel && sel && !hub.notes.some((n) => n.id === sel.id)) sel = hub.notes.find((n) => n.id === sel.id) || sel;
      paintHead(); paintList(); paintPane();
    } catch (e) { mount(pane, errorBox(e, () => load())); }
  }
  const cls = () => { shell.classList.toggle('show-detail', mobileDetail); };

  // --------------------------------------------------------------- header
  function paintHead() {
    const s = hub.stats;
    mount(head, pageHead('Chronotes', `${s.total} note${s.total === 1 ? '' : 's'}, ${s.pinned} pinned. Private to you, and the same notebook you see with the bot.`,
      h('button', { class: 'btn', type: 'button', onClick: exportAll, disabled: !s.total }, ico('notes', 18), 'Export notebook'),
      h('button', { class: 'btn primary', type: 'button', onClick: () => startNew() }, ico('notebook', 18), 'New note')));
  }
  async function exportAll(e) {
    await act(e.currentTarget, async () => {
      const r = await get('/api/notes/export');
      const url = URL.createObjectURL(new Blob([r.markdown], { type: 'text/markdown' }));
      const a = h('a', { href: url, download: r.filename }); document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 4000);
      toast(`${r.count} note${r.count === 1 ? '' : 's'} exported.`, { kind: 'good', title: 'Notebook saved', icon: 'notes' });
    });
  }

  // --------------------------------------------------------------- list column
  const search = h('input', { class: 'input', type: 'search', placeholder: 'Search titles and text', 'aria-label': 'Search notes', maxLength: 50 });
  search.addEventListener('input', debounce(() => { q = search.value.trim(); load(); }, 220));
  function paintList() {
    const items = [{ id: 'all', label: 'All' }, ...hub.subjects.map((s) => ({ id: s.key, label: s.label.replace(' & Shortcuts', '').replace(' Checklist', '').replace(' Notes', '') }))];
    const filterRow = chips(items, subject, (id) => { subject = id; load(); });
    const pin = h('button', { class: `chip ${pinnedOnly ? 'on' : ''}`, type: 'button', 'aria-pressed': String(pinnedOnly), onClick: () => { pinnedOnly = !pinnedOnly; load(); } }, 'Pinned only');
    const rows = hub.notes.map((n) => h('button', {
      class: `nb-item ${sel?.id === n.id && !editing?.isNew ? 'on' : ''}`, type: 'button', style: { '--nc': accentOf(n.subject) }, onClick: () => open(n.id),
    }, h('span', { class: 'top' }, h('b', n.title), n.pinned ? h('span', { class: 'pinmark', title: 'Pinned' }, 'Pinned') : null),
      h('span', { class: 'ex' }, plain(n.excerpt)), h('span', { class: 'meta' }, h('span', { class: 'sub' }, n.subject), h('span', fmtDate(n.updated_at)))));
    mount(listCol, h('div', { class: 'nb-tools' }, search, h('div', { class: 'row wrap' }, filterRow, pin)),
      rows.length ? h('div', { class: 'nb-items' }, rows)
        : hub.filtered ? empty({ icon: 'notes', title: 'No notes match', text: 'Try a different word, or clear the filters.', action: h('button', { class: 'btn', type: 'button', onClick: () => { q = ''; search.value = ''; subject = 'all'; pinnedOnly = false; load(); } }, 'Clear filters') })
          : empty({ icon: 'notebook', title: 'Your notebook is empty', text: 'Save formulas, mistake logs and revision lists. Everything you write here shows up in the bot too.', action: h('button', { class: 'btn primary', type: 'button', onClick: () => startNew() }, 'Write your first note') }));
  }

  // --------------------------------------------------------------- reader
  async function open(id) {
    if (editing && !(await leaveEditor())) return;
    editing = null;
    try { sel = (await get(`/api/notes/${id}`)).note; } catch (e) { toast(e.message, { kind: 'bad' }); return load(); }
    mobileDetail = true; cls(); paintList(); paintPane();
  }
  function reader() {
    const n = sel, col = accentOf(n.subject);
    const act_ = (label, icon, fn, kind = '') => h('button', { class: `btn sm ${kind}`, type: 'button', onClick: fn }, icon ? ico(icon, 16) : null, label);
    return h('article', { class: 'nb-read', style: { '--nc': col } },
      h('div', { class: 'nb-bar' },
        h('button', { class: 'btn sm ghost back', type: 'button', onClick: () => { mobileDetail = false; cls(); } }, 'All notes'),
        h('div', { class: 'acts' },
          act_(n.pinned ? 'Unpin' : 'Pin', null, async (e) => act(e.currentTarget, async () => { sel = (await patch(`/api/notes/${n.id}`, { pinned: !n.pinned })).note; await load(); })),
          act_('Edit', null, () => startEdit()),
          h('a', { class: 'btn sm', href: `/api/notes/${n.id}/card`, target: '_blank', rel: 'noopener' }, ico('chrono_clock', 16), 'Card'),
          act_('Delete', null, () => remove(), 'danger'))),
      h('header', h('span', { class: 'chip-sub' }, n.subject), h('h2', n.title), h('p', { class: 'meta' }, `Saved ${fmtDate(n.updated_at)}. Note #${n.id}.`)),
      n.image_url ? h('img', { class: 'att', src: n.image_url, alt: `Attachment on ${n.title}`, loading: 'lazy' }) : null,
      markdown(n.content));
  }
  async function remove() {
    if (!(await confirmBox(`"${sel.title}" will be removed from your notebook, here and in the bot.`, { title: 'Delete this note?', confirm: 'Delete note', danger: true }))) return;
    await del(`/api/notes/${sel.id}`);
    toast('Note deleted.', { kind: 'good', title: 'Deleted' });
    sel = null; mobileDetail = false; cls(); await load(false);
  }

  // --------------------------------------------------------------- editor
  function startNew(prefill = {}) {
    editing = { isNew: true, title: '', subject: subject !== 'all' ? (hub.subjects.find((s) => s.key === subject)?.label.split(' ')[0] || 'General') : 'General', content: STARTER, ...prefill };
    mobileDetail = true; cls(); paintList(); paintPane();
  }
  function startEdit() { editing = { isNew: false, id: sel.id, title: sel.title, subject: sel.subject, content: sel.content }; paintPane(); }
  const dirty = () => editing && (editing.isNew ? (editing.title.trim() || (editing.content !== STARTER && editing.content.trim())) : (editing.title !== sel.title || editing.subject !== sel.subject || editing.content !== sel.content));
  async function leaveEditor() {
    if (!dirty()) return true;
    return confirmBox('You have changes that aren\'t saved yet.', { title: 'Discard changes?', confirm: 'Discard', danger: true });
  }
  function editor() {
    const L = hub.limits, e = editing;
    const title = h('input', { class: 'input', maxLength: L.title, placeholder: 'e.g. Rotational mechanics: key formulas', value: e.title, 'aria-label': 'Title' });
    const sub = h('input', { class: 'input', maxLength: L.subject, list: 'nb-subjects', value: e.subject, placeholder: 'General', 'aria-label': 'Category' });
    const list = h('datalist', { id: 'nb-subjects' }, ['Physics', 'Chemistry', 'Mathematics', 'Formulas', 'Revision', 'General'].map((v) => h('option', { value: v })));
    const text = h('textarea', { class: 'input mono', maxLength: L.content, 'aria-label': 'Note content', spellcheck: 'true' });
    text.value = e.content;
    const count = h('span', { class: 'count' });
    const prev = h('div', { class: 'nb-prev' });
    const paintPrev = debounce(() => { mount(prev, markdown(text.value || '*Nothing to preview yet.*')); }, 180);
    const sync = () => { e.title = title.value; e.subject = sub.value; e.content = text.value; count.textContent = `${text.value.length.toLocaleString('en-IN')} / ${L.content.toLocaleString('en-IN')}`; count.classList.toggle('bad', text.value.length > L.content * 0.95); paintPrev(); };
    [title, sub, text].forEach((el) => el.addEventListener('input', sync));
    const insert = (pre, post_ = '') => {
      const a = text.selectionStart, b = text.selectionEnd, mid = text.value.slice(a, b);
      text.setRangeText(pre + mid + post_, a, b, 'select'); text.focus(); text.setSelectionRange(a + pre.length, a + pre.length + mid.length); sync();
    };
    const tool = (label, fn, tip) => h('button', { class: 'btn sm ghost', type: 'button', title: tip || label, onClick: fn }, label);
    const save = async (btn) => {
      await act(btn, async () => {
        const body = { title: e.title, subject: e.subject, content: e.content };
        if (e.isNew) { const r = await post('/api/notes', body); sel = r.note; toast('Saved to your notebook.', { kind: 'good', title: 'Note created', icon: 'notes' }); }
        else { const r = await patch(`/api/notes/${e.id}`, body); sel = r.note; toast('Changes saved.', { kind: 'good', title: 'Note updated' }); }
        editing = null; await load();
      });
    };
    const saveBtn = h('button', { class: 'btn primary', type: 'button', onClick: (ev) => save(ev.currentTarget) }, e.isNew ? 'Save note' : 'Save changes');
    text.addEventListener('keydown', (ev) => { if ((ev.ctrlKey || ev.metaKey) && ev.key === 's') { ev.preventDefault(); saveBtn.click(); } });
    title.addEventListener('keydown', (ev) => { if ((ev.ctrlKey || ev.metaKey) && ev.key === 's') { ev.preventDefault(); saveBtn.click(); } });
    setTimeout(() => { sync(); (e.isNew ? title : text).focus(); }, 0);
    return h('div', { class: 'nb-edit' },
      h('div', { class: 'nb-bar' },
        h('button', { class: 'btn sm ghost back', type: 'button', onClick: async () => { if (await leaveEditor()) { editing = null; if (!sel) mobileDetail = false; cls(); paintList(); paintPane(); } } }, 'Cancel'),
        h('div', { class: 'acts' }, h('span', { class: 'faint hint' }, 'Ctrl+S to save'), saveBtn)),
      h('div', { class: 'row2' }, h('div', { class: 'field' }, h('label', 'Title'), title), h('div', { class: 'field' }, h('label', 'Category'), sub, list)),
      h('div', { class: 'tools' }, tool('Heading', () => insert('## '), 'Heading'), tool('Bold', () => insert('**', '**')), tool('Bullet', () => insert('- ')),
        tool('Formula', () => insert('$', '$'), 'Inline formula'), tool('Formula block', () => insert('\n$$\n', '\n$$\n'), 'Display formula'), tool('Code', () => insert('`', '`')), count),
      h('div', { class: 'split' }, h('div', { class: 'field' }, h('label', 'Content'), text), h('div', { class: 'field' }, h('label', 'Preview'), prev)));
  }

  function paintPane() {
    if (editing) return mount(pane, editor());
    if (sel) return mount(pane, reader());
    mount(pane, h('div', { class: 'nb-blank' }, ico('notebook', 56), h('h3', 'Pick a note to read'), h('p', 'Or start a new one. Formulas typed between dollar signs are typeset.'),
      h('button', { class: 'btn primary', type: 'button', onClick: () => startNew() }, 'New note')));
  }

  await load();
  if (ctx.query?.n) open(ctx.query.n);
}
