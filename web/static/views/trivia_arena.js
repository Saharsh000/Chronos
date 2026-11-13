import { h, post, mount, ico, num, state, emit, ApiError } from '/static/core/core.js';
import { act, toast, confirmBox, coins, xpPill, candyPill, bar } from '/static/core/ui.js';
import { segs, blocks, matchTable, DIFF, subKey, clockText } from '/static/views/trivia_ui.js';

const KEYS = 'ABCDEFGH';
const TITLES = { single: 'Single correct', multiple: 'One or more correct', integer: 'Numerical value', match: 'Match the following', assertion_reason: 'Assertion and reason', statements: 'Statements' };

/**
 * One live question. Returns { el, destroy }. The server owns the clock and the answer key:
 * this only sends a token + the chosen answer and renders whatever the server reveals.
 */
export function round({ q, session, cooldownLeft, onResult, onNext, onChange, onStop, ctx }) {
  const T = q.type.id;
  const multi = T === 'multiple', integer = T === 'integer';
  const sel = new Set();
  let intVal = '', done = false, busy = false, result = null, timer = null;
  const el = h('div', { class: 'tz-round', style: { '--sc': `var(--${subKey(q.subject.id)})` } });
  const remaining = () => Math.max(0, q.deadline - (Date.now() / 1000 + state.skew));

  // ------------------------------------------------------------ header + clock
  const clockNum = h('b', { class: 'num' }, clockText(q.time_limit));
  const clockBar = bar(1);
  clockBar.classList.add('tz-clock-bar');
  const clock = h('div', { class: 'tz-clock', role: 'timer', 'aria-label': 'Time left' }, ico('focus_clock', 20), clockNum, clockBar);
  const crumbs = h('div', { class: 'tz-crumbs' }, h('span', { class: 'sub' }, q.subject.name), h('span', { class: 'sep' }, '/'), h('span', q.chapter.name), h('span', { class: 'sep' }, '/'), h('span', { class: 'topic' }, q.topic.name));
  const tags = h('div', { class: 'tz-tags' },
    h('span', { class: `tag diff-${q.difficulty}` }, DIFF[q.difficulty]),
    h('span', { class: 'tag' }, q.exam.name),
    h('span', { class: 'tag' }, TITLES[T] || q.type.name),
    h('span', { class: 'tag marks' }, h('b', { class: 'good' }, `+${q.marking.correct}`), ' / ', h('b', { class: 'bad' }, String(q.marking.incorrect))),
    q.from_cache ? h('span', { class: 'tag soft', title: 'Served instantly from the pre-generated vault' }, 'From the vault') : null,
    q.offline ? h('span', { class: 'tag soft', title: 'The live question service was unreachable, so this is from the built-in pool' }, 'Offline pool') : null);

  // ------------------------------------------------------------ question body
  const bodyEl = h('div', { class: 'tz-body' }, q.body.match ? matchTable(q.body.match) : blocks(q.body.blocks));
  const optsEl = h('div', { class: `tz-opts ${T}` });
  let intInput = null;

  function optionNode(o) {
    const content = o.pairs
      ? h('span', { class: 'pairs' }, o.pairs.map((p) => h('span', { class: 'pair' }, h('b', p.from), h('i', '→'), h('b', p.to))))
      : h('span', { class: 'txt' }, ...segs(o.segs));
    const b = h('button', { class: 'tz-opt', type: 'button', dataset: { key: o.key }, 'aria-pressed': 'false', onClick: () => pick(o.key) },
      h('span', { class: 'key' }, o.key), content, h('span', { class: 'mark' }));
    return b;
  }
  function paintOpts() {
    const ans = result?.answer?.options || [];
    optsEl.querySelectorAll('.tz-opt').forEach((b) => {
      const k = b.dataset.key, on = sel.has(k);
      b.setAttribute('aria-pressed', String(on));
      b.classList.toggle('on', on && !done);
      if (done && !result?.expired && !result?.skipped) {
        const right = ans.includes(k);
        b.classList.toggle('right', right && on); b.classList.toggle('wrong', on && !right); b.classList.toggle('missed', right && !on);
      } else if (done) b.classList.toggle('missed', ans.includes(k));
      b.disabled = done;
      b.querySelector('.mark').textContent = done ? (ans.includes(k) ? 'Correct' : on ? 'Your pick' : '') : '';
      if (done && ans.includes(k) && on) b.querySelector('.mark').textContent = 'Your pick, correct';
    });
    submit.disabled = done || busy || !ready();
  }
  const ready = () => (integer ? /^[+-]?\d{1,6}$/.test(intVal.trim()) : sel.size > 0);
  function pick(k) {
    if (done) return;
    if (multi) { sel.has(k) ? sel.delete(k) : sel.add(k); } else { sel.clear(); sel.add(k); }
    paintOpts();
  }
  if (integer) {
    intInput = h('input', { class: 'input tz-int', type: 'text', inputmode: 'numeric', autocomplete: 'off', placeholder: 'Type a whole number', 'aria-label': 'Your numerical answer', maxLength: 7 });
    intInput.addEventListener('input', () => { intVal = intInput.value.replace(/[^\d+-]/g, ''); if (intInput.value !== intVal) intInput.value = intVal; paintOpts(); });
    optsEl.append(h('div', { class: 'tz-intbox' }, intInput, h('span', { class: 'faint' }, 'Whole numbers only, like 4 or -2.')));
  } else {
    q.options.forEach((o) => optsEl.append(optionNode(o)));
  }
  const hint = h('p', { class: 'tz-hint faint' }, multi ? 'More than one option can be correct. Select all that apply.' : integer ? q.type.instructions : 'Press A to D to choose, Enter to submit.');

  // ------------------------------------------------------------ actions
  const submit = h('button', { class: 'btn primary lg', type: 'button', disabled: true, onClick: (e) => send(e.currentTarget) }, 'Submit answer');
  const skipBtn = h('button', { class: 'btn ghost', type: 'button', onClick: (e) => skip(e.currentTarget) }, ico('chronocoin', 16), `Skip for ${q.skip_cost}`);
  const actions = h('div', { class: 'tz-actions' }, submit, skipBtn);

  const fail = (e) => {
    if (e instanceof ApiError && e.code === 'no_question') { toast('This question expired on the server. Start a new one.', { kind: 'bad', title: 'Question expired' }); onChange(); return true; }
    return false;
  };
  async function send(btn) {
    if (done || busy || !ready()) return;
    busy = true; paintOpts();
    const answer = integer ? intVal.trim() : multi ? [...sel] : [...sel][0];
    try {
      const r = await act(btn, () => post('/api/trivia/answer', { token: q.token, answer }));
      if (r) finish(r);
    } catch (e) { fail(e); }
    busy = false; if (!done) paintOpts();
  }
  async function skip(btn) {
    if (done || busy) return;
    if (!(await confirmBox(`Skipping costs ${q.skip_cost} Chronocoins. You'll see the solution, but it won't count toward your marks.`, { title: 'Skip this question?', confirm: `Skip for ${q.skip_cost}` }))) return;
    busy = true;
    try {
      const r = await act(btn, () => post('/api/trivia/skip', { token: q.token }));
      if (r) finish(r);
    } catch (e) { fail(e); }
    busy = false;
  }
  async function timeUp() {
    if (done || busy) return;
    busy = true;
    for (let i = 0; i < 4 && !done; i++) {
      try { finish(await post('/api/trivia/reveal', { token: q.token })); break; }
      catch (e) { if (e.code === 'not_yet') { await new Promise((r) => setTimeout(r, 700)); continue; } if (!fail(e)) toast(e.message, { kind: 'bad' }); break; }
    }
    busy = false;
  }

  // ------------------------------------------------------------ result
  const resultEl = h('section', { class: 'tz-result', hidden: true });
  function finish(r) {
    if (done) return;
    done = true; result = r; clearInterval(timer);
    if (r.correct !== undefined) {
      session.attempted++; if (r.correct) session.correct++;
      session.marks += r.marks; session.coins += r.rewards.coins; session.xp += r.rewards.xp; session.candy += r.rewards.candy;
      session.streak = r.stats.streak;
      emit('data-changed');
    }
    if (r.skipped) session.skipped++;
    if (r.expired) session.timeouts++;
    onResult?.();
    el.classList.add('done', r.expired ? 'timeout' : r.skipped ? 'skipped' : r.correct ? 'correct' : 'wrong');
    actions.hidden = true; hint.hidden = true; if (intInput) intInput.disabled = true;
    paintOpts(); paintResult(r); clock.classList.add('stopped');
    if (r.tier_up) toast(`You reached ${r.tier_up}.`, { kind: 'good', title: 'New trivia rank', icon: 'trophy' });
    resultEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  function paintResult(r) {
    const answered = r.correct !== undefined;
    const head = r.expired ? ['Time\'s up', 'No marks lost. The solution is below.', 'pomodoro']
      : r.skipped ? ['Skipped', `Paid ${r.cost} Chronocoins. No marks either way.`, 'chronocoin']
        : r.correct ? ['Correct', `${r.marks > 0 ? '+' : ''}${r.marks} marks`, 'champion_crown'] : ['Not this time', `${r.marks} mark${Math.abs(r.marks) === 1 ? '' : 's'}`, 'streak_freeze'];
    const ansText = r.answer.integer !== null && r.answer.integer !== undefined && integer ? String(r.answer.integer) : r.answer.display;
    const nextBtn = h('button', { class: 'btn primary lg', type: 'button', onClick: (e) => onNext(e.currentTarget) }, 'Next question');
    const left = cooldownLeft();
    if (left > 0.2) {
      nextBtn.disabled = true;
      const end = Date.now() + left * 1000;
      const t = setInterval(() => { const s = Math.ceil((end - Date.now()) / 1000); if (s <= 0) { clearInterval(t); nextBtn.disabled = false; nextBtn.textContent = 'Next question'; } else nextBtn.textContent = `Next question in ${s}s`; }, 250);
      ctx.cleanup(() => clearInterval(t)); nextBtn.textContent = `Next question in ${Math.ceil(left)}s`;
    }
    resultEl.hidden = false;
    mount(resultEl,
      h('div', { class: 'tz-verdict' }, ico(head[2], 40), h('div', h('h3', head[0]), h('p', head[1]))),
      h('div', { class: 'tz-key' }, h('span', 'Correct answer'), h('b', ansText)),
      answered ? h('div', { class: 'tz-gains' }, coins(`+${r.rewards.coins}`), xpPill(`+${r.rewards.xp}`), r.rewards.candy ? candyPill(`+${r.rewards.candy}`) : null,
        h('span', { class: 'pill', title: 'Current streak' }, `Streak ${r.stats.streak}`), r.leveled_up ? h('span', { class: 'pill lvl' }, `Level ${r.new_level}`) : null) : null,
      answered ? h('div', { class: 'tz-tier' }, h('div', { class: 'row' }, h('b', r.tier.title), h('span', { class: 'faint' }, `${num(r.stats.marks)} marks, rank #${r.rank} of ${r.players}`)),
        bar(r.tier.progress / 100), r.tier.next_title ? h('span', { class: 'faint' }, `${num(r.tier.needed)} more marks to ${r.tier.next_title}`) : h('span', { class: 'faint' }, 'Top rank reached.')) : null,
      h('div', { class: 'tz-sol' }, h('h4', 'Solution'), h('div', { class: 'body' }, blocks(r.explanation)), h('p', { class: 'concept' }, h('b', 'Core concept: '), ...segs(r.concept))),
      h('div', { class: 'tz-next' }, nextBtn, h('button', { class: 'btn', type: 'button', onClick: onChange }, 'Change chapter'), h('button', { class: 'btn ghost', type: 'button', onClick: onStop }, 'End session')));
    nextBtn.focus?.();
  }

  // ------------------------------------------------------------ keyboard + clock
  const onKey = (e) => {
    if (done || e.ctrlKey || e.metaKey || e.altKey || document.querySelector('.modal-wrap')) return;
    if (integer) { if (e.key === 'Enter') send(submit); return; }
    const k = e.key.toUpperCase(), idx = '12345678'.indexOf(k);
    const key = idx >= 0 ? q.options[idx]?.key : KEYS.includes(k) && k.length === 1 ? k : null;
    if (key && q.options.some((o) => o.key === key)) { e.preventDefault(); pick(key); }
    else if (e.key === 'Enter') { e.preventDefault(); send(submit); }
  };
  document.addEventListener('keydown', onKey);
  const tick = () => {
    const r = remaining();
    clockNum.textContent = clockText(r);
    clockBar.set(r / q.time_limit);
    clock.classList.toggle('low', r <= 15); clock.classList.toggle('crit', r <= 7);
    if (r <= 0) { clearInterval(timer); timeUp(); }
  };
  timer = setInterval(tick, 250); tick();
  const destroy = () => { clearInterval(timer); document.removeEventListener('keydown', onKey); };
  ctx.cleanup(destroy);

  mount(el,
    h('div', { class: 'tz-top' }, crumbs, clock),
    h('div', { class: 'tz-card' }, tags, bodyEl, optsEl, hint, actions),
    resultEl);
  paintOpts();
  setTimeout(() => (integer ? intInput.focus() : null), 0);
  return { el, destroy };
}
