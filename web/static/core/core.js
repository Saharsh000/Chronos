// Core helpers: state/bus, API client, DOM builder, formatters, icons.
export const state = {
  me: null,          // /api/me payload
  guild: null,       // current guild id (string)
  session: null,     // /api/session payload (kept fresh by app.js)
  skew: 0,           // serverNow - clientNow (seconds)
  bus: new EventTarget(),
};

export function emit(name, detail) { state.bus.dispatchEvent(new CustomEvent(name, { detail })); }
export function on(name, fn) {
  const f = (e) => fn(e.detail);
  state.bus.addEventListener(name, f);
  return () => state.bus.removeEventListener(name, f);
}
export const nowSec = () => Math.floor(Date.now() / 1000 + state.skew);

// ---------------------------------------------------------------- API
export class ApiError extends Error {
  constructor(message, status = 0, code = 'error', data = null) {
    super(message); this.status = status; this.code = code; this.data = data;
  }
}

export async function api(method, path, body) {
  const headers = { 'X-Requested-With': 'chronos' };
  if (state.guild) headers['X-Guild'] = state.guild;
  const init = { method, headers, credentials: 'same-origin' };
  if (body !== undefined) { headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
  let res;
  try { res = await fetch(path, init); }
  catch { throw new ApiError("Can't reach Chronos. Check your connection.", 0, 'network'); }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    if (res.status === 401) emit('unauth');
    throw new ApiError(data?.error || `Request failed (${res.status})`, res.status, data?.code, data);
  }
  if (data && typeof data.now === 'number') state.skew = data.now - Date.now() / 1000;
  return data;
}
export const qs = (o = {}) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '') p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : '';
};
export const get = (path, params) => api('GET', path + qs(params));
export const post = (path, body = {}) => api('POST', path, body);
export const patch = (path, body = {}) => api('PATCH', path, body);
export const del = (path, body) => api('DELETE', path, body);

// ---------------------------------------------------------------- DOM
const PROPS = new Set(['value', 'checked', 'disabled', 'selected', 'hidden', 'indeterminate']);
function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}
function setAttrs(el, attrs) {
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') { for (const [sk, sv] of Object.entries(v)) { if (sk.startsWith('--')) el.style.setProperty(sk, sv); else el.style[sk] = sv; } }
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (PROPS.has(k)) el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
}
const isAttrs = (a) => a && typeof a === 'object' && !(a instanceof Node) && !Array.isArray(a);
/** h('div', {class:'x', onClick}, child, 'text', [more]) — text is always escaped. */
export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  if (isAttrs(attrs)) setAttrs(el, attrs); else kids.unshift(attrs);
  append(el, kids);
  return el;
}
export function svg(tag, attrs, ...kids) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  if (isAttrs(attrs)) {
    for (const [k, v] of Object.entries(attrs)) if (v != null && v !== false) el.setAttribute(k, v);
  } else kids.unshift(attrs);
  append(el, kids);
  return el;
}
export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];
export const mount = (root, ...nodes) => root.replaceChildren(...nodes.flat(Infinity).filter(Boolean));

// ---------------------------------------------------------------- formats
const p2 = (n) => String(Math.floor(n)).padStart(2, '0');
export function clock(sec) {
  sec = Math.max(0, Math.floor(sec));
  return `${p2(sec / 3600)}:${p2((sec % 3600) / 60)}:${p2(sec % 60)}`;
}
export function dur(sec) {
  sec = Math.max(0, Math.round(sec));
  if (sec < 60) return `${sec}s`;
  const h_ = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
  if (h_ === 0) return `${m}m`;
  return m ? `${h_}h ${p2(m)}m` : `${h_}h`;
}
export const num = (n) => Number(n || 0).toLocaleString('en-IN');
export function ago(ts) {
  const d = nowSec() - ts;
  if (d < 45) return 'just now';
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}
const TZ = 'Asia/Kolkata';
export const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', timeZone: TZ });
export const fmtDate = (ts) => new Date(ts * 1000).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: TZ });
/** Always show a block as start – end (never end alone). */
export const timeRange = (a, b) => `${fmtTime(a)} – ${fmtTime(b)}`;
export const pct = (a, b) => (b > 0 ? Math.max(0, Math.min(1, a / b)) : 0);
export const plural = (n, w) => `${num(n)} ${w}${n === 1 ? '' : 's'}`;

// ---------------------------------------------------------------- icons
const ICON_SIZES = [16, 32, 64, 128, 256];
export function iconUrl(name, size = 32) {
  if (name.startsWith('food/')) return `/assets/icons/${name}.png`;   // food art ships at one size
  const s = ICON_SIZES.find((x) => x >= size) || 256;
  return `/assets/icons/${name}_${s}.png`;
}
/** Pixel-art icon from the bot's assets, e.g. ico('chronocoin', 24). */
export function ico(name, size = 24, cls = '') {
  const img = h('img', { class: `ico ${cls}`, src: iconUrl(name, size), width: size, height: size, alt: '', loading: 'lazy' });
  img.addEventListener('error', () => { img.src = `/assets/icons/${name}.png`; }, { once: true });
  return img;
}
export function tierIcon(key, size = 32, cls = '') {
  const s = ICON_SIZES.find((x) => x >= size) || 128;
  const img = h('img', { class: `ico tier ${cls}`, src: `/assets/icons/tiers/${key}_${s}.png`, width: size, height: size, alt: '' });
  img.addEventListener('error', () => { img.src = `/assets/icons/tiers/${key}.png`; }, { once: true });
  return img;
}
export const SUBJECTS = {
  physics: { label: 'Physics', icon: 'subject_physics', color: 'var(--physics)' },
  chemistry: { label: 'Chemistry', icon: 'subject_chemistry', color: 'var(--chemistry)' },
  maths: { label: 'Maths', icon: 'subject_maths', color: 'var(--maths)' },
};
export function guard(fn) {   // run an async handler, toast errors
  return async (...a) => { try { return await fn(...a); } catch (e) { (await import('/static/core/ui.js')).toast(e.message, { kind: 'bad' }); } };
}
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const debounce = (fn, ms = 300) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

/** Load a view's own stylesheet once: loadCss('/static/views/shop.css') */
export function loadCss(href) {
  if (document.querySelector(`link[href="${href}"]`)) return;
  document.head.append(h('link', { rel: 'stylesheet', href }));
}
