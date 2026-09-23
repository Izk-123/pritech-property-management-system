/**
 * Cache warm-up.
 *
 * Runs on page load while online. Fetches critical data
 * (today's arrivals, in-house guests, room status) and stores
 * it in IndexedDB so it's available during the next outage.
 *
 * Only runs on tenant schemas — the public schema has no
 * operational data to cache.
 */

(async function warmUpCache() {
  if (!navigator.onLine) return;
  if (!window.pritechDB) return;
  if (!document.body.dataset.tenantSchema) return;
  if (document.body.dataset.tenantSchema === 'public') return;

  // Don't warm up more than once per hour
  const lastWarmup = await window.pritechDB.db.metadata.get('last_warmup');
  if (lastWarmup) {
    const hourAgo = Date.now() - 60 * 60 * 1000;
    if (new Date(lastWarmup.value).getTime() > hourAgo) return;
  }

  try {
    // Fetch arrivals
    const arrivalsRes = await fetch('/api/v1/reservations/?status=CONF&check_in=today');
    if (arrivalsRes.ok) {
      const arrivals = await arrivalsRes.json();
      await window.pritechDB.cacheArrivals(arrivals.results || arrivals);
    }

    // Fetch room status
    const roomsRes = await fetch('/api/v1/units/?is_active=true');
    if (roomsRes.ok) {
      const rooms = await roomsRes.json();
      await window.pritechDB.cacheRooms(rooms.results || rooms);
    }

    // Fetch housekeeping tasks
    const tasksRes = await fetch('/api/v1/housekeeping/tasks/?status__in=PEND,PROG');
    if (tasksRes.ok) {
      const tasks = await tasksRes.json();
      const db = window.pritechDB.db;
      await db.cachedTasks.clear();
      await db.cachedTasks.bulkAdd(tasks.results || tasks);
    }

    // Record warmup time
    await window.pritechDB.db.metadata.put({
      key: 'last_warmup',
      value: new Date().toISOString(),
    });

    console.log('[Pritech] Cache warmed up for offline use');
  } catch (error) {
    console.warn('[Pritech] Cache warm-up failed:', error);
  }
})();