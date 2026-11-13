import { h } from '/static/core/core.js';
// Small shared helpers for views. Item blurbs come from the bot and mention Discord commands; on the web say what to do instead.
export function clean(s = '') {
  return String(s)
    .replace(/\s*Open with `\.openbox`\./g, ' Open it from your Bag.')
    .replace(/`\.use`\s+to\s+/g, 'Use it to ')
    .replace(/`\.stats`\s*/g, 'stats ')
    .replace(/`\.(\w+)`/g, 'the $1 action')
    .replace(/`/g, '');
}

// ---------------------------------------------------------------- math + light markdown

let katexReady = null;
/** Load the vendored KaTeX once (served from /static/vendor, so it passes the CSP). Resolves to window.katex, or null if it can't load. */
export function loadKatex() {
  if (katexReady) return katexReady;
  katexReady = new Promise((resolve) => {
    document.head.append(h('link', { rel: 'stylesheet', href: '/static/vendor/katex/katex.min.css' }));
    const s = h('script', { src: '/static/vendor/katex/katex.min.js' });
    s.onload = () => resolve(window.katex || null);
    s.onerror = () => resolve(null);
    document.head.append(s);
  });
  return katexReady;
}

/** A math span: shows `fallback` (plain Unicode) right away and swaps in typeset KaTeX once it's loaded. */
export function mathEl(tex, { display = false, fallback = '' } = {}) {
  const el = h(display ? 'div' : 'span', { class: display ? 'math display' : 'math' }, fallback || tex);
  loadKatex().then((k) => {
    if (!k) return;
    try { k.render(tex, el, { displayMode: display, throwOnError: true, strict: 'ignore', trust: false, maxExpand: 200 }); } catch { /* keep the Unicode fallback */ }
  });
  return el;
}

/** Split text into plain / $inline$ / $$display$$ parts (an escaped \$ stays a dollar sign). */
export function splitMath(text) {
  const out = []; const re = /\$\$([\s\S]+?)\$\$|(?<![\\$])\$([^$\n]+?)(?<!\\)\$/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push({ t: 'text', v: text.slice(last, m.index) });
    out.push(m[1] !== undefined ? { t: 'math', v: m[1].trim(), display: true } : { t: 'math', v: m[2].trim(), display: false });
    last = re.lastIndex;
  }
  if (last < text.length) out.push({ t: 'text', v: text.slice(last) });
  return out.map((p) => (p.t === 'text' ? { ...p, v: p.v.replace(/\\\$/g, '$') } : p));
}

/** Inline markdown-lite (**bold**, *italic*, `code`) plus $math$, built as DOM, never as HTML. */
export function inline(text) {
  const nodes = [];
  for (const part of splitMath(text)) {
    if (part.t === 'math') { nodes.push(mathEl(part.v, { display: false })); continue; }
    const re = /`([^`]+)`|\*\*([^*]+)\*\*|\*([^*\n]+)\*/g; let last = 0, m;
    while ((m = re.exec(part.v))) {
      if (m.index > last) nodes.push(part.v.slice(last, m.index));
      nodes.push(m[1] !== undefined ? h('code', m[1]) : m[2] !== undefined ? h('strong', m[2]) : h('em', m[3]));
      last = re.lastIndex;
    }
    if (last < part.v.length) nodes.push(part.v.slice(last));
  }
  return nodes;
}

/** Block markdown-lite for notes: #/##/### headings, - lists, 1. lists, > quotes, ``` code, $$ blocks, blank-line paragraphs. */
export function markdown(src) {
  const root = h('div', { class: 'md' });
  const lines = String(src).replace(/\r\n/g, '\n').split('\n');
  let i = 0, para = [], list = null;
  const flush = () => { if (para.length) { root.append(h('p', ...para.flatMap((l, k) => (k ? [h('br'), ...inline(l)] : inline(l))))); para = []; } };
  const endList = () => { list = null; };
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      flush(); endList(); const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      root.append(h('pre', h('code', buf.join('\n')))); i++; continue;
    }
    if (/^\s*\$\$\s*$/.test(line)) {
      flush(); endList(); const buf = []; i++;
      while (i < lines.length && !/^\s*\$\$\s*$/.test(lines[i])) buf.push(lines[i++]);
      root.append(mathEl(buf.join('\n'), { display: true })); i++; continue;
    }
    let m;
    if ((m = /^(#{1,3})\s+(.*)$/.exec(line))) { flush(); endList(); root.append(h(`h${m[1].length + 2}`, ...inline(m[2]))); }
    else if ((m = /^\s*[-*]\s+(.*)$/.exec(line))) { flush(); if (!list || list.tag !== 'ul') { list = { tag: 'ul', el: h('ul') }; root.append(list.el); } list.el.append(h('li', ...inline(m[1]))); }
    else if ((m = /^\s*(\d+)[.)]\s+(.*)$/.exec(line))) { flush(); if (!list || list.tag !== 'ol') { list = { tag: 'ol', el: h('ol') }; root.append(list.el); } list.el.append(h('li', ...inline(m[2]))); }
    else if ((m = /^>\s?(.*)$/.exec(line))) { flush(); endList(); root.append(h('blockquote', ...inline(m[1]))); }
    else if (/^\s*$/.test(line)) { flush(); endList(); }
    else { endList(); para.push(line); }
    i++;
  }
  flush();
  return root;
}
