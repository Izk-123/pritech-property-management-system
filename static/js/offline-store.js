/**
 * Pritech PMS Offline Store
 *
 * Provides a tenant-scoped IndexedDB database for:
 *   - Caching critical data (room status, reservations, arrivals)
 *   - Queuing offline operations for sync
 *   - Detecting online/offline transitions
 *
 * Every tenant subdomain gets its own database, so data never
 * leaks between tenants on the same device.
 */

const tenantSlug = window.location.hostname
    .replace(/\./g, '_')
    .toLowerCase();

const db = new Dexie(`pritech_pms_${tenantSlug}`);

db.version(1).stores({
    // Cached server data (read-only, refreshed from API)
    cachedRooms: 'id, identifier, status, property_id',
    cachedArrivals: 'id, guest_name, check_in, status',
    cachedInHouse: 'id, guest_name, room, check_out, balance',
    cachedTasks: 'id, unit, task_type, status, priority',

    // Offline operation queue (write-ahead log)
    syncQueue: '++id, operation, endpoint, payload, created_at, status, retries',

    // Metadata
    metadata: 'key, value',
});

// ── Connectivity detection ────────────────────────────────────────
window.pritechOnline = {
    _listeners: [],
    isOnline: navigator.onLine,

    onChange(callback) {
        this._listeners.push(callback);
    },

    _notify() {
        this._listeners.forEach((cb) => cb(this.isOnline));
    },
};

window.addEventListener('online', () => {
    window.pritechOnline.isOnline = true;
    window.pritechOnline._notify();
    syncPendingOperations();
});

window.addEventListener('offline', () => {
    window.pritechOnline.isOnline = false;
    window.pritechOnline._notify();
});

// ── Queue an offline operation ────────────────────────────────────
async function queueOperation(operation, endpoint, payload) {
    const id = await db.syncQueue.add({
        operation,
        endpoint,
        payload,
        created_at: new Date().toISOString(),
        status: 'pending',
        retries: 0,
    });

    // Register a background sync if supported
    if ('serviceWorker' in navigator && 'SyncManager' in window) {
        const registration = await navigator.serviceWorker.ready;
        try {
            await registration.sync.register('pritech-sync-queue');
        } catch (e) {
            // Background sync not available — the sync will happen on next page load
            console.warn('Background sync registration failed:', e);
        }
    }

    return id;
}

// ── Sync pending operations ───────────────────────────────────────
async function syncPendingOperations() {
    if (!navigator.onLine) return;

    const pending = await db.syncQueue
        .where('status').equals('pending')
        .sortBy('created_at');

    for (const op of pending) {
        try {
            const response = await fetch(op.endpoint, {
                method: op.operation,
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                },
                body: JSON.stringify(op.payload),
            });

            if (response.ok) {
                await db.syncQueue.update(op.id, { status: 'synced' });
            } else if (response.status === 409) {
                // Conflict — log it for manual review
                await db.syncQueue.update(op.id, {
                    status: 'conflict',
                    conflict_data: await response.json(),
                });
            } else {
                await db.syncQueue.update(op.id, {
                    retries: op.retries + 1,
                    status: op.retries >= 5 ? 'failed' : 'pending',
                });
            }
        } catch (error) {
            // Network error — leave in queue for next attempt
            await db.syncQueue.update(op.id, {
                retries: op.retries + 1,
                status: op.retries >= 5 ? 'failed' : 'pending',
            });
        }
    }

    // Clean up synced operations older than 7 days
    const cutoff = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
    await db.syncQueue
        .where('status').equals('synced')
        .and((op) => new Date(op.created_at) < cutoff)
        .delete();

    // Notify the UI
    const remaining = await db.syncQueue
        .where('status').equals('pending').count();
    window.dispatchEvent(new CustomEvent('pritech:sync-status', {
        detail: { pending: remaining },
    }));
}

function getCsrfToken() {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
}

// ── Cache helpers ─────────────────────────────────────────────────
async function cacheRooms(rooms) {
    await db.cachedRooms.clear();
    await db.cachedRooms.bulkAdd(rooms);
}

async function getCachedRooms() {
    return db.cachedRooms.toArray();
}

async function cacheArrivals(arrivals) {
    await db.cachedArrivals.clear();
    await db.cachedArrivals.bulkAdd(arrivals);
}

async function getCachedArrivals() {
    return db.cachedArrivals.toArray();
}

// ── Expose the API ────────────────────────────────────────────────
window.pritechDB = {
    db,
    queueOperation,
    syncPendingOperations,
    cacheRooms,
    getCachedRooms,
    cacheArrivals,
    getCachedArrivals,
};

// Auto-sync on page load if online
if (navigator.onLine) {
    syncPendingOperations();
}