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
 */
(function () {
  'use strict';

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');

  /* ── Utilities ───────────────────────────────────────────────── */

  function $all(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function setDelay(el, ms) {
    el.style.setProperty('--pritech-delay', ms + 'ms');
  }

  function cssNumber(varName, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
    return v ? parseFloat(v) : fallback;
  }

  /* ── 1. Dashboard module stagger ─────────────────────────────── */

  function initDashboardStagger() {
    var modules = $all('#content .module, #content [data-admin-module]');
    if (!modules.length) return;

    var step = cssNumber('--pritech-stagger-ms', 55);
    modules.forEach(function (el, i) {
      setDelay(el, i * step);
    });
  }

  /* ── 2. Table row stagger (first N rows only) ────────────────── */

  function initTableStagger() {
    $all('#result_list tbody, table tbody').forEach(function (tbody) {
      var rows = Array.prototype.slice.call(tbody.children);
      var limit = Math.min(rows.length, 25);
      for (var i = 0; i < limit; i++) {
        setDelay(rows[i], i * 32);
      }
    });
  }

  /* ── 3. Sidebar nav stagger + ripple on click ───────────────── */

  function initSidebar() {
    var items = $all('#nav-sidebar li, nav.sidebar li, aside nav li');
    if (!items.length) return;

    items.forEach(function (el, i) {
      setDelay(el, i * 26);
    });

    // Ripple on anchor click
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

  /* ── 4. Button press feedback ────────────────────────────────── */

  function initButtonPress() {
    if (reduced.matches) return;

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

  /* ── 5. Form fieldset stagger ────────────────────────────────── */

  function initFieldsetStagger() {
    $all('fieldset.module, .form-row').forEach(function (el, i) {
      setDelay(el, i * 40);
    });
  }

  /* ── 6. Realtime toast bridge ────────────────────────────────── */

  function initRealtimeBridge() {
    // Only run if the admin is loaded inside a tenant schema
    var schema = document.body.getAttribute('data-tenant-schema');
    if (!schema || schema === 'public') return;

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

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }

  /* ── 7. Lifecycle — re-run on DOM swaps ──────────────────────── */

  function boot() {
    if (reduced.matches) return;
    initDashboardStagger();
    initTableStagger();
    initSidebar();
    initButtonPress();
    initFieldsetStagger();
    initRealtimeBridge();
  }

  // Re-boot when Unfold or HTMX swaps content (changelists, modals)
  document.addEventListener('DOMContentLoaded', boot);

  document.body.addEventListener('htmx:afterSwap', function () {
    if (reduced.matches) return;
    initDashboardStagger();
    initTableStagger();
    initFieldsetStagger();
  });

  // React to runtime preference changes
  reduced.addEventListener('change', function () {
    if (!reduced.matches) boot();
  });
})();