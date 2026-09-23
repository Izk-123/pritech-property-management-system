/**
 * Offline-aware form submission.
 *
 * Attach to any form with the `data-offline-form` attribute.
 * If the browser is online, submits normally.
 * If offline, queues the submission in IndexedDB.
 */

document.addEventListener('submit', async (event) => {
  const form = event.target.closest('form[data-offline-form]');
  if (!form) return;

  // If online, let the form submit normally
  if (navigator.onLine) return;

  event.preventDefault();

  const endpoint = form.getAttribute('data-offline-endpoint') || form.action;
  const method = (form.method || 'POST').toUpperCase();
  const payload = {};

  // Serialize form data
  const formData = new FormData(form);
  for (const [key, value] of formData.entries()) {
    if (key === 'csrfmiddlewaretoken') continue;
    if (payload[key]) {
      // Handle multiple values (e.g., checkboxes)
      if (!Array.isArray(payload[key])) payload[key] = [payload[key]];
      payload[key].push(value);
    } else {
      payload[key] = value;
    }
  }

  // Queue the operation
  await window.pritechDB.queueOperation(method, endpoint, payload);

  // Show confirmation
  const successMsg = form.getAttribute('data-offline-success')
    || 'Saved offline. Will sync when online.';

  const banner = document.createElement('div');
  banner.className = 'fixed top-4 left-1/2 -translate-x-1/2 z-50 ' +
                    'rounded-lg bg-amber-500 text-white px-4 py-2 ' +
                    'text-sm font-medium shadow-lg';
  banner.textContent = successMsg;
  document.body.appendChild(banner);
  setTimeout(() => banner.remove(), 4000);

  // Reset the form
  form.reset();

  // Navigate if the form specifies a destination
  const redirect = form.getAttribute('data-offline-redirect');
  if (redirect) {
    setTimeout(() => window.location.href = redirect, 1200);
  }
});