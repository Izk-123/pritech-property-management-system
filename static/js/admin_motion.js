/**
 * Pritech PMS — Admin motion controller.
 *
 * Runs inside the Django admin (Unfold theme). Adds:
 *   - Staggered entry of dashboard modules, table rows, sidebar items
 *   - Ripple effect on sidebar nav clicks
 *   - Press feedback on submit buttons
 *   - Live region for realtime toasts (bridge from realtime.js)
 *
 * No external dependencies. Uses native Web Animations API.
 *
 * IMPORTANT LOADING NOTES
 * -----------------------
 * Unfold may load this script with `defer`, `async`, or via dynamic
 * injection depending on version and configuration. Any of those can
 * mean that `DOMContentLoaded` has ALREADY fired by the time this
 * script executes. To be safe we:
 *   1. Check `document.readyState` — if it is not 'loading', the DOM
 *      is already parsed and we init immediately.
 *   2. Guard every `document.body` access with a null check.
 *   3. Attach HTMX listeners at most once.
 * This prevents the "Cannot read properties of null" crash that would
 * otherwise break Alpine.js (Unfold's modal/dropdown engine) and leave
 * the "Available shortcuts" modal stuck open.
 */
(function () {
  'use strict';

  // ── Reduced-motion preference ────────────────────────────────────
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');

  // ── Utilities ────────────────────────────────────────────────────

  function $all(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function setDelay(el, ms) {
    el.style.setProperty('--pritech-delay', ms + 'ms');
  }

  function cssNumber(varName, fallback) {
    var v = getComputedStyle(document.documentElement)
      .getPropertyValue(varName)
      .trim();
    return v ? parseFloat(v) : fallback;
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }

  // ── 1. Dashboard module stagger ──────────────────────────────────

  function initDashboardStagger() {
    var modules = $all('#content .module, #content [data-admin-module]');
    if (!modules.length) return;

    var step = cssNumber('--pritech-stagger-ms', 55);
    modules.forEach(function (el, i) {
      setDelay(el, i * step);
    });
  }

  // ── 2. Table row stagger (first N rows only) ─────────────────────

  function initTableStagger() {
    $all('#result_list tbody, table tbody').forEach(function (tbody) {
      var rows = Array.prototype.slice.call(tbody.children);
      var limit = Math.min(rows.length, 25);
      for (var i = 0; i < limit; i++) {
        setDelay(rows[i], i * 32);
      }
    });
  }

  // ── 3. Sidebar nav stagger + ripple on click ─────────────────────

  function initSidebar() {
    var items = $all('#nav-sidebar li, nav.sidebar li, aside nav li');
    if (!items.length) return;

    items.forEach(function (el, i) {
      setDelay(el, i * 26);
    });

    // Attach the ripple listener only once across all boot cycles.
    if (window._pritechSidebarRippleAttached) return;
    window._pritechSidebarRippleAttached = true;

    document.addEventListener('pointerdown', function (e) {
      var a = e.target.closest('#nav-sidebar a, nav.sidebar a, aside nav a');
      if (!a) return;
      if (reduced.matches) return;

      var rect = a.getBoundingClientRect();
      var size = Math.max(rect.width, rect.height);
      var ripple = document.createElement('span');
      ripple.className = 'pritech-ripple';
      ripple.style.width = ripple.style.height = size + 'px';
      ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
      ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
      a.appendChild(ripple);
      setTimeout(function () { ripple.remove(); }, 640);
    });
  }

  // ── 4. Button press feedback ─────────────────────────────────────

  function initButtonPress() {
    if (reduced.matches) return;

    // Attach the press listener only once across all boot cycles.
    if (window._pritechButtonPressAttached) return;
    window._pritechButtonPressAttached = true;

    document.addEventListener('pointerdown', function (e) {
      var btn = e.target.closest(
        'button[type="submit"], .submit-row button, .submit-row input[type="submit"], .button'
      );
      if (!btn) return;
      btn.animate(
        [
          { transform: 'scale(1)' },
          { transform: 'scale(0.965)' },
          { transform: 'scale(1)' },
        ],
        { duration: 320, easing: 'cubic-bezier(0.34,1.56,0.64,1)' }
      );
    });
  }

  // ── 5. Form fieldset stagger ─────────────────────────────────────

  function initFieldsetStagger() {
    $all('fieldset.module, .form-row').forEach(function (el, i) {
      setDelay(el, i * 40);
    });
  }

  // ── 6. Realtime toast bridge ─────────────────────────────────────

  function initRealtimeBridge() {
    // Never touch document.body if it doesn't exist yet.
    if (!document.body) return;

    // Only run inside a tenant schema — the public schema has no
    // operational realtime traffic.
    var schema = document.body.getAttribute('data-tenant-schema');
    if (!schema || schema === 'public') return;

    // Attach only once.
    if (window._pritechRealtimeBridgeAttached) return;
    window._pritechRealtimeBridgeAttached = true;

    window.addEventListener('pritech:realtime', function (e) {
      var detail = e.detail || {};
      if (!detail.title) return;

      var colors = {
        success: '#10b981',
        error:   '#ef4444',
        warning: '#f59e0b',
        info:    '#0ea5e9',
      };
      var bg = colors[detail.type] || colors.info;

      var el = document.createElement('div');
      el.className = 'pritech-admin-toast';
      el.style.cssText =
        'position:fixed;top:16px;right:16px;z-index:9999;width:320px;' +
        'border-radius:12px;padding:12px 16px;color:#fff;' +
        'box-shadow:0 12px 40px -12px rgba(0,0,0,0.35);' +
        'font-family:Inter,system-ui,sans-serif;font-size:13px;' +
        'background:' + bg + ';opacity:0;transform:translateX(24px);' +
        'transition:opacity 220ms ease,transform 260ms cubic-bezier(0.34,1.56,0.64,1);';
      el.innerHTML =
        '<p style="font-weight:600;margin:0 0 4px 0;">' +
        escapeHtml(detail.title) +
        '</p>' +
        (detail.message
          ? '<p style="margin:0;opacity:0.92;font-size:12px;">' +
            escapeHtml(detail.message) +
            '</p>'
          : '');
      document.body.appendChild(el);

      requestAnimationFrame(function () {
        el.style.opacity = '1';
        el.style.transform = 'translateX(0)';
      });

      setTimeout(function () {
        el.style.opacity = '0';
        el.style.transform = 'translateX(24px)';
        setTimeout(function () { el.remove(); }, 300);
      }, 5200);
    });
  }

  // ── 7. HTMX listener — guarded, attached at most once ────────────

  function attachHtmxListener() {
    // Guard: body may not exist yet.
    if (!document.body) return;

    // Attach at most once — boot() runs on DOMContentLoaded AND on
    // runtime preference changes, so without this guard we'd register
    // duplicate listeners on every re-boot.
    if (window._pritechHtmxAttached) return;
    window._pritechHtmxAttached = true;

    document.body.addEventListener('htmx:afterSwap', function () {
      if (reduced.matches) return;
      initDashboardStagger();
      initTableStagger();
      initFieldsetStagger();
    });
  }

  // ── 8. Boot ──────────────────────────────────────────────────────

  function boot() {
    if (reduced.matches) return;
    initDashboardStagger();
    initTableStagger();
    initSidebar();
    initButtonPress();
    initFieldsetStagger();
    initRealtimeBridge();
  }

  function init() {
    boot();
    attachHtmxListener();
  }

  // ── 9. Lifecycle — handle every load scenario ────────────────────
  //
  // `document.readyState` states:
  //   'loading'     → document is still being parsed; wait for
  //                   DOMContentLoaded.
  //   'interactive' → DOM parsed but subresources still loading;
  //                   DOMContentLoaded may have already fired.
  //   'complete'    → everything loaded.
  //
  // If we see anything other than 'loading', DOMContentLoaded has
  // already fired or will fire synchronously after our listener is
  // added — either way we can init immediately.

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }

  // React to runtime preference changes.
  reduced.addEventListener('change', function () {
    if (!reduced.matches) boot();
  });
})();