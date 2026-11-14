// The Lab DLC interactive view: Element Tray, Reaction Flask, and 100-Compound Compendium.
import { state, h, get, post, mount, on, num } from '/static/core/core.js';
import { toast, confirmBox, errToast, act, celebrate, pageHead, bar } from '/static/core/ui.js';

export default async function lab(root, ctx) {
  let labData = null;
  let compendiumData = null;
  let selectedCategory = 'All';
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

  // Live element drop listener
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
      mount(root, h('div', { class: 'pad' }, 'Loading The Lab...'));
      return;
    }

    if (!labData.unlocked) {
      renderLocked();
    } else {
      renderUnlocked();
    }
  };

  const renderLocked = () => {
    const chemHours = labData.chemistry_hours || 0;
    const reqHours = labData.required_chemistry_hours || 30.0;
    const coins = labData.coins || 0;
    const reqCoins = labData.required_coins || 60000;

    const chemPct = Math.min(100, Math.round((chemHours / reqHours) * 100));
    const coinsPct = Math.min(100, Math.round((coins / reqCoins) * 100));

    const unlockBtn = h('button', {
      class: `btn lg ${labData.can_unlock ? 'primary' : 'disabled'}`,
      disabled: !labData.can_unlock,
      onClick: async (e) => {
        if (!labData.can_unlock) return;
        const ok = await confirmBox(
          'Spend 60,000 Chronocoins to permanently unlock The Lab and Organic Chemistry mode?',
          { title: 'Unlock The Lab', confirm: 'Unlock (60,000 Coins)' }
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
    }, 'Unlock The Lab (60,000 Coins)');

    const lockedEl = h('div', { class: 'lab-locked' },
      h('h1', 'The Lab (Locked)'),
      h('p', 'The Lab is a prestigious research workshop for serious chemistry scholars. Unlock it to harvest elements and synthesize 100 JEE organic compounds.'),
      h('div', { class: 'lab-reqs' },
        h('div', { class: 'req-item' },
          h('div', { class: 'req-header' }, h('span', 'Chemistry Study Time'), h('span', `${chemHours.toFixed(1)}h / ${reqHours}h (${chemPct}%)`)),
          bar(chemHours, reqHours, { color: 'var(--accent)' })),
        h('div', { class: 'req-item' },
          h('div', { class: 'req-header' }, h('span', 'Chronocoins Balance'), h('span', `${num(coins)} / ${num(reqCoins)} (${coinsPct}%)`)),
          bar(coins, reqCoins, { color: 'var(--accent)' }))),
      h('div', { style: { marginTop: '16px' } }, unlockBtn)
    );

    mount(root, h('div', { class: 'lab-wrap' }, pageHead('The Lab', 'Unlock Organic Chemistry mode and synthesis'), lockedEl));
  };

  const renderUnlocked = () => {
    // Check if current flask matches any compound
    const match = findMatchingCompound();

    // 1. Element Tray
    const elemCards = Object.keys(flaskAtoms).map((elem) => {
      const stock = labData.elements[elem] || 0;
      const cap = labData.element_cap || 500;
      const inFlask = flaskAtoms[elem] || 0;
      const available = stock - inFlask;

      return h('div', {
        class: `elem-card ${available <= 0 ? 'disabled' : ''}`,
        onClick: () => {
          if (available > 0) {
            flaskAtoms[elem] = inFlask + 1;
            render();
          } else {
            toast(`No more ${elem} available in stock. Study with .start oc to harvest more!`, { kind: 'bad' });
          }
        },
      },
        h('div', { class: 'elem-sym' }, elem),
        h('div', { class: 'elem-name' }, getElementName(elem)),
        h('div', { class: `elem-count ${stock >= cap ? 'capped' : ''}` }, `${available}/${stock}`)
      );
    });

    // 2. Reaction Flask formula & tags
    const flaskTags = Object.entries(flaskAtoms).filter(([_, cnt]) => cnt > 0).map(([elem, cnt]) => {
      return h('span', { class: 'atom-tag' },
        `${elem}: ${cnt}`,
        h('span', {
          class: 'rm',
          title: `Remove 1 ${elem}`,
          onClick: (e) => {
            e.stopPropagation();
            flaskAtoms[elem] = Math.max(0, flaskAtoms[elem] - 1);
            render();
          },
        }, '×')
      );
    });

    const formulaStr = buildFormulaString(flaskAtoms);

    const flaskEl = h('div', { class: `reaction-flask ${match ? 'match' : ''}` },
      h('div', { class: 'flask-formula' }, formulaStr ? formulaStr : h('span', { class: 'placeholder' }, 'Click elements above to add atoms...')),
      flaskTags.length > 0 ? h('div', { class: 'flask-atom-tags' }, ...flaskTags) : null,
      match ? h('div', { class: 'flask-match-banner' }, `MATCH: ${match.name} (${match.category})`) : null,
      h('div', { class: 'row', style: { justifyContent: 'center', gap: '10px', marginTop: '10px' } },
        match ? h('button', {
          class: 'btn primary',
          onClick: async (e) => {
            await act(e.currentTarget, async () => {
              try {
                const res = await post('/api/lab/synth', { compound: match.id, confirm: true });
                celebrate();
                toast(`Synthesized ${match.name} (+${res.coins_earned} coins, +${res.xp_earned} XP)!`, { kind: 'good', title: 'Synthesis Success' });
                // Reset flask
                flaskAtoms = { C: 0, H: 0, O: 0, N: 0, Cl: 0, F: 0, Br: 0, I: 0 };
                await loadData();
              } catch (err) {
                errToast(err);
              }
            });
          },
        }, `Synthesize ${match.name}`) : null,
        flaskTags.length > 0 ? h('button', {
          class: 'btn secondary',
          onClick: () => {
            flaskAtoms = { C: 0, H: 0, O: 0, N: 0, Cl: 0, F: 0, Br: 0, I: 0 };
            render();
          },
        }, 'Clear Flask') : null
      )
    );

    // 3. Compendium Grid
    const categories = ['All', ...(compendiumData?.categories || [])];
    const catPills = categories.map((cat) => {
      return h('button', {
        class: `cat-pill ${selectedCategory === cat ? 'active' : ''}`,
        onClick: () => {
          selectedCategory = cat;
          render();
        },
      }, cat);
    });

    const filteredCompounds = (compendiumData?.compounds || []).filter((c) => {
      if (selectedCategory === 'All') return true;
      return c.category === selectedCategory;
    });

    const compoundCards = filteredCompounds.map((c) => {
      if (!c.discovered) {
        return h('div', {
          class: 'comp-card undiscovered',
          title: 'Undiscovered compound. Experiment in the flask to reveal!',
        },
          h('div', { class: 'title' }, h('span', '???'), h('span', { class: 'cat' }, c.category)),
          h('div', { class: 'fact' }, `Atoms: ${c.total_atoms} · Craft to reveal formula and JEE fact.`)
        );
      }

      return h('div', {
        class: 'comp-card discovered',
        onClick: () => {
          // Pre-load required atoms into flask if in stock
          if (c.elements) {
            flaskAtoms = { ...c.elements };
            render();
            toast(`Loaded ${c.name} recipe into reaction flask!`, { kind: 'good' });
          }
        },
      },
        h('div', { class: 'title' },
          h('span', c.name),
          c.is_your_discovery ? h('span', { class: 'disc-star', title: 'Server first discovery by you!' }, '⭐') : null
        ),
        h('div', { class: 'formula' }, c.formula),
        h('div', { class: 'cat' }, c.category),
        h('div', { class: 'fact' }, c.fact),
        h('div', { class: 'times' }, `Crafted: ${c.times_crafted}x`)
      );
    });

    // Assemble Layout
    const leftPanel = h('div', { class: 'lab-panel' },
      h('div', { class: 'lab-panel-head' },
        h('h2', 'Element Stores'),
        h('span', { class: 'mute', style: { fontSize: '.85rem' } }, `Max ${labData.element_cap || 500} / elem`)),
      h('div', { class: 'element-tray' }, ...elemCards),
      h('div', { class: 'lab-panel-head', style: { marginTop: '10px' } }, h('h2', 'Reaction Flask')),
      flaskEl
    );

    const rightPanel = h('div', { class: 'lab-panel' },
      h('div', { class: 'lab-panel-head' },
        h('h2', 'Compendium'),
        h('span', { class: 'mute', style: { fontSize: '.85rem' } }, `${labData.collection_count} / ${labData.total_compounds} Discovered`)),
      h('div', { class: 'cat-filters' }, ...catPills),
      h('div', { class: 'compendium-grid' }, ...compoundCards)
    );

    const layout = h('div', { class: 'lab-layout' }, leftPanel, rightPanel);

    mount(root,
      h('div', { class: 'lab-wrap' },
        pageHead('The Lab', 'Organic Chemistry Synthesis & Compendium'),
        layout
      )
    );
  };

  const getElementName = (sym) => {
    const names = { C: 'Carbon', H: 'Hydrogen', O: 'Oxygen', N: 'Nitrogen', Cl: 'Chlorine', F: 'Fluorine', Br: 'Bromine', I: 'Iodine' };
    return names[sym] || sym;
  };

  const buildFormulaString = (atoms) => {
    let res = '';
    const order = ['C', 'H', 'O', 'N', 'Cl', 'F', 'Br', 'I'];
    for (const e of order) {
      const cnt = atoms[e] || 0;
      if (cnt > 0) {
        res += e + (cnt > 1 ? cnt : '');
      }
    }
    return res;
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
