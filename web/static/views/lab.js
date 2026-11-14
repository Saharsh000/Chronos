// The Lab DLC: Interactive Reaction Flask, Reagent Shelf, and 500-Compound Compendium.
import { state, h, get, post, mount, on, num, svg } from '/static/core/core.js';
import { toast, confirmBox, errToast, act, celebrate, pageHead, bar } from '/static/core/ui.js';

export default async function lab(root, ctx) {
  let labData = null;
  let compendiumData = null;
  let selectedCategory = 'All';
  let filterMode = 'all'; // 'all', 'craftable', 'crafted', 'uncrafted'
  let searchQuery = '';
  let flaskAtoms = { C: 0, H: 0, O: 0, N: 0, Cl: 0, F: 0, Br: 0, I: 0 };

  const loadData = async () => {
    const [l, c] = await Promise.all([
      get('/api/lab').catch(() => null),
      get('/api/lab/compendium').catch(() => null),
    ]);
    labData = l;
    compendiumData = c;
    render();
  };

  // Live element drop listener from studying sessions
  on('lab_elements_updated', (ev) => {
    if (labData && labData.unlocked && ev.elements) {
      for (const [k, v] of Object.entries(ev.elements)) {
        if (labData.elements[k] !== undefined) {
          labData.elements[k] = Math.min(labData.element_cap || 500, (labData.elements[k] || 0) + v);
        }
      }
      render();
    }
  });

  const render = () => {
    if (!labData) {
      mount(root, h('div', { class: 'pad' }, 'Loading The Lab apparatus...'));
      return;
    }

    if (!labData.unlocked) {
      renderLocked();
    } else {
      renderUnlocked();
    }
  };

  // -------------------------------------------------------------------------
  // LOCKED LAB VIEW
  // -------------------------------------------------------------------------
  const renderLocked = () => {
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
            toast('The Lab unlocked! Organic Chemistry mode and 500 synthesizable compounds are now active.', { title: 'Welcome to The Lab', kind: 'good' });
            await loadData();
          } catch (err) {
            errToast(err);
          }
        });
      },
    }, `Unlock The Lab (${num(reqCoins)} Coins)`);

    const lockedEl = h('div', { class: 'lab-locked' },
      h('h1', '⚗️ The Lab (Locked)'),
      h('p', 'The Lab is a prestigious research workshop for serious chemistry scholars. Unlock it to harvest elemental precursors and synthesize 500 authentic organic compounds across 21 categories.'),
      h('div', { class: 'lab-reqs' },
        h('div', { class: 'req-item' },
          h('div', { class: 'req-header' }, h('span', 'Chemistry Study Time'), h('span', `${chemHours.toFixed(1)}h / ${reqHours}h (${chemPct}%)`)),
          bar(chemHours, reqHours, { color: 'var(--chemistry)' })),
        h('div', { class: 'req-item' },
          h('div', { class: 'req-header' }, h('span', 'Chronocoins Balance'), h('span', `${num(coins)} / ${num(reqCoins)} (${coinsPct}%)`)),
          bar(coins, reqCoins, { color: 'var(--accent)' }))),
      h('div', { style: { marginTop: '16px' } }, unlockBtn)
    );

    mount(root, h('div', { class: 'lab-wrap' }, pageHead('The Lab', 'Unlock Organic Chemistry Mode and Compound Synthesis'), lockedEl));
  };

  // -------------------------------------------------------------------------
  // UNLOCKED LAB WORKBENCH VIEW
  // -------------------------------------------------------------------------
  const renderUnlocked = () => {
    const match = findMatchingCompound();
    const totalFlaskAtoms = Object.values(flaskAtoms).reduce((a, b) => a + b, 0);

    // =========================================================================
    // 1. REACTION FLASK APPARATUS (SVG with dynamic liquid & bubbles)
    // =========================================================================
    const flaskSvg = renderFlaskSvg(flaskAtoms, totalFlaskAtoms, match);

    // Digital readout formula
    const formattedFormula = buildFormattedFormula(flaskAtoms);

    // Stoichiometry tags in flask with direct '-' removal
    const stoichTags = Object.entries(flaskAtoms).filter(([_, cnt]) => cnt > 0).map(([elem, cnt]) => {
      return h('span', { class: `stoich-pill elem-${elem}` },
        `${elem}: ${cnt}`,
        h('span', {
          class: 'rm',
          title: `Remove 1 ${elem} from flask`,
          onClick: (e) => {
            e.stopPropagation();
            flaskAtoms[elem] = Math.max(0, flaskAtoms[elem] - 1);
            render();
          },
        }, '×')
      );
    });

    // Detector banner
    let detectorClass = 'standby';
    let detectorText = 'STANDBY: Add elements from shelf or compendium';
    if (match) {
      detectorClass = 'stable';
      detectorText = `✨ STABLE: ${match.name} (${match.category})`;
    } else if (totalFlaskAtoms > 0) {
      detectorClass = 'unstable';
      detectorText = `⚡ UNSTABLE MIXTURE: ${totalFlaskAtoms} atoms in flask`;
    }

    const flaskApparatus = h('div', {
      class: `flask-apparatus ${match ? 'has-match' : ''}`,
      style: {
        '--flask-glow': match ? '#10b981' : (totalFlaskAtoms > 0 ? getLiquidColor(flaskAtoms).c1 : 'transparent')
      }
    },
      h('div', { class: 'flask-svg-container' }, flaskSvg),
      h('div', { class: 'stirrer-base' },
        h('div', { class: 'stirrer-status' },
          h('div', { class: `stirrer-led ${match ? 'active' : (totalFlaskAtoms > 0 ? 'heating' : '')}` }),
          h('span', match ? 'REACTION READY' : (totalFlaskAtoms > 0 ? 'HEATING & STIRRING' : 'IDLE'))
        ),
        h('span', { style: { fontSize: '.72rem', color: 'var(--mute)', fontFamily: 'monospace' } },
          totalFlaskAtoms > 0 ? `${Math.min(1200, 300 + totalFlaskAtoms * 25)} RPM` : '0 RPM'
        )
      ),
      h('div', { class: 'flask-monitor' },
        h('div', { class: `hud-formula ${totalFlaskAtoms === 0 ? 'empty' : ''}` },
          formattedFormula || '[ EMPTY FLASK ]'
        ),
        h('div', { class: `reaction-detector ${detectorClass}` }, detectorText),
        stoichTags.length > 0 ? h('div', { class: 'flask-stoich-tags' }, ...stoichTags) : null
      ),
      h('div', { class: 'flask-actions' },
        match ? h('button', {
          class: 'btn-synthesize',
          onClick: async (e) => {
            await act(e.currentTarget, async () => {
              try {
                const res = await post('/api/lab/synth', { compound: match.id, confirm: true });
                celebrate();
                toast(`Synthesized ${match.name} (+${res.coins_earned} coins, +${res.xp_earned} XP)!`, { kind: 'good', title: 'Synthesis Success' });
                flaskAtoms = { C: 0, H: 0, O: 0, N: 0, Cl: 0, F: 0, Br: 0, I: 0 };
                await loadData();
              } catch (err) {
                errToast(err);
              }
            });
          },
        }, `⚗️ SYNTHESIZE ${match.name.toUpperCase()}`) : null,
        totalFlaskAtoms > 0 ? h('button', {
          class: 'btn-dump',
          title: 'Dump flask contents back to inventory',
          onClick: () => {
            flaskAtoms = { C: 0, H: 0, O: 0, N: 0, Cl: 0, F: 0, Br: 0, I: 0 };
            render();
          },
        }, '🧹 Dump Flask') : null
      )
    );

    // =========================================================================
    // 2. REAGENT DISPENSER RACK (8 Elements)
    // =========================================================================
    const vialCards = Object.keys(flaskAtoms).map((elem) => {
      const stock = labData.elements[elem] || 0;
      const cap = labData.element_cap || 500;
      const inFlask = flaskAtoms[elem] || 0;
      const available = stock - inFlask;

      return h('div', {
        class: `reagent-vial elem-${elem} ${available <= 0 ? 'depleted' : ''}`,
        title: `Click to dispense 1 ${elem} into flask (${available} available)`,
        onClick: () => {
          if (available > 0) {
            flaskAtoms[elem] = inFlask + 1;
            render();
          } else {
            toast(`No more ${elem} in stock. Study with .start oc to harvest more!`, { kind: 'bad' });
          }
        },
      },
        h('div', { class: 'vial-sym' }, elem),
        h('div', { class: 'vial-name' }, getElementName(elem)),
        h('div', { class: `vial-qty ${stock >= cap ? 'capped' : ''}` }, `${available}/${stock}`),
        h('div', { class: 'vial-quick-add' }, '+1 Atom')
      );
    });

    const leftWorkbench = h('div', { class: 'lab-panel' },
      h('div', { class: 'lab-panel-head' },
        h('h2', '⚗️ Reaction Flask'),
        h('span', { class: 'mute', style: { fontSize: '.82rem' } }, `${totalFlaskAtoms} Atoms Poured`)
      ),
      flaskApparatus,
      h('div', { class: 'lab-panel-head', style: { marginTop: '8px' } },
        h('h2', '🧪 Reagent Shelf'),
        h('span', { class: 'mute', style: { fontSize: '.82rem' } }, `Max ${labData.element_cap || 500} / elem`)
      ),
      h('div', { class: 'reagent-rack' }, ...vialCards)
    );

    // =========================================================================
    // 3. COMPENDIUM & 500-COMPOUND WORKBENCH (FULL NAMES, NO ???)
    // =========================================================================
    const allCompounds = compendiumData?.compounds || [];

    // Filter by: search query + category + filter mode
    const qLower = searchQuery.trim().toLowerCase();
    const filteredCompounds = allCompounds.filter((c) => {
      // 1. Category check
      if (selectedCategory !== 'All' && c.category !== selectedCategory) return false;

      // 2. Filter mode check
      const canCraft = canCraftCompound(c, labData.elements);
      if (filterMode === 'craftable' && !canCraft) return false;
      if (filterMode === 'crafted' && !c.discovered) return false;
      if (filterMode === 'uncrafted' && c.discovered) return false;

      // 3. Search query check
      if (qLower) {
        const nameMatch = c.name?.toLowerCase().includes(qLower);
        const formulaMatch = c.formula?.toLowerCase().includes(qLower);
        const catMatch = c.category?.toLowerCase().includes(qLower);
        const factMatch = c.fact?.toLowerCase().includes(qLower);
        const structMatch = c.structure?.toLowerCase().includes(qLower);
        if (!nameMatch && !formulaMatch && !catMatch && !factMatch && !structMatch) return false;
      }
      return true;
    });

    // Compendium Cards
    const compoundCards = filteredCompounds.map((c) => {
      const canCraft = canCraftCompound(c, labData.elements);

      // Reagent cost pills with stock check
      const reagentPills = Object.entries(c.elements || {}).filter(([_, needed]) => needed > 0).map(([elem, needed]) => {
        const userStock = labData.elements[elem] || 0;
        const hasEnough = userStock >= needed;
        return h('span', {
          class: `reagent-badge ${hasEnough ? 'have' : 'need'}`,
          title: `${elem}: need ${needed}, you have ${userStock}`
        }, `${needed}${elem}`);
      });

      return h('div', {
        class: `comp-card ${c.discovered ? 'crafted' : 'uncrafted'} ${canCraft ? 'craftable-now' : ''}`,
      },
        h('div', { class: 'card-top' },
          h('div', { class: 'card-name' }, c.name),
          c.is_your_discovery ? h('span', { class: 'card-star', title: 'Server first discovery by you!' }, '⭐') : null
        ),
        h('div', { class: 'card-formula-row' },
          h('span', { class: 'card-formula' }, c.formula),
          h('span', { class: 'card-cat-tag' }, c.category)
        ),
        c.structure && c.structure !== c.formula ? h('div', { class: 'card-structure', title: 'Condensed structural formula' }, c.structure) : null,
        h('div', { class: 'reagents-needed' }, ...reagentPills),
        h('div', { class: 'card-fact' }, `🔬 ${c.fact}`),
        h('div', { class: 'card-actions' },
          h('span', { class: `card-status-badge ${c.discovered ? 'done' : 'undone'}` },
            c.discovered ? `✅ Synthesized (${c.times_crafted}×)` : '⏳ Uncrafted'
          ),
          h('div', { class: 'row', style: { gap: '6px' } },
            h('button', {
              class: 'btn-card-load',
              title: `Load ${c.name} required elements into the flask`,
              onClick: () => {
                flaskAtoms = { ...c.elements };
                render();
                toast(`Loaded recipe for ${c.name} into reaction flask!`, { kind: 'good' });
              },
            }, '⚗️ Load Flask'),
            canCraft ? h('button', {
              class: 'btn-card-synth',
              title: `Synthesize ${c.name} immediately!`,
              onClick: async (e) => {
                await act(e.currentTarget, async () => {
                  try {
                    const res = await post('/api/lab/synth', { compound: c.id, confirm: true });
                    celebrate();
                    toast(`Synthesized ${c.name} (+${res.coins_earned} coins, +${res.xp_earned} XP)!`, { kind: 'good', title: 'Synthesis Success' });
                    await loadData();
                  } catch (err) {
                    errToast(err);
                  }
                });
              },
            }, '⚡ Quick Synth') : null
          )
        )
      );
    });

    // Category pills with compound count
    const categories = ['All', ...(compendiumData?.categories || [])];
    const catPills = categories.map((cat) => {
      const count = cat === 'All' ? allCompounds.length : allCompounds.filter((x) => x.category === cat).length;
      return h('button', {
        class: `cat-pill ${selectedCategory === cat ? 'active' : ''}`,
        onClick: () => {
          selectedCategory = cat;
          render();
        },
      }, `${cat} (${count})`);
    });

    // Quick filter mode tabs
    const filterTabs = [
      { id: 'all', label: `All (${allCompounds.length})` },
      { id: 'craftable', label: `⚡ Ready to Craft (${allCompounds.filter((x) => canCraftCompound(x, labData.elements)).length})` },
      { id: 'crafted', label: `✅ Crafted (${labData.collection_count})` },
      { id: 'uncrafted', label: `⏳ Uncrafted (${allCompounds.length - labData.collection_count})` },
    ].map((tab) => {
      return h('button', {
        class: `filter-tab ${filterMode === tab.id ? 'active' : ''}`,
        onClick: () => {
          filterMode = tab.id;
          render();
        },
      }, tab.label);
    });

    const searchInput = h('input', {
      type: 'search',
      class: 'lab-search-input',
      placeholder: 'Search 500 compounds by name, formula, or structure (e.g. caffeine, TNT, C6H6)...',
      value: searchQuery,
      onInput: (e) => {
        searchQuery = e.target.value;
        render();
      },
    });

    const rightWorkbench = h('div', { class: 'lab-panel' },
      h('div', { class: 'lab-panel-head' },
        h('h2', '📖 500-Compound Compendium'),
        h('span', { class: 'mute', style: { fontSize: '.84rem', fontWeight: 'bold' } },
          `${filteredCompounds.length} compounds shown · ${labData.collection_count} / ${labData.total_compounds} Discovered`
        )
      ),
      h('div', { class: 'comp-header-bar' },
        h('div', { class: 'comp-search-row' }, searchInput),
        h('div', { class: 'quick-filter-tabs' }, ...filterTabs),
        h('div', { class: 'cat-strip' }, ...catPills)
      ),
      h('div', { class: 'compendium-grid' }, ...compoundCards)
    );

    const layout = h('div', { class: 'lab-layout' }, leftWorkbench, rightWorkbench);

    mount(root,
      h('div', { class: 'lab-wrap' },
        pageHead('The Lab', 'Organic Chemistry Synthesis & 500-Compound Compendium'),
        layout
      )
    );
  };

  // -------------------------------------------------------------------------
  // HELPER FUNCTIONS
  // -------------------------------------------------------------------------
  const canCraftCompound = (comp, userElements) => {
    if (!comp || !comp.elements || !userElements) return false;
    for (const [elem, needed] of Object.entries(comp.elements)) {
      if ((userElements[elem] || 0) < needed) return false;
    }
    return true;
  };

  const getElementName = (sym) => {
    const names = { C: 'Carbon', H: 'Hydrogen', O: 'Oxygen', N: 'Nitrogen', Cl: 'Chlorine', F: 'Fluorine', Br: 'Bromine', I: 'Iodine' };
    return names[sym] || sym;
  };

  const buildFormattedFormula = (atoms) => {
    let res = '';
    const order = ['C', 'H', 'O', 'N', 'Cl', 'F', 'Br', 'I'];
    const subMap = { '0':'₀','1':'₁','2':'₂','3':'₃','4':'₄','5':'₅','6':'₆','7':'₇','8':'₈','9':'₉' };
    for (const e of order) {
      const cnt = atoms[e] || 0;
      if (cnt > 0) {
        const sub = cnt > 1 ? String(cnt).split('').map(d => subMap[d] || d).join('') : '';
        res += `${e}${sub} `;
      }
    }
    return res.trim();
  };

  const getLiquidColor = (atoms) => {
    // Determine dominant or special element
    if (atoms.I > 0) return { c1: '#a855f7', c2: '#6b21a8' }; // Purple iodine
    if (atoms.Br > 0) return { c1: '#ea580c', c2: '#9a3412' }; // Amber bromine
    if (atoms.Cl > 0 || atoms.F > 0) return { c1: '#22c55e', c2: '#15803d' }; // Toxic green
    if (atoms.N > 0) return { c1: '#38bdf8', c2: '#1d4ed8' }; // Cobalt cyan
    if (atoms.O > 0) return { c1: '#f43f5e', c2: '#9f1239' }; // Ruby crimson
    if (atoms.C > 0) return { c1: '#f59e0b', c2: '#b45309' }; // Cognac amber
    return { c1: '#4fd6a0', c2: '#0f766e' };
  };

  const renderFlaskSvg = (atoms, totalAtoms, match) => {
    const colors = match ? { c1: '#10b981', c2: '#047857' } : getLiquidColor(atoms);
    const maxAtomsVisual = 30;
    const liquidHeight = totalAtoms === 0 ? 0 : Math.min(145, 26 + (totalAtoms / maxAtomsVisual) * 115);
    const liquidY = 244 - liquidHeight;

    const el = document.createElement('div');
    el.className = 'flask-svg-container';
    el.innerHTML = `
      <svg class="flask-svg" viewBox="0 0 240 270" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <clipPath id="flaskInteriorClip">
            <path d="M 98 80 L 40 226 Q 34 246 56 246 L 184 246 Q 206 246 200 226 L 142 80 Z" />
          </clipPath>
          <linearGradient id="flaskLiquidGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="${colors.c1}" stop-opacity="0.95" />
            <stop offset="100%" stop-color="${colors.c2}" stop-opacity="0.98" />
          </linearGradient>
          <linearGradient id="glassGloss" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="white" stop-opacity="0.25" />
            <stop offset="50%" stop-color="white" stop-opacity="0.05" />
            <stop offset="100%" stop-color="white" stop-opacity="0.3" />
          </linearGradient>
        </defs>

        <!-- Fumes/Vapor particles when active -->
        ${totalAtoms > 0 ? `
          <ellipse cx="120" cy="20" rx="14" ry="5" fill="${colors.c1}" class="flask-vapor" />
          <ellipse cx="126" cy="12" rx="10" ry="4" fill="${colors.c2}" class="flask-vapor" />
        ` : ''}

        <!-- Flask Background Tint -->
        <path d="M 98 80 L 40 226 Q 34 246 56 246 L 184 246 Q 206 246 200 226 L 142 80 Z" fill="rgba(255,255,255,0.03)" />

        <!-- Liquid Interior (Clipped to Flask Contour) -->
        <g clip-path="url(#flaskInteriorClip)">
          ${totalAtoms > 0 ? `
            <rect x="0" y="${liquidY}" width="240" height="260" fill="url(#flaskLiquidGrad)" class="flask-liquid-path" />
            <!-- Meniscus curve -->
            <path d="M 30 ${liquidY} Q 120 ${liquidY + 4} 210 ${liquidY}" stroke="rgba(255,255,255,0.6)" stroke-width="2.5" fill="none" class="flask-meniscus" />
            <!-- Animated bubbles in chemical liquid -->
            <circle cx="80" cy="${liquidY + 25}" r="3.5" class="flask-bubble" />
            <circle cx="115" cy="${liquidY + 45}" r="4.5" class="flask-bubble" />
            <circle cx="155" cy="${liquidY + 30}" r="3" class="flask-bubble" />
            <circle cx="135" cy="${liquidY + 60}" r="5" class="flask-bubble" />
            <circle cx="95" cy="${liquidY + 70}" r="2.5" class="flask-bubble" />
          ` : ''}
        </g>

        <!-- Graduated Measurement Markings on Glass (ml) -->
        <line x1="56" y1="220" x2="74" y2="220" class="flask-grad-line" />
        <text x="78" y="222" class="flask-grad-text">50ml</text>

        <line x1="70" y1="185" x2="86" y2="185" class="flask-grad-line" />
        <text x="90" y="187" class="flask-grad-text">100ml</text>

        <line x1="84" y1="150" x2="98" y2="150" class="flask-grad-line" />
        <text x="102" y="152" class="flask-grad-text">150ml</text>

        <line x1="98" y1="115" x2="110" y2="115" class="flask-grad-line" />
        <text x="114" y="117" class="flask-grad-text">200ml</text>

        <!-- Glass Outline (Conical Erlenmeyer Body + Cylindrical Neck + Rim) -->
        <path d="M 92 24 L 148 24 Q 152 24 150 28 L 144 32 L 142 80 L 200 226 Q 206 246 184 246 L 56 246 Q 34 246 40 226 L 98 80 L 96 32 L 90 28 Q 88 24 92 24 Z" class="flask-glass-outline" />

        <!-- Specular Glass Highlights & Reflections -->
        <path d="M 194 224 L 141 84 L 141 32" class="flask-specular" />
        <path d="M 48 226 Q 42 240 60 242" stroke="rgba(255,255,255,0.4)" stroke-width="2" fill="none" />
      </svg>
    `;
    return el;
  };

  const findMatchingCompound = () => {
    if (!compendiumData?.compounds) return null;
    const totalInFlask = Object.values(flaskAtoms).reduce((a, b) => a + b, 0);
    if (totalInFlask === 0) return null;

    for (const c of compendiumData.compounds) {
      if (c.elements) {
        let match = true;
        for (const [k, v] of Object.entries(flaskAtoms)) {
          if ((c.elements[k] || 0) !== v) {
            match = false;
            break;
          }
        }
        if (match) return c;
      }
    }
    return null;
  };

  await loadData();
}
