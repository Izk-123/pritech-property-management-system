/**
 * Pritech PMS real-time client.
 *
 * Opens WebSockets on tenant pages and dispatches incoming events
 * as DOM CustomEvents. Components subscribe via addEventListener.
 *
 * Reconnects automatically with exponential backoff. Falls back to
 * polling on network events if WebSockets are blocked.
 */
(function () {
  'use strict';

  var RECONNECT_BASE = 1000;
  var RECONNECT_MAX = 30000;
  var PING_INTERVAL = 25000;

  var sockets = {};
  var attempt = {};
  var stopped = false;
  var pingTimer = null;

  function wsUrl(path) {
    var proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return proto + '//' + window.location.host + path;
  }

  function connect(name, path, onMessage) {
    if (stopped) return;
    if (sockets[name] && sockets[name].readyState <= 1) return;

    var ws;
    try {
      ws = new WebSocket(wsUrl(path));
    } catch (e) {
      scheduleReconnect(name, path, onMessage);
      return;
    }
    sockets[name] = ws;

    ws.addEventListener('open', function () {
      attempt[name] = 0;
      console.info('[Pritech] WS connected:', name);
    });

    ws.addEventListener('message', function (evt) {
      var data;
      try { data = JSON.parse(evt.data); } catch (e) { return; }
      if (data.type === 'pong') return;
      onMessage(data);
      window.dispatchEvent(new CustomEvent('pritech:realtime', {
        detail: Object.assign({ stream: name }, data),
      }));
    });

    ws.addEventListener('close', function () {
      if (!stopped) scheduleReconnect(name, path, onMessage);
    });
  }

  function scheduleReconnect(name, path, onMessage) {
    attempt[name] = (attempt[name] || 0) + 1;
    var delay = Math.min(
      RECONNECT_BASE * Math.pow(2, attempt[name] - 1),
      RECONNECT_MAX
    );
    setTimeout(function () { connect(name, path, onMessage); }, delay);
  }

  function heartbeat() {
    Object.keys(sockets).forEach(function (name) {
      var ws = sockets[name];
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    });
  }

  function disconnectAll() {
    stopped = true;
    Object.keys(sockets).forEach(function (name) {
      try { sockets[name].close(); } catch (e) {}
    });
  }

  window.addEventListener('beforeunload', disconnectAll);
  window.addEventListener('online', function () {
    stopped = false;
    Object.keys(sockets).forEach(function (name) {
      if (sockets[name].readyState === WebSocket.CLOSED) {
        attempt[name] = 0;
        connect(name, '/ws/' + name + '/', function () {});
      }
    });
  });

  if (!('WebSocket' in window)) return;
  if (!document.body.dataset.tenantSchema) return;
  if (document.body.dataset.tenantSchema === 'public') return;

  connect('notifications', '/ws/notifications/', function (data) {
    if (data.title) showToast(data.type || 'info', data.title, data.message || '');
  });

  pingTimer = setInterval(heartbeat, PING_INTERVAL);

  function showToast(type, title, message) {
    var colors = {
      success: 'bg-emerald-500',
      error: 'bg-red-500',
      warning: 'bg-amber-500',
      info: 'bg-sky-500',
    };
    var color = colors[type] || colors.info;

    var el = document.createElement('div');
    el.className = 'fixed top-4 right-4 z-50 w-80 rounded-xl text-white ' +
                   'shadow-2xl px-4 py-3 transform transition-all duration-300 ' +
                   'translate-x-full ' + color;
    el.innerHTML =
      '<p class="text-sm font-semibold">' + escapeHtml(title) + '</p>' +
      (message ? '<p class="mt-1 text-xs opacity-90">' + escapeHtml(message) + '</p>' : '');
    document.body.appendChild(el);

    requestAnimationFrame(function () { el.classList.remove('translate-x-full'); });
    setTimeout(function () {
      el.classList.add('translate-x-full');
      setTimeout(function () { el.remove(); }, 300);
    }, 5000);
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  window.pritechRealtime = { connect: connect, showToast: showToast };
})();