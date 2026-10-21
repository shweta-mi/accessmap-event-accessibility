const map = L.map('map', { scrollWheelZoom: false }).setView([25.44, 81.85], 12);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; OpenStreetMap contributors', maxZoom: 19
}).addTo(map);

let markers = [];
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, ch => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[ch]));

function feature(label, value) {
  const yes = value === true;
  const no = value === false;
  const state = yes ? '✓' : no ? '—' : '?';
  const css = yes ? '' : ' no';
  return `<span class="feature${css}">${state} ${escapeHTML(label)}</span>`;
}

function verificationInfo(place) {
  if (place.verification_status === 'verified') {
    return `<div class="verification verified"><span>✓ VERIFIED</span><small>${escapeHTML(place.verified_on || '')} · ${escapeHTML(place.verification_source)}</small></div>`;
  }
  return `<div class="verification demo"><span>DEMO DATA</span><small>Illustrative, not surveyed</small></div>`;
}

async function loadPlaces() {
  const query = new URLSearchParams({
    step_free: $('step').checked,
    restroom: $('restroom').checked,
    area: $('area').value,
  });
  const response = await fetch('/api/places?' + query);
  if (!response.ok) throw new Error('Could not load venue records. Please try again.');
  const data = await response.json();
  $('count').textContent = String(data.places.length).padStart(2, '0');
  $('data-summary').textContent = `${data.counts.verified} verified · ${data.counts.demo} demo records`;
  $('empty').hidden = data.places.length > 0;
  $('cards').innerHTML = data.places.map(place => `
    <article class="venue">
      <div class="venue-top"><div><h3>${escapeHTML(place.name)}</h3><div class="area">${escapeHTML(place.area)} · Transit: ${escapeHTML(place.transit)}</div></div></div>
      ${verificationInfo(place)}
      <div class="features">${feature('Step-free', place.step_free)}${feature('Accessible restroom', place.accessible_restroom)}${feature('Transit ' + place.transit, place.transit !== 'Low' && place.transit !== 'Unknown')}</div>
      ${place.details ? `<div class="venue-note">${escapeHTML(place.details)}</div>` : ''}
    </article>`).join('');

  markers.forEach(marker => map.removeLayer(marker));
  markers = data.places.map(place => {
    const verified = place.verification_status === 'verified';
    const marker = L.circleMarker([place.lat, place.lon], {
      radius: verified ? 9 : 7,
      color: verified ? '#174e3b' : '#6e8075',
      weight: 2,
      fillColor: verified ? '#3f8a61' : '#b5c1b4',
      fillOpacity: .95,
    }).addTo(map);
    const status = verified
      ? `Verified ${escapeHTML(place.verified_on || '')} · ${escapeHTML(place.verification_source)}`
      : 'Illustrative demo record; verify details directly with the venue.';
    marker.bindPopup(`<strong>${escapeHTML(place.name)}</strong><br>${escapeHTML(place.area)}<br><small>${status}</small>`);
    return marker;
  });
  if (markers.length) map.fitBounds(L.featureGroup(markers).getBounds().pad(.2));
}

async function refresh() {
  try {
    await loadPlaces();
  } catch (error) {
    $('cards').innerHTML = '';
    $('empty').hidden = false;
    $('empty').textContent = error.message;
  }
}

['step', 'restroom'].forEach(id => $(id).addEventListener('change', refresh));
$('area').addEventListener('input', () => {
  clearTimeout(window.areaSearchTimer);
  window.areaSearchTimer = setTimeout(refresh, 220);
});
$('reset').addEventListener('click', () => {
  $('step').checked = false;
  $('restroom').checked = false;
  $('area').value = '';
  refresh();
});
$('open-suggest').addEventListener('click', () => {
  $('suggest-panel').open = true;
  $('suggest-panel').scrollIntoView({ behavior: 'smooth', block: 'center' });
  $('suggestion-form').elements.name.focus({ preventScroll: true });
});

let adminKey = '';
const adminStatus = $('admin-status');

function setAdminStatus(message, type = '') {
  adminStatus.className = 'admin-status' + (type ? ' ' + type : '');
  adminStatus.textContent = message;
}

async function adminRequest(path, method = 'GET', payload = undefined) {
  const options = { method, headers: { 'X-Admin-Key': adminKey } };
  if (payload !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(payload);
  }
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || `Request failed (${response.status}).`);
  return result;
}

