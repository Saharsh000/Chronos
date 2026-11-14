// Chronos Web: The Lab DLC & Organic Chemistry Synthesis View
import { state, h, get, post, mount, on, num, ico, loadCss } from '/static/core/core.js';
import { toast, confirmBox, errToast, act, celebrate, pageHead, bar, tabs } from '/static/core/ui.js';

export default async function lab(root, ctx) {
  loadCss('/static/views/lab.css');

  let labData = null;
  let compendiumData = null;
  let activeCompound = null;
  let selectedCategory = 'All';
  let filterMode = 'all'; // 'all', 'ready', 'crafted', 'uncrafted'
  let searchQuery = '';

  const wrap = h('div', { class: 'lab-wrap' });
  mount(root, wrap);

  async function loadData() {
    try {
      const [l, c] = await Promise.all([
        get('/api/lab'),
        get('/api/lab/compendium'),
      ]);
      labData = l;
      compendiumData = c;

      // Pick default active compound if none selected
      if (!activeCompound && c?.compounds?.length) {
        // Pick first ready uncrafted compound, or methane
        const ready = c.compounds.find((x) => canCraft(x) && !x.discovered) ||
                      c.compounds.find((x) => canCraft(x)) ||
                      c.compounds[0];
        activeCompound = ready;
      } else if (activeCompound && c?.compounds) {
        activeCompound = c.compounds.find((x) => x.id === activeCompound.id) || activeCompound;
      }

      paint();
    } catch (err) {
      mount(wrap, h('div', { class: 'pad' }, errToast(err)));
    }
  }

  // Live element drop listener while studying
  on('lab_elements_updated', (ev) => {
    if (labData && labData.unlocked && ev.elements) {
      for (const [k, v] of Object.entries(ev.elements)) {
        if (labData.elements[k] !== undefined) {
          labData.elements[k] = Math.min(labData.element_cap || 500, (labData.elements[k] || 0) + v);
        }
      }
      paint();
    }
  });

  function canCraft(comp) {
    if (!comp || !comp.elements || !labData || !labData.elements) return false;
    for (const [elem, req] of Object.entries(comp.elements)) {
      if ((labData.elements[elem] || 0) < req) return false;
    }
    return true;
  }

  function getMissingElements(comp) {
    if (!comp || !comp.elements || !labData || !labData.elements) return [];
    const missing = [];
    for (const [elem, req] of Object.entries(comp.elements)) {
      const have = labData.elements[elem] || 0;
      if (have < req) {
        missing.push({ elem, req, have, short: req - have });
      }
    }
    return missing;
  }

  async function synthesize(compound, btn) {
    await act(btn, async () => {
      try {
        const res = await post('/api/lab/synth', { compound: compound.id, confirm: true });
        celebrate();
        toast(
          `Synthesized ${compound.name} (+${num(res.coins_earned)} coins, +${num(res.xp_earned)} XP)!`,
          { kind: 'good', title: 'Synthesis Success', icon: 'potion_flask' }
        );
        await loadData();
      } catch (err) {
        errToast(err);
      }
    });
  }

  // -------------------------------------------------------------------------
  // MAIN PAINT ROUTINE
  // -------------------------------------------------------------------------
  function paint() {
    if (!labData) return;

    if (!labData.unlocked) {
      paintLocked();
      return;
    }

    paintUnlocked();
  }

  // -------------------------------------------------------------------------
  // LOCKED VIEW
  // -------------------------------------------------------------------------
  function paintLocked() {
    const chemHours = labData.chemistry_hours || 0;
    const reqHours = labData.required_chemistry_hours || 30.0;
    const coins = labData.coins || 0;
    const reqCoins = labData.required_coins || 80000;

    const chemPct = Math.min(100, Math.round((chemHours / reqHours) * 100));
    const coinsPct = Math.min(100, Math.round((coins / reqCoins) * 100));

    const unlockBtn = h('button', {
      class: `btn lg ${labData.can_unlock ? 'primary' : 'disabled'}`,
      disabled: !labData.can_unlock,
      onClick: async (e) => {
        if (!labData.can_unlock) return;
        const ok = await confirmBox(
          `Spend ${num(reqCoins)} Chronocoins to permanently unlock The Lab and Organic Chemistry mode?`,
          { title: 'Unlock The Lab', confirm: `Unlock (${num(reqCoins)} Coins)` }
        );
        if (!ok) return;

        await act(e.currentTarget, async () => {
          try {
            await post('/api/lab/unlock');
            celebrate();
            toast('The Lab unlocked! Organic Chemistry mode is now active.', { title: 'Welcome to The Lab', kind: 'good' });
            await loadData();
          } catch (err) {
            errToast(err);
          }
        });
      },
    }, `Unlock The Lab (${num(reqCoins)} Coins)`);

    const lockedEl = h('div', { class: 'lab-locked' },
      h('h1', '⚗️ The Lab (Locked)'),
      h('p', 'The Lab is a prestigious research workshop for serious chemistry scholars. Unlock it to harvest elements while studying and synthesize 500 authentic JEE organic compounds across 21 categories.'),
      h('div', { class: 'lab-reqs' },
        h('div', { class: 'req-item' },
          h('div', { class: 'req-header' }, h('span', 'Chemistry Study Time'), h('span', `${chemHours.toFixed(1)}h / ${reqHours}h (${chemPct}%)`)),
          bar(chemHours, reqHours, { color: 'var(--chemistry)' })),
        h('div', { class: 'req-item' },
          h('div', { class: 'req-header' }, h('span', 'Chronocoins Balance'), h('span', `${num(coins)} / ${num(reqCoins)} (${coinsPct}%)`)),
          bar(coins, reqCoins, { color: 'var(--accent)' }))),
      h('div', { style: { marginTop: '16px' } }, unlockBtn)
    );

    mount(wrap, pageHead('The Lab', 'Unlock Organic Chemistry Mode and Compound Synthesis'), lockedEl);
  }

  // -------------------------------------------------------------------------
  // UNLOCKED VIEW
  // -------------------------------------------------------------------------
  function paintUnlocked() {
    const allCompounds = compendiumData?.compounds || [];
    const elements = labData.elements || {};
    const cap = labData.element_cap || 500;

    // 1. Element Shelf (Compact Horizontal Grid)
    const elemList = ['C', 'H', 'O', 'N', 'Cl', 'F', 'Br', 'I'];
    const elemNames = { C: 'Carbon', H: 'Hydrogen', O: 'Oxygen', N: 'Nitrogen', Cl: 'Chlorine', F: 'Fluorine', Br: 'Bromine', I: 'Iodine' };
    const elemTiles = elemList.map((sym) => {
      const stock = elements[sym] || 0;
      return h('div', { class: `elem-tile tile-${sym}` },
        h('span', { class: 'elem-tile-sym' }, sym),
        h('span', { class: 'elem-tile-name' }, elemNames[sym]),
        h('span', { class: `elem-tile-stock ${stock >= cap ? 'capped' : ''}` }, `${stock}/${cap}`)
      );
    });

    const shelfCard = h('div', { class: 'elem-shelf-card' },
      h('div', { class: 'elem-shelf-header' },
        h('h3', ico('potion_flask', 18), 'Reagent Precursor Stores'),
        h('span', { class: 'faint', style: { fontSize: '.8rem' } }, `Earned per minute with .start oc · Max ${cap} / elem`)
      ),
      h('div', { class: 'elem-shelf-grid' }, ...elemTiles)
    );

    // 2. Reaction Station (Compact, NOT a giant ass flask!)
    let stationEl = null;
    if (activeCompound) {
      const c = activeCompound;
      const ready = canCraft(c);
      const missing = getMissingElements(c);

      const recipeChips = Object.entries(c.elements || {}).filter(([_, req]) => req > 0).map(([sym, req]) => {
        const have = elements[sym] || 0;
        const ok = have >= req;
        return h('span', { class: `recipe-chip ${ok ? 'ok' : 'short'}` }, `${req} ${sym} (${have}/${req})`);
      });

      const synthBtn = h('button', {
        class: `btn lg ${ready ? 'primary' : 'disabled'}`,
        disabled: !ready,
        onClick: (e) => { if (ready) synthesize(c, e.currentTarget); },
      }, ready ? `⚗️ Synthesize ${c.name}` : `Need ${missing.map(m => `${m.short} ${m.elem}`).join(', ')}`);

      stationEl = h('div', { class: 'reaction-station' },
        h('div', { class: 'station-icon' }, '⚗️'),
        h('div', { class: 'station-details' },
          h('div', { class: 'station-title' },
            h('span', c.name),
            h('span', { class: 'station-formula' }, c.formula),
            c.discovered ? h('span', { class: 'tag good' }, `Crafted ${c.times_crafted}×`) : h('span', { class: 'tag' }, 'Uncrafted')
          ),
          h('div', { class: 'station-meta' },
            h('span', { class: 'card-cat' }, c.category),
            h('div', { class: 'station-recipe' }, ...recipeChips)
          ),
          c.structure && c.structure !== c.formula ? h('div', { class: 'card-struct' }, `Structure: ${c.structure}`) : null,
          h('div', { class: 'faint', style: { fontSize: '.82rem', marginTop: '2px' } }, `🔬 ${c.fact}`)
        ),
        h('div', { class: 'station-actions' }, synthBtn)
      );
    }

    // 3. Filter and Search Controls
    const readyCount = allCompounds.filter((x) => canCraft(x)).length;
    const filterTabs = [
      { id: 'all', label: `All Compounds (${allCompounds.length})` },
      { id: 'ready', label: `⚡ Ready to Craft (${readyCount})` },
      { id: 'crafted', label: `✅ Crafted (${labData.collection_count})` },
      { id: 'uncrafted', label: `⏳ Uncrafted (${allCompounds.length - labData.collection_count})` },
    ];

    const tabsEl = tabs(filterTabs, filterMode, (id) => {
      filterMode = id;
      paintCards();
    });

    const searchInput = h('input', {
      type: 'search',
      class: 'comp-search-input',
      placeholder: 'Search 500 compounds by name, formula, or structure (e.g. methane, benzene, caffeine, TNT)...',
      value: searchQuery,
    });
    searchInput.addEventListener('input', (e) => {
      searchQuery = e.target.value;
      paintCards();
    });

    // 21 Category Buttons
    const categories = ['All', ...(compendiumData?.categories || [])];
    const catButtons = categories.map((cat) => {
      const count = cat === 'All' ? allCompounds.length : allCompounds.filter((x) => x.category === cat).length;
      return h('button', {
        class: `cat-btn ${selectedCategory === cat ? 'active' : ''}`,
        type: 'button',
        onClick: () => {
          selectedCategory = cat;
          // Update active state on buttons
          catScroll.querySelectorAll('.cat-btn').forEach((b) => b.classList.remove('active'));
          catButtons[categories.indexOf(cat)].classList.add('active');
          paintCards();
        },
      }, `${cat} (${count})`);
    });
    const catScroll = h('div', { class: 'cat-scroll' }, ...catButtons);

    const controlsCard = h('div', { class: 'comp-controls' },
      h('div', { class: 'comp-search-bar' }, searchInput),
      tabsEl,
      catScroll
    );

    // 4. Specimen Grid Container
    const gridEl = h('div', { class: 'comp-grid' });

    function paintCards() {
      const qLower = searchQuery.trim().toLowerCase();
      const filtered = allCompounds.filter((c) => {
        if (selectedCategory !== 'All' && c.category !== selectedCategory) return false;
        const ready = canCraft(c);
        if (filterMode === 'ready' && !ready) return false;
        if (filterMode === 'crafted' && !c.discovered) return false;
        if (filterMode === 'uncrafted' && c.discovered) return false;

        if (qLower) {
          const matchName = c.name?.toLowerCase().includes(qLower);
          const matchFormula = c.formula?.toLowerCase().includes(qLower);
          const matchCat = c.category?.toLowerCase().includes(qLower);
          const matchStruct = c.structure?.toLowerCase().includes(qLower);
          const matchFact = c.fact?.toLowerCase().includes(qLower);
          if (!matchName && !matchFormula && !matchCat && !matchStruct && !matchFact) return false;
        }
        return true;
      });

      const cardNodes = filtered.map((c) => {
        const ready = canCraft(c);
        const missing = getMissingElements(c);

        const reagentPills = Object.entries(c.elements || {}).filter(([_, req]) => req > 0).map(([sym, req]) => {
          const have = elements[sym] || 0;
          const ok = have >= req;
          return h('span', { class: `reagent-pill ${ok ? 'have' : 'lack'}` }, `${req}${sym}`);
        });

        const synthCardBtn = h('button', {
          class: `btn sm ${ready ? 'primary' : 'disabled'}`,
          disabled: !ready,
          title: ready ? `Synthesize ${c.name}` : `Need ${missing.map(m => `${m.short} ${m.elem}`).join(', ')}`,
          onClick: (e) => {
            e.stopPropagation();
            if (ready) synthesize(c, e.currentTarget);
          },
        }, ready ? (c.discovered ? '⚗️ Re-craft' : '⚗️ Synthesize') : `Need ${missing[0]?.short || ''} ${missing[0]?.elem || ''}`);

        return h('div', {
          class: `specimen-card ${c.discovered ? 'crafted' : 'uncrafted'} ${ready ? 'ready-to-craft' : ''}`,
          onClick: () => {
            activeCompound = c;
            paintUnlocked();
            window.scrollTo({ top: 0, behavior: 'smooth' });
          },
        },
          h('div', { class: 'card-head' },
            h('span', { class: 'card-cat' }, c.category),
            h('span', { class: `card-status-pill ${c.discovered ? 'crafted' : (ready ? 'ready' : '')}` },
              c.discovered ? `✅ ${c.times_crafted}×` : (ready ? '⚡ Ready' : '⏳ Uncrafted')
            )
          ),
          h('div', { class: 'card-body' },
            h('div', { class: 'card-formula' }, c.formula),
            h('div', { class: 'card-name' }, c.name),
            c.structure && c.structure !== c.formula ? h('div', { class: 'card-struct' }, c.structure) : null,
            h('div', { class: 'card-reagents' }, ...reagentPills),
            h('div', { class: 'card-fact-box' }, c.fact)
          ),
          h('div', { class: 'card-footer' },
            h('span', { class: 'card-coins' }, ico('chronocoin', 16), c.discovered ? '+repeat' : `+bonus`),
            synthCardBtn
          )
        );
      });

      mount(gridEl, cardNodes.length ? cardNodes : h('div', { class: 'pad faint' }, 'No matching compounds found.'));
    }

    // Initial paint of cards
    paintCards();

    // Assemble page
    mount(wrap,
      pageHead(
        'The Lab',
        `Organic Chemistry Synthesis · ${labData.collection_count} / ${allCompounds.length} Discovered (${Math.round(labData.collection_count / Math.max(1, allCompounds.length) * 100)}%)`,
        h('span', { class: 'tag good' }, `Daily Cap: ${num(labData.daily?.repeat_coins || 0)} / ${num(labData.daily_repeat_cap || 5000)}`)
      ),
      shelfCard,
      stationEl,
      controlsCard,
      gridEl
    );
  }

  await loadData();
}
