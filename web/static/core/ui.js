// Reusable UI pieces. Import what you need: import { toast, modal, ... } from '/static/core/ui.js'
import { h, ico, tierIcon, num, ApiError, state, svg } from '/static/core/core.js';

// ------------------------------------------------------------ toast
export function toast(message, { title = '', kind = '', icon = null, ttl = 5200, sticky = false } = {}) {
  const host = document.getElementById('toasts');
  const el = h('div', { class: `toast ${kind}`, role: kind === 'bad' ? 'alert' : 'status' },
    icon ? (typeof icon === 'string' ? ico(icon, 28) : icon) : null,
    h('div', { class: 'grow' }, title ? h('b', title) : null, message ? h('span', message) : null));
  const close = () => { el.classList.add('out'); setTimeout(() => el.remove(), 260); };
  el.addEventListener('click', close);
  host.append(el);
  while (host.children.length > 4) host.firstChild.remove();
  if (!sticky) setTimeout(close, ttl);
  el.close = close;
  return el;
}
export const errToast = (e) => toast(e instanceof Error ? e.message : String(e), { kind: 'bad', title: 'That didn\'t work' });

// ------------------------------------------------------------ modal
export function modal({ title, content, actions = [], wide = false, cls = '', onClose } = {}) {
  const wrap = h('div', { class: 'modal-wrap' });
  const box = h('div', { class: `modal ${wide ? 'wide' : ''} ${cls}`, role: 'dialog', 'aria-modal': 'true', 'aria-label': title || 'Dialog' });
  const prev = document.activeElement;
  const close = (v) => {
    document.removeEventListener('keydown', onKey);
    wrap.remove(); prev?.focus?.(); onClose?.(v);
  };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  document.addEventListener('keydown', onKey);
  wrap.addEventListener('mousedown', (e) => { if (e.target === wrap) close(); });
  const foot = actions.length ? h('div', { class: 'row', style: { justifyContent: 'flex-end' } },
    actions.map((a) => h('button', {
      class: `btn ${a.kind || ''}`, type: 'button',
      onClick: async (e) => {
        if (!a.onClick) return close(a.value);
        const btn = e.currentTarget; btn.classList.add('busy');
        try { const r = await a.onClick(); if (r !== false) close(a.value); } catch (err) { errToast(err); } finally { btn.classList.remove('busy'); }
      },
    }, a.label))) : null;
  box.append(...[title ? h('h2', title) : null, content, foot].filter(Boolean));
  wrap.append(box); document.body.append(wrap);
  (box.querySelector('[autofocus], input, textarea, select, .btn.primary') || box).focus?.();
  return { close, el: box };
}
export function confirmBox(message, { title = 'Are you sure?', confirm = 'Confirm', danger = false } = {}) {
  return new Promise((resolve) => {
    modal({
      title, content: h('p', { class: 'mute' }, message), onClose: (v) => resolve(v === true),
      actions: [{ label: 'Cancel', value: false }, { label: confirm, kind: danger ? 'danger' : 'primary', value: true }],
    });
  });
}
/** Ask for one line of text. Resolves to the string, or null if cancelled. */
export function askText(title, { label = '', value = '', placeholder = '', confirm = 'Save', multiline = false, max = 200 } = {}) {
  return new Promise((resolve) => {
    const input = multiline ? h('textarea', { class: 'input', placeholder, maxLength: max, value }) : h('input', { class: 'input', placeholder, maxLength: max, value, autofocus: true });
    input.value = value;
    let result = null;
    const m = modal({
      title, content: h('div', { class: 'field' }, label ? h('label', label) : null, input),
      onClose: () => resolve(result),
      actions: [{ label: 'Cancel', value: null }, { label: confirm, kind: 'primary', onClick: () => { result = input.value.trim(); if (!result) return false; } }],
    });
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !multiline) { result = input.value.trim(); if (result) m.close(); } });
  });
}

// ------------------------------------------------------------ states
export function empty({ icon = 'notebook', title = 'Nothing here yet', text = '', action = null } = {}) {
  return h('div', { class: 'empty' }, ico(icon, 48), h('h3', title), text ? h('p', text) : null, action);
}
export function loadingPage(n = 3) { return h('div', { class: 'loading-page' }, Array.from({ length: n }, () => h('div', { class: 'skeleton' }))); }
export function errorBox(e, retry) {
  const msg = e instanceof ApiError || e instanceof Error ? e.message : String(e);
  return h('div', { class: 'err-box stack' }, h('b', 'Couldn\'t load this'), h('span', { class: 'mute' }, msg),
    retry ? h('div', h('button', { class: 'btn sm', onClick: retry }, 'Try again')) : null);
}