function showPending(submissions) {
  const pending = submissions.filter(item => item.status === 'pending');
  $('pending-list').innerHTML = pending.length ? pending.map(item => `
    <article class="pending-item" data-id="${Number(item.id)}">
      <div class="pending-heading"><div><h3>${escapeHTML(item.name)}</h3><span>${escapeHTML(item.area)} · ${Number(item.latitude).toFixed(4)}, ${Number(item.longitude).toFixed(4)}</span></div><b>AWAITING REVIEW</b></div>
      <div class="pending-facts">Step-free: ${item.step_free === null ? 'Unknown' : item.step_free ? 'Yes' : 'No'} · Accessible restroom: ${item.accessible_restroom === null ? 'Unknown' : item.accessible_restroom ? 'Yes' : 'No'} · Transit: ${escapeHTML(item.transit)}</div>
      <details class="evidence-details"><summary>View submitted evidence and notes</summary><p><b>Submitted source:</b> ${escapeHTML(item.evidence)}</p><p>${escapeHTML(item.details || 'No extra notes provided.')}</p></details>
      <div class="review-grid"><label>Verification source for approval<input class="review-source" maxlength="500" placeholder="What did you verify, and where?"></label><label>Verified on<input class="review-date" type="date"></label></div>
      <div class="review-actions"><button type="button" data-decision="approve">Approve and publish</button><button class="reject" type="button" data-decision="reject">Reject</button></div>
      <div class="review-message" role="status" aria-live="polite"></div>
    </article>`).join('') : '<div class="no-pending">No pending suggestions.</div>';
}

async function connectAdmin() {
  const key = $('admin-key').value.trim();
  if (!key) {
    setAdminStatus('Enter the admin key to connect.', 'failure');
    return;
  }
  adminKey = key;
  setAdminStatus('Checking admin access…');
  try {
    const result = await adminRequest('/api/admin/submissions');
    showPending(result.submissions);
    $('admin-disconnect').hidden = false;
    setAdminStatus(`Connected · ${result.submissions.filter(item => item.status === 'pending').length} pending`, 'success');
  } catch (error) {
    adminKey = '';
    $('pending-list').innerHTML = '';
    setAdminStatus(error.message, 'failure');
  }
}

$('admin-connect').addEventListener('click', connectAdmin);
$('admin-key').addEventListener('keydown', event => {
  if (event.key === 'Enter') connectAdmin();
});
$('admin-disconnect').addEventListener('click', () => {
  adminKey = '';
  $('admin-key').value = '';
  $('pending-list').innerHTML = '';
  $('admin-disconnect').hidden = true;
  setAdminStatus('Disconnected.');
});
$('admin-panel').addEventListener('click', async event => {
  const button = event.target.closest('button[data-decision]');
  if (!button) return;
  const card = button.closest('.pending-item');
  const message = card.querySelector('.review-message');
  const decision = button.dataset.decision;
  const payload = { decision };
  if (decision === 'approve') {
    payload.verification_source = card.querySelector('.review-source').value.trim();
    payload.verified_on = card.querySelector('.review-date').value;
    if (payload.verification_source.length < 8 || !payload.verified_on) {
      message.textContent = 'Enter a verification source and date before approving.';
      message.className = 'review-message failure';
      return;
    }
  }
  button.disabled = true;
  message.textContent = 'Saving review…';
  message.className = 'review-message';
  try {
    await adminRequest(`/api/admin/submissions/${Number(card.dataset.id)}/review`, 'POST', payload);
    const result = await adminRequest('/api/admin/submissions');
    showPending(result.submissions);
    setAdminStatus(`Connected · ${result.submissions.filter(item => item.status === 'pending').length} pending`, 'success');
  } catch (error) {
    message.textContent = error.message;
    message.className = 'review-message failure';
    button.disabled = false;
  }
});
$('admin-shortcut').addEventListener('click', event => {
  event.preventDefault();
  $('admin-panel').open = true;
  $('admin-panel').scrollIntoView({ behavior: 'smooth', block: 'center' });
  $('admin-key').focus({ preventScroll: true });
});

$('suggestion-form').addEventListener('submit', async event => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = new FormData(form);
  const toBool = value => value === '' ? null : value === 'true';
  const payload = {
    name: values.get('name'), area: values.get('area'),
    latitude: Number(values.get('latitude')), longitude: Number(values.get('longitude')),
    step_free: toBool(values.get('step_free')),
    accessible_restroom: toBool(values.get('accessible_restroom')),
    transit: values.get('transit'), evidence: values.get('evidence'), details: values.get('details') || '',
  };
  const button = form.querySelector('button[type="submit"]');
  const status = $('form-status');
  button.disabled = true;
  button.textContent = 'Sending…';
  status.className = 'form-status';
  status.textContent = '';
  try {
    const response = await fetch('/api/submissions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
      const message = Array.isArray(result.detail)
        ? result.detail.map(issue => issue.msg).join(' ')
        : result.detail || 'Could not submit this suggestion.';
      throw new Error(message);
    }
    status.classList.add('success');
    status.textContent = result.message;
    form.reset();
  } catch (error) {
    status.classList.add('failure');
    status.textContent = error.message;
  } finally {
    button.disabled = false;
    button.innerHTML = 'Send for review <span>→</span>';
  }
});

refresh();
