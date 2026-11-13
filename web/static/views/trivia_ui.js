import { h } from '/static/core/core.js';
import { mathEl } from '/static/views/lib.js';

/** Server-structured segments ({k:'text'} / {k:'math'}) -> DOM nodes. Math is typeset by KaTeX, with distexer's Unicode as the fallback. */
export const segs = (list = []) => list.map((s) => (s.k === 'math' ? mathEl(s.tex, { display: s.display, fallback: s.uni }) : s.v));

/** Paragraphs and list items (Statement I / (i) / (a)) from distexer's layout. */
export const blocks = (list = []) => list.map((b) => (b.t === 'item'
  ? h('div', { class: 'tz-item', style: { '--lv': b.level || 0 } }, b.label ? h('b', { class: 'lbl' }, b.label) : h('i', { class: 'dot' }), h('span', ...segs(b.segs)))
  : h('p', ...segs(b.segs))));

export function matchTable(m) {
  const col = (title, rows, kind) => h('div', { class: `col ${kind}` }, h('h4', title),
    rows.map((r) => h('div', { class: 'row-m' }, h('b', { class: 'k' }, r.key), h('span', ...segs(r.segs)))));
  return h('div', { class: 'tz-match' }, m.stem?.length ? h('p', { class: 'stem' }, ...segs(m.stem)) : null,
    h('div', { class: 'cols' }, col(m.header_i, m.list_i, 'a'), col(m.header_ii, m.list_ii, 'b')),
    m.tail?.length ? h('p', { class: 'tail' }, ...segs(m.tail)) : null);
}

export const DIFF = { easy: 'Easy', medium: 'Medium', hard: 'Hard' };
export const subKey = (id) => (id === 'mathematics' ? 'maths' : id);
export const clockText = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