// ------------------------------------------------------------ bits
export function avatar(person, size = 36) {
  return h('img', { class: 'avatar', src: person?.avatar || '', width: size, height: size, alt: '', loading: 'lazy',
    style: { width: `${size}px`, height: `${size}px` } });
}
export const coins = (n, size = 18) => h('span', { class: 'pill', title: 'Chronocoins' }, ico('chronocoin', size), num(n));
export const xpPill = (n, size = 18) => h('span', { class: 'pill', title: 'XP' }, ico('chronos_xp', size), num(n));
export const candyPill = (n, size = 18) => h('span', { class: 'pill', title: 'Candy' }, ico('candy', size), num(n));
export function bar(frac, { color, lg = false } = {}) {
  const fill = h('i');
  const el = h('div', { class: `bar ${lg ? 'lg' : ''}`, role: 'progressbar', style: color ? { '--bar': color } : null }, fill);
  const set = (f) => { const v = Math.max(0, Math.min(1, f || 0)); el.setAttribute('aria-valuenow', Math.round(v * 100)); fill.style.width = `${v * 100}%`; };
  requestAnimationFrame(() => set(frac)); el.set = set;
  return el;
}
export function tabs(items, active, onChange) {
  const el = h('div', { class: 'tabs', role: 'tablist' });
  const paint = (id) => [...el.children].forEach((b) => b.setAttribute('aria-selected', String(b.dataset.id === id)));
  items.forEach((t) => el.append(h('button', { role: 'tab', type: 'button', dataset: { id: t.id }, onClick: () => { paint(t.id); onChange(t.id); } }, t.label)));
  paint(active); el.select = (id) => { paint(id); onChange(id); };
  return el;
}
export function chips(items, active, onChange) {
  const el = h('div', { class: 'chips' });
  const paint = (id) => [...el.children].forEach((b) => b.classList.toggle('on', b.dataset.id === id));
  items.forEach((t) => el.append(h('button', { class: 'chip', type: 'button', dataset: { id: t.id }, onClick: () => { paint(t.id); onChange(t.id); } }, t.icon ? ico(t.icon, 16) : null, t.label)));
  paint(active); return el;
}
export function field(label, input, hint) { return h('div', { class: 'field' }, h('label', label), input, hint ? h('span', { class: 'faint', style: { fontSize: '.82rem' } }, hint) : null); }
export function pageHead(title, sub, ...actions) {
  return h('div', { class: 'page-head' }, h('div', h('h1', title), sub ? h('p', sub) : null), actions.length ? h('div', { class: 'actions' }, actions) : null);
}
/** Run an async action on a button: disables it, toasts errors. Returns the result (or undefined on failure). */
export async function act(btn, fn) {
  btn?.classList.add('busy');
  try { return await fn(); } catch (e) { errToast(e); } finally { btn?.classList.remove('busy'); }
}
export function floatText(text, near) {
  const r = (near || document.body).getBoundingClientRect();
  const el = h('div', { class: 'float-up', style: { left: `${r.left + r.width / 2}px`, top: `${r.top}px` } }, text);
  document.body.append(el); setTimeout(() => el.remove(), 1500);
}
export function celebrate({ title, sub = '', tier = null, tierName = '' }) {
  return modal({
    cls: 'celebrate',
    content: h('div', { class: 'stack', style: { justifyItems: 'center' } },
      tier ? tierIcon(tier, 128) : ico('champion_crown', 96),
      h('div', { class: 'big' }, title),
      sub ? h('p', { class: 'mute' }, sub) : null,
      tierName ? h('span', { class: 'tag accent' }, tierName) : null),
    actions: [{ label: 'Nice', kind: 'primary', value: true }],
  });
}
/** Progress ring for stats: ring(fraction, {size, stroke, color}, ...centerChildren) */
export function ring(frac, { size = 96, stroke = 9, color = 'var(--accent)' } = {}, ...center) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const el = h('div', { style: { position: 'relative', width: `${size}px`, height: `${size}px`, display: 'grid', placeItems: 'center' } },
    svg('svg', { width: size, height: size, viewBox: `0 0 ${size} ${size}`, style: 'position:absolute;transform:rotate(-90deg)' },
      svg('circle', { cx: size / 2, cy: size / 2, r, fill: 'none', stroke: 'var(--s3)', 'stroke-width': stroke }),
      svg('circle', { cx: size / 2, cy: size / 2, r, fill: 'none', stroke: color, 'stroke-width': stroke, 'stroke-linecap': 'round',
        'stroke-dasharray': c, 'stroke-dashoffset': c * (1 - Math.max(0, Math.min(1, frac))), style: 'transition:stroke-dashoffset .8s var(--ease)' })),
    h('div', { style: { position: 'relative', textAlign: 'center' } }, center));
  return el;
}
export { state };
