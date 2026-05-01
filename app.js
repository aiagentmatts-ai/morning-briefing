/* ═══════════════════════════════════════════════════════════
   Daily Briefings PWA — Application Logic
   Morning briefing only
   ═══════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  // ─── State ──────────────────────────────────────────────
  const state = {
    dark: false,
    screen: 'main',       // 'main' | { category object }
    scrollY: 0,
    morningData: null,
    loading: true,
    settingsOpen: false,
    lastUpdated: null,
    dataUrl: '',          // configurable base URL (empty = use ./data)
    feedback: [],         // [{ id, text, ts }]
    improvements: [],     // [{ id, title, description, source_feedback, estimated_effort }]
    improvementDecisions: {}, // { [id]: 'approved' | 'dismissed' }
    pendingDelete: null,  // feedback id awaiting confirm-tap
    toast: null,          // { text, ts } — transient flash message
  };

  // ─── Data Loading ───────────────────────────────────────
  function getDataBaseUrl() {
    return (state.dataUrl && state.dataUrl.trim()) || './data';
  }

  async function tryFetch(list) {
    for (const u of list) {
      try {
        const r = await fetch(`${u}?t=${Date.now()}`);
        if (r.ok) return await r.json();
      } catch {}
    }
    return null;
  }

  async function loadData() {
    state.loading = true;
    render();

    const base = getDataBaseUrl().replace(/\/$/, '');
    const candidates = [`${base}/morning.json`, `${base}/sample-morning.json`];

    try {
      const m = await tryFetch(candidates);
      if (m) {
        state.morningData = m;
        localStorage.setItem('db_morning', JSON.stringify(m));
      }
      state.lastUpdated = new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    } catch (e) {
      console.warn('Fetch failed', e);
    }

    if (!state.morningData) {
      try { state.morningData = JSON.parse(localStorage.getItem('db_morning')); } catch {}
    }

    state.loading = false;
    render();

    loadImprovements();
  }

  async function loadImprovements() {
    const base = getDataBaseUrl().replace(/\/$/, '');
    const data = await tryFetch([`${base}/improvements.json`]);
    if (data && Array.isArray(data.items)) {
      state.improvements = data.items;
      localStorage.setItem('db_improvements', JSON.stringify(data));
    } else {
      try {
        const cached = JSON.parse(localStorage.getItem('db_improvements') || 'null');
        if (cached && Array.isArray(cached.items)) state.improvements = cached.items;
      } catch {}
    }
    if (state.settingsOpen) render();
  }

  // ─── Persistence ────────────────────────────────────────
  function loadPrefs() {
    try {
      const saved = JSON.parse(localStorage.getItem('db_prefs') || '{}');
      if (saved.dark !== undefined) state.dark = saved.dark;
      if (saved.dataUrl !== undefined) state.dataUrl = saved.dataUrl;
    } catch {}
    applyTheme();
  }

  function savePrefs() {
    localStorage.setItem('db_prefs', JSON.stringify({
      dark: state.dark,
      dataUrl: state.dataUrl,
    }));
  }

  function applyTheme() {
    document.documentElement.setAttribute('data-theme', state.dark ? 'dark' : 'light');
  }

  function loadFeedback() {
    try {
      const raw = JSON.parse(localStorage.getItem('db_feedback') || '[]');
      if (Array.isArray(raw)) state.feedback = raw;
    } catch {}
  }

  function saveFeedback() {
    localStorage.setItem('db_feedback', JSON.stringify(state.feedback));
  }

  function loadDecisions() {
    try {
      const raw = JSON.parse(localStorage.getItem('db_improvement_decisions') || '{}');
      if (raw && typeof raw === 'object') state.improvementDecisions = raw;
    } catch {}
  }

  function saveDecisions() {
    localStorage.setItem('db_improvement_decisions', JSON.stringify(state.improvementDecisions));
  }

  function showToast(text) {
    state.toast = { text, ts: Date.now() };
    render();
    setTimeout(() => {
      if (state.toast && Date.now() - state.toast.ts >= 1900) {
        state.toast = null;
        render();
      }
    }, 2000);
  }

  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        () => showToast('Copied'),
        () => fallbackCopy(text)
      );
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      showToast('Copied');
    } catch {
      showToast('Copy failed');
    }
  }

  // ─── Helpers ────────────────────────────────────────────
  function formatDate(dateStr) {
    if (!dateStr) {
      const now = new Date();
      return now.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    }
    const d = new Date(dateStr + 'T12:00:00');
    return d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  }

  function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.slice(0, len - 1) + '…' : str;
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }

  // ─── Chevron SVG ────────────────────────────────────────
  const chevronBack = `<svg width="8" height="14" viewBox="0 0 8 14" fill="none"><path d="M7 1L1 7l6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

  // ─── Render Engine ──────────────────────────────────────
  const $ = (sel) => document.querySelector(sel);

  function render() {
    const app = $('#app');
    if (!app) return;

    const data = state.morningData;
    const dateStr = data?.date ? formatDate(data.date) : formatDate();

    app.innerHTML = `
      <div class="status-bar-spacer"></div>
      ${renderHeaderBar()}
      <div class="content-scroll" id="content-scroll">
        ${renderMasthead(dateStr)}
        ${state.loading ? renderLoading() : renderScreen(data)}
      </div>
      ${renderSettingsOverlay()}
      ${renderToast()}
    `;

    bindEvents();
  }

  function renderToast() {
    if (!state.toast) return '';
    return `<div class="toast">${escapeHtml(state.toast.text)}</div>`;
  }

  function renderHeaderBar() {
    return `
      <div class="header-bar">
        <div class="header-bar__date">${escapeHtml(new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' }))}</div>
        <div class="header-bar__actions">
          <button class="header-bar__btn" data-action="toggle-settings" aria-label="Settings">⚙</button>
        </div>
      </div>
    `;
  }

  function renderMasthead(dateStr) {
    return `
      <div class="masthead" id="masthead">
        <div class="masthead__border">
          <div class="masthead__title">Morning Briefing</div>
        </div>
        <div class="masthead__date">${escapeHtml(dateStr)}</div>
      </div>
    `;
  }

  function renderLoading() {
    return `
      <div class="loading-state">
        <div class="loading-spinner"></div>
        <div class="loading-text">Loading briefing…</div>
      </div>
    `;
  }

  function renderScreen(data) {
    if (!data) return renderEmpty();

    if (typeof state.screen === 'object') {
      return renderCategoryDetail(state.screen);
    }

    return renderMorning(data);
  }

  function renderEmpty() {
    return `
      <div class="empty-state">
        <div class="empty-state__icon">☀️</div>
        <div class="empty-state__title">No briefing available</div>
        <div class="empty-state__subtitle">Today's morning briefing hasn't been generated yet.</div>
      </div>
    `;
  }

  // ═══════════════════════════════════════════════════════════
  // FULL VIEW — newspaper layout
  // ═══════════════════════════════════════════════════════════

  function renderMorning(data) {
    const sections = data.sections || [];
    const topSection = sections[0];
    const topStory = topSection?.stories?.[0];

    return `
      <div class="screen content-padding">
        ${topStory ? `
          <div class="top-story">
            <div class="top-story__label">Top Story</div>
            <div class="top-story__content" data-action="open-category" data-index="0">
              <div class="top-story__headline">${escapeHtml(topStory.headline)}</div>
              ${topStory.summary ? `<div class="top-story__summary">${escapeHtml(topStory.summary)}</div>` : ''}
              <div class="top-story__meta">
                <span class="top-story__source">${escapeHtml(topStory.source || '')} · ${escapeHtml(topStory.time || '')}</span>
                <span class="top-story__category">${escapeHtml(topSection.label)} →</span>
              </div>
            </div>
          </div>
        ` : ''}

        <div class="category-grid-header">
          <div class="category-grid-header__label">All Sections</div>
        </div>
        <div class="category-grid">
          ${sections.map((cat, i) => {
            const isRight = i % 2 === 1;
            const isLastRow = i >= sections.length - 2;
            const isLastSingle = sections.length % 2 === 1 && i === sections.length - 1;
            return `
              <div class="category-cell ${isRight ? 'category-cell--right' : ''} ${!isRight ? 'category-cell--border-right' : ''} ${!isLastRow && !isLastSingle ? 'category-cell--border-bottom' : ''}"
                   data-action="open-category" data-index="${i}">
                <div class="category-cell__top">
                  <div class="category-cell__name">${escapeHtml(cat.label)}</div>
                  <div class="category-cell__badge">${cat.count || cat.stories?.length || 0}</div>
                </div>
                <div class="category-cell__preview">${escapeHtml(truncate(cat.stories?.[0]?.headline || '', 65))}</div>
              </div>
            `;
          }).join('')}
        </div>

        ${renderMarketTable(data)}

        ${state.lastUpdated ? `<div class="last-updated">Updated ${state.lastUpdated}</div>` : ''}
      </div>
    `;
  }

  function renderMarketTable(data) {
    const md = data?.market_data;
    if (!md?.rows?.length) return '';
    return `
      <div class="market-table">
        <div class="market-table__header">
          <div class="market-table__title">Energy Markets</div>
          ${md.as_of ? `<div class="market-table__as-of">${escapeHtml(md.as_of)}</div>` : ''}
        </div>
        <table class="market-table__grid">
          <tbody>
            ${md.rows.map(r => {
              const ch = (r.change || '').trim();
              const dir = ch.startsWith('+') ? 'up' : ch.startsWith('-') ? 'down' : 'flat';
              return `
                <tr class="market-table__row">
                  <td class="market-table__name">${escapeHtml(r.market || '')}</td>
                  <td class="market-table__price">${escapeHtml(r.price || '')}</td>
                  <td class="market-table__change market-table__change--${dir}">${escapeHtml(ch)}</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderCategoryDetail(cat) {
    return `
      <div class="screen screen--slide-in content-padding">
        <div class="category-back" data-action="go-back">
          ${chevronBack}
          <span class="category-back__text">Briefing</span>
        </div>
        <div class="category-detail">
          <div class="category-detail__count">${cat.count || cat.stories?.length || 0} Stories</div>
          <div class="category-detail__title">${escapeHtml(cat.label)}</div>
        </div>
        ${(cat.stories || []).map(s => `
          <div class="story-item">
            <div class="story-item__headline">
              ${escapeHtml(s.headline)}
              ${s.flagged ? '<span class="story-item__flag">⚡</span>' : ''}
            </div>
            ${s.summary ? `<div class="story-item__summary">${escapeHtml(s.summary)}</div>` : ''}
            <div class="story-item__meta">
              <span class="story-item__source">${escapeHtml(s.source || '')}</span>
              <span class="story-item__dot">·</span>
              <span class="story-item__time">${escapeHtml(s.time || '')}</span>
              ${s.url ? `<a class="story-item__link" href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">Read →</a>` : ''}
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  // ─── Settings Overlay ───────────────────────────────────
  function renderSettingsOverlay() {
    return `
      <div class="settings-overlay ${state.settingsOpen ? 'settings-overlay--visible' : ''}" id="settings-overlay">
        <div class="settings-panel">
          <div class="settings-panel__handle"></div>
          <div class="settings-panel__title">Settings</div>

          <div class="settings-row">
            <span class="settings-row__label">Dark Mode</span>
            <button class="toggle-switch ${state.dark ? 'toggle-switch--on' : ''}"
                    data-action="toggle-dark">
              <div class="toggle-switch__knob"></div>
            </button>
          </div>

          <div class="settings-row settings-row--stack">
            <span class="settings-row__label">Briefings URL</span>
            <input class="settings-row__input"
                   type="text"
                   inputmode="url"
                   placeholder="./data  (or https://you.github.io/repo/data)"
                   value="${escapeHtml(state.dataUrl)}"
                   data-action="set-data-url" />
            <span class="settings-row__hint">Base URL holding morning.json</span>
          </div>

          <div class="settings-row">
            <span class="settings-row__label">Refresh</span>
            <button class="settings-row__action" data-action="refresh">Reload now</button>
          </div>

          <hr class="settings-divider" />

          ${renderFeedbackSection()}

          <hr class="settings-divider" />

          ${renderImprovementsSection()}

          ${renderApprovedSection()}
        </div>
      </div>
    `;
  }

  function renderFeedbackSection() {
    const items = state.feedback || [];
    return `
      <div class="settings-panel__title">Report a bug or idea</div>

      <div class="settings-row settings-row--stack">
        <textarea class="feedback-textarea"
                  id="feedback-textarea"
                  rows="4"
                  placeholder="What broke, what's clunky, what would you like to see?"></textarea>
        <div class="feedback-actions">
          <button class="settings-row__action" data-action="add-feedback">Add to inbox</button>
        </div>
      </div>

      <div class="feedback-inbox-header">
        <span class="feedback-inbox-header__count">Inbox · ${items.length} ${items.length === 1 ? 'item' : 'items'}</span>
        ${items.length ? `<button class="feedback-inbox-header__copy" data-action="copy-feedback-inbox">Copy ⧉</button>` : ''}
      </div>

      ${items.length === 0 ? `
        <div class="feedback-empty">No feedback yet. Type a bug or idea above and tap Add.</div>
      ` : `
        <div class="feedback-list">
          ${items.map(item => `
            <div class="feedback-list__row">
              <div class="feedback-list__date">${escapeHtml(formatShortDate(item.ts))}</div>
              <div class="feedback-list__text">${escapeHtml(item.text)}</div>
              <button class="feedback-list__delete ${state.pendingDelete === item.id ? 'feedback-list__delete--pending' : ''}"
                      data-action="delete-feedback"
                      data-id="${escapeHtml(item.id)}">${state.pendingDelete === item.id ? 'Tap again' : '✕'}</button>
            </div>
          `).join('')}
        </div>
      `}
    `;
  }

  function renderImprovementsSection() {
    const items = state.improvements || [];
    const decisions = state.improvementDecisions || {};
    const suggested = items.filter(it => !decisions[it.id]);

    return `
      <div class="settings-panel__title">
        Suggested improvements
        ${suggested.length ? `<span class="settings-panel__count">${suggested.length} new</span>` : ''}
      </div>

      ${suggested.length === 0 ? `
        <div class="feedback-empty">No suggestions yet. After you copy your inbox to Claude, suggestions will show up here.</div>
      ` : `
        <div class="improvement-list">
          ${suggested.map(it => `
            <div class="improvement-card">
              <div class="improvement-card__title">${escapeHtml(it.title || '')}</div>
              ${it.description ? `<div class="improvement-card__body">${escapeHtml(it.description)}</div>` : ''}
              ${Array.isArray(it.source_feedback) && it.source_feedback.length ? `
                <div class="improvement-card__source">From: ${it.source_feedback.map(s => `"${escapeHtml(s)}"`).join(' · ')}</div>
              ` : ''}
              <div class="improvement-card__actions">
                <button class="improvement-card__btn improvement-card__btn--pick"
                        data-action="pick-improvement" data-id="${escapeHtml(it.id)}">Pick ✓</button>
                <button class="improvement-card__btn improvement-card__btn--dismiss"
                        data-action="dismiss-improvement" data-id="${escapeHtml(it.id)}">Dismiss ✕</button>
              </div>
            </div>
          `).join('')}
        </div>
      `}
    `;
  }

  function renderApprovedSection() {
    const items = state.improvements || [];
    const decisions = state.improvementDecisions || {};
    const approved = items.filter(it => decisions[it.id] === 'approved');
    if (!approved.length) return '';

    return `
      <hr class="settings-divider" />
      <div class="settings-panel__title">
        Approved — ready to build
        <span class="settings-panel__count">${approved.length} ${approved.length === 1 ? 'item' : 'items'}</span>
      </div>

      <div class="approved-list">
        ${approved.map(it => `
          <div class="approved-list__row">
            <span class="approved-list__check">✓</span>
            <span class="approved-list__title">${escapeHtml(it.title || '')}</span>
            <button class="approved-list__undo"
                    data-action="unpick-improvement"
                    data-id="${escapeHtml(it.id)}"
                    aria-label="Move back to suggestions">↩</button>
          </div>
        `).join('')}
      </div>

      <div class="feedback-actions feedback-actions--full">
        <button class="settings-row__action" data-action="copy-approved-list">Copy approved list to clipboard ⧉</button>
      </div>
    `;
  }

  function formatShortDate(ts) {
    if (!ts) return '';
    try {
      const d = new Date(ts);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch { return ''; }
  }

  // ─── Event Binding ──────────────────────────────────────
  function bindEvents() {
    const scroll = $('#content-scroll');
    const masthead = $('#masthead');
    if (scroll && masthead) {
      scroll.addEventListener('scroll', () => {
        const y = scroll.scrollTop;
        masthead.style.opacity = Math.max(0, 1 - y / 60);
      }, { passive: true });
    }

    const overlay = $('#settings-overlay');
    if (overlay) {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
          state.settingsOpen = false;
          render();
        }
      });
    }

    const urlInput = document.querySelector('.settings-row__input');
    if (urlInput) {
      urlInput.addEventListener('change', (e) => {
        state.dataUrl = e.target.value.trim();
        savePrefs();
        loadData();
      });
    }
  }

  function handleClick(e) {
    const target = e.target.closest('[data-action]');
    if (!target) return;

    if (target.tagName === 'INPUT') return;

    const action = target.dataset.action;

    switch (action) {
      case 'open-category': {
        const idx = parseInt(target.dataset.index);
        const data = state.morningData;
        if (data?.sections?.[idx]) {
          state.screen = data.sections[idx];
          render();
          const scroll = $('#content-scroll');
          if (scroll) scroll.scrollTop = 0;
        }
        break;
      }

      case 'go-back': {
        state.screen = 'main';
        render();
        break;
      }

      case 'toggle-settings': {
        state.settingsOpen = !state.settingsOpen;
        render();
        break;
      }

      case 'toggle-dark': {
        state.dark = !state.dark;
        applyTheme();
        savePrefs();
        render();
        break;
      }

      case 'refresh': {
        loadData();
        break;
      }

      case 'add-feedback': {
        const ta = document.getElementById('feedback-textarea');
        const text = (ta?.value || '').trim();
        if (!text) return;
        const entry = {
          id: 'fb_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7),
          text,
          ts: Date.now(),
        };
        state.feedback.unshift(entry);
        saveFeedback();
        render();
        break;
      }

      case 'delete-feedback': {
        const id = target.dataset.id;
        if (state.pendingDelete !== id) {
          state.pendingDelete = id;
          render();
          setTimeout(() => {
            if (state.pendingDelete === id) {
              state.pendingDelete = null;
              render();
            }
          }, 2500);
        } else {
          state.feedback = state.feedback.filter(f => f.id !== id);
          state.pendingDelete = null;
          saveFeedback();
          render();
        }
        break;
      }

      case 'copy-feedback-inbox': {
        const items = state.feedback || [];
        if (!items.length) return;
        const today = new Date().toISOString().slice(0, 10);
        const lines = items.map(it => {
          const d = new Date(it.ts).toISOString().slice(0, 10);
          return `- ${d} — ${it.text}`;
        });
        const payload =
          `Briefing app feedback (${items.length} ${items.length === 1 ? 'item' : 'items'}, exported ${today}):\n` +
          lines.join('\n') +
          `\n\nPlease update data/improvements.json with proposed improvements.`;
        copyToClipboard(payload);
        break;
      }

      case 'pick-improvement': {
        const id = target.dataset.id;
        state.improvementDecisions[id] = 'approved';
        saveDecisions();
        render();
        break;
      }

      case 'dismiss-improvement': {
        const id = target.dataset.id;
        state.improvementDecisions[id] = 'dismissed';
        saveDecisions();
        render();
        break;
      }

      case 'unpick-improvement': {
        const id = target.dataset.id;
        delete state.improvementDecisions[id];
        saveDecisions();
        render();
        break;
      }

      case 'copy-approved-list': {
        const decisions = state.improvementDecisions || {};
        const approved = (state.improvements || []).filter(it => decisions[it.id] === 'approved');
        if (!approved.length) return;
        const lines = approved.map((it, i) => `${i + 1}. ${it.title}${it.description ? ' — ' + it.description : ''}`);
        const payload = `Approved improvements to implement:\n` + lines.join('\n');
        copyToClipboard(payload);
        break;
      }
    }
  }

  document.addEventListener('click', handleClick);

  // ─── Init ───────────────────────────────────────────────
  function init() {
    loadPrefs();
    loadFeedback();
    loadDecisions();
    render();
    loadData();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
