const $ = (selector) => document.querySelector(selector);
const feed = $('#feed');
const wrap = $('.feed-wrap');
const start = $('#start');
const stop = $('#stop');
const testVoice = $('#test-voice');
const videoFile = $('#video-file');
const upload = $('#upload');
const uploadStatus = $('#upload-status');
const uploadRow = $('#upload-row');
const voice = $('#voice');
const destination = $('#destination');
const routeButton = $('#route');
const suggestionList = $('#suggestions');
const searchStatus = $('#search-status');
const sourceCamera = $('#source-camera');
const sourceDevice = $('#source-device');
const sourceFile = $('#source-file');
let monitoring = false;
let sourceMode = 'server';
let sourceChosen = false;
let deviceActive = false;
let captureSession = '';
let locationWatcher = null;
let lastAlertId = 0;
let lastHapticAlertId = 0;
let lastNavigationEventId = 0;
let selectedDestination = null;
let suggestionTimer = null;
let suggestionRequest = 0;
let lastPosition = null;

function setText(selector, text) { $(selector).textContent = text; }

function speak(text, alertId = null) {
  if (!voice.checked || !('speechSynthesis' in window) || !text) return;
  if (alertId !== null && alertId === lastAlertId) return;
  if (alertId !== null) lastAlertId = alertId;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.5;
  window.speechSynthesis.speak(utterance);
}

function speakNavigation(text, eventId) {
  if (!voice.checked || !text || eventId === lastNavigationEventId) return;
  lastNavigationEventId = eventId;
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  }
}

testVoice.addEventListener('click', () => {
  if (!('speechSynthesis' in window)) {
    setText('#alert-help', 'Speech is not supported by this browser');
    return;
  }
  speak('SafeStride voice alerts are working');
  setText('#alert-help', 'Voice test sent to the browser audio output');
});

/* ---------- map (Leaflet draws it; place search comes from /places) ---------- */
let map = null;
let userMarker = null;
let routeLine = null;
let destinationMarker = null;
let routeKey = '';

function initMap() {
  const element = $('#map');
  if (typeof L === 'undefined') {
    element.classList.add('empty');
    element.textContent = 'Map needs an internet connection';
    return;
  }
  map = L.map(element, { zoomControl: true, attributionControl: true }).setView([20.5937, 78.9629], 4);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors',
  }).addTo(map);
}

function updateMapPosition(latitude, longitude) {
  if (!map) return;
  const point = [latitude, longitude];
  if (!userMarker) {
    userMarker = L.circleMarker(point, { radius: 8, color: '#101216', weight: 2, fillColor: '#b9e769', fillOpacity: 1 }).addTo(map);
    map.setView(point, 16);
  } else {
    userMarker.setLatLng(point);
  }
}

function updateMapRoute(geometry) {
  if (!map) return;
  const key = geometry && geometry.length ? `${geometry.length}:${geometry[0]}:${geometry[geometry.length - 1]}` : '';
  if (key === routeKey) return;
  routeKey = key;
  if (routeLine) { map.removeLayer(routeLine); routeLine = null; }
  if (destinationMarker) { map.removeLayer(destinationMarker); destinationMarker = null; }
  if (!key) return;
  routeLine = L.polyline(geometry, { color: '#3f8cff', weight: 5, opacity: 0.9 }).addTo(map);
  destinationMarker = L.circleMarker(geometry[geometry.length - 1], { radius: 8, color: '#101216', weight: 2, fillColor: '#ff7272', fillOpacity: 1 }).addTo(map);
  map.fitBounds(routeLine.getBounds(), { padding: [24, 24] });
}

/* ---------- location (needed for routes, so it runs even before the camera starts) ---------- */
function startLocationUpdates() {
  if (!('geolocation' in navigator)) {
    setText('#gps-badge', 'NO GPS');
    return;
  }
  locationWatcher = navigator.geolocation.watchPosition(async (position) => {
    const { latitude, longitude, accuracy, heading, speed } = position.coords;
    lastPosition = { latitude, longitude };
    setText('#gps-badge', `GPS ±${Math.round(accuracy)} m`);
    $('#gps-badge').classList.add('live');
    updateMapPosition(latitude, longitude);
    try {
      await fetch('/location', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ latitude, longitude, accuracy, heading, speed, timestamp: position.timestamp }),
      });
    } catch (_) {
      setText('#gps-badge', 'GPS NOT SENT');
    }
  }, () => {
    setText('#gps-badge', 'GPS DENIED');
    $('#gps-badge').classList.remove('live');
  }, { enableHighAccuracy: true, maximumAge: 2000, timeout: 10000 });
}

function cardinal(bearing) {
  return ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(bearing / 45) % 8];
}

async function refreshState() {
  try {
    const response = await fetch('/state', { cache: 'no-store' });
    const data = await response.json();
    const live = data.connected || deviceActive;
    $('#connection-dot').classList.toggle('live', live);
    setText('#connection-label', live ? 'Connected' : 'Offline');
    setText('#mode-badge', live ? 'LIVE' : 'STANDBY');
    $('#mode-badge').classList.toggle('live', live);
    setText('#status', data.status || 'Waiting');
    setText('#objects', data.detections ?? 0);
    setText('#fps', data.fps ? `${data.fps} fps` : '--');
    setText('#depth', data.depth ? 'ACTIVE' : 'OFF');
    if (!sourceChosen && data.source_kind) {
      const onPhone = /Android|iPhone|iPad/i.test(navigator.userAgent);
      sourceMode = data.source_kind === 'file' ? 'file' : onPhone ? 'device' : 'server';
      showSource(sourceMode);
    }

    const safetyActive = Boolean(data.alert && data.alert_time && Date.now() / 1000 - data.alert_time < 4);
    const danger = safetyActive && data.alert.startsWith('Stop');
    const card = $('#alert-card');
    card.classList.toggle('danger', danger);
    card.classList.toggle('caution', safetyActive && !danger);
    setText('#alert-kicker', danger ? 'STOP / URGENT' : safetyActive ? 'SAFETY CAUTION' : 'SAFETY CLEAR');
    setText('#alert', safetyActive ? data.alert : 'No active alert');
    setText('#alert-help', safetyActive ? 'Spoken alert dispatched' : 'The path is being watched.');
    if (monitoring && safetyActive && data.urgent && data.alert_id !== lastHapticAlertId) {
      lastHapticAlertId = data.alert_id;
      if ('vibrate' in navigator) navigator.vibrate([120, 80, 120]);
    }
    if (monitoring && safetyActive) speak(data.alert, data.alert_id);

    const nav = data.navigation;
    if (nav) {
      setText('#route-status', nav.active ? (nav.guidance || 'Route active') : 'No active route');
      setText('#route-distance', nav.active && nav.distance_remaining != null
        ? (nav.arrived ? 'Arrived' : `${Math.round(nav.distance_remaining)} m remaining`) : '');
      setText('#route-direction', nav.active && nav.target_bearing != null
        ? `Road direction ${cardinal(nav.target_bearing)} (${Math.round(nav.target_bearing)}°)` : '');
      updateMapRoute(nav.active ? nav.route_geometry : []);
      if (monitoring && !safetyActive) speakNavigation(nav.message, nav.event_id);
    }
  } catch (_) {
    setText('#connection-label', 'Offline');
  }
}

/* ---------- destination search ---------- */
function hideSuggestions() {
  suggestionList.hidden = true;
  suggestionList.replaceChildren();
}

function showSuggestions(items) {
  suggestionList.replaceChildren();
  for (const item of items) {
    const row = document.createElement('li');
    row.tabIndex = 0;
    const name = document.createElement('b');
    name.textContent = item.name;
    const address = document.createElement('small');
    address.textContent = item.display_name;
    row.append(name, address);
    const choose = () => {
      destination.value = item.display_name;
      selectedDestination = [item.latitude, item.longitude];
      hideSuggestions();
      searchStatus.textContent = 'Place selected. Press Route.';
    };
    row.addEventListener('click', choose);
    row.addEventListener('keydown', (event) => { if (event.key === 'Enter') choose(); });
    suggestionList.append(row);
  }
  suggestionList.hidden = items.length === 0;
}

async function searchPlaces(query) {
  const request = ++suggestionRequest;
  searchStatus.textContent = 'Searching nearby places…';
  try {
    const response = await fetch(`/places?q=${encodeURIComponent(query)}`, { cache: 'no-store' });
    if (!response.ok) throw new Error('Search failed');
    const data = await response.json();
    if (request !== suggestionRequest) return;
    showSuggestions(data.suggestions || []);
    searchStatus.textContent = data.suggestions && data.suggestions.length
      ? `${data.provider || 'OpenStreetMap'} results` : 'No places found. Try a different name.';
  } catch (_) {
    if (request === suggestionRequest) searchStatus.textContent = 'Place search is unavailable right now';
  }
}

destination.addEventListener('input', () => {
  selectedDestination = null;
  clearTimeout(suggestionTimer);
  const query = destination.value.trim();
  if (query.length < 3) {
    suggestionRequest += 1;
    hideSuggestions();
    searchStatus.textContent = '';
    return;
  }
  suggestionTimer = setTimeout(() => searchPlaces(query), 400);
});

destination.addEventListener('keydown', (event) => { if (event.key === 'Enter') routeButton.click(); });

routeButton.addEventListener('click', async () => {
  const query = destination.value.trim();
  if (!query) {
    setText('#route-status', 'Enter a destination first.');
    return;
  }
  hideSuggestions();
  routeButton.disabled = true;
  setText('#route-status', 'Finding a walking route...');
  try {
    const body = { destination: query };
    if (selectedDestination) body.destination_coordinates = selectedDestination;
    const response = await fetch('/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error((await response.text()) || 'Route request failed');
    const result = await response.json();
    setText('#route-status', result.navigation.destination_name || 'Route ready. Start walking.');
    refreshState();
  } catch (error) {
    setText('#route-status', error.message);
  } finally {
    routeButton.disabled = false;
  }
});

/* ---------- source, start / stop, upload ---------- */
const sourceButtons = { server: sourceCamera, device: sourceDevice, file: sourceFile };

function showSource(mode) {
  for (const [name, button] of Object.entries(sourceButtons)) {
    button.classList.toggle('active', name === mode);
    button.setAttribute('aria-checked', String(name === mode));
  }
  uploadRow.hidden = mode !== 'file';
}

function chooseSource(mode) {
  if (monitoring) return;
  sourceMode = mode;
  sourceChosen = true;
  showSource(mode);
}
sourceCamera.addEventListener('click', () => chooseSource('server'));
sourceDevice.addEventListener('click', () => chooseSource('device'));
sourceFile.addEventListener('click', () => chooseSource('file'));

/* Phone camera: the browser captures frames and the server annotates them. */
const captureCanvas = document.createElement('canvas');
const captureVideo = document.createElement('video');
captureVideo.muted = true;
captureVideo.playsInline = true;
let deviceStream = null;

async function startDeviceCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setText('#status', 'Camera needs HTTPS (open the https:// address)');
    return false;
  }
  try {
    deviceStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } },
      audio: false,
    });
  } catch (error) {
    setText('#status', `Camera unavailable: ${error.name}`);
    return false;
  }
  captureVideo.srcObject = deviceStream;
  await captureVideo.play();
  deviceActive = true;
  captureSession = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()));
  sendDeviceFrames();
  return true;
}

function stopDeviceCamera() {
  deviceActive = false;
  if (deviceStream) deviceStream.getTracks().forEach((track) => track.stop());
  deviceStream = null;
  captureVideo.srcObject = null;
}

async function sendDeviceFrames() {
  while (deviceActive) {
    if (!captureVideo.videoWidth) { await new Promise((resolve) => setTimeout(resolve, 50)); continue; }
    captureCanvas.width = 640;
    captureCanvas.height = Math.round(640 * captureVideo.videoHeight / captureVideo.videoWidth);
    captureCanvas.getContext('2d').drawImage(captureVideo, 0, 0, captureCanvas.width, captureCanvas.height);
    const capturedAt = performance.now() / 1000;
    const image = captureCanvas.toDataURL('image/jpeg', 0.6).split(',')[1];
    try {
      const response = await fetch('/frame', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image, captured_at: capturedAt, session: captureSession }),
      });
      if (!response.ok) throw new Error(`Server error ${response.status}`);
      const result = await response.json();
      if (deviceActive) feed.src = `data:image/jpeg;base64,${result.image}`;
    } catch (error) {
      setText('#status', error.message);
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
}

function endMonitoring() {
  stopDeviceCamera();
  feed.src = '';
  wrap.classList.remove('active');
  start.disabled = false;
  stop.disabled = true;
  monitoring = false;
}

start.addEventListener('click', async () => {
  start.disabled = true;
  if (sourceMode === 'device') {
    if (!(await startDeviceCamera())) { start.disabled = false; return; }
  } else {
    const useServerCamera = sourceChosen && sourceMode === 'server' ? 'use=camera&' : '';
    feed.src = `/stream?${useServerCamera}stamp=${Date.now()}`;
  }
  wrap.classList.add('active');
  stop.disabled = false;
  monitoring = true;
  refreshState();
});

stop.addEventListener('click', () => {
  endMonitoring();
  setText('#status', 'Stopped');
});

upload.addEventListener('click', async () => {
  const file = videoFile.files[0];
  if (!file) {
    uploadStatus.textContent = 'Choose a video first';
    return;
  }
  upload.disabled = true;
  uploadStatus.textContent = 'Uploading...';
  const form = new FormData();
  form.append('video', file);
  try {
    const response = await fetch('/upload', { method: 'POST', body: form });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || 'Upload failed');
    endMonitoring();
    uploadStatus.textContent = `${result.name} ready. Press Start monitoring.`;
    setText('#status', 'Uploaded video ready');
  } catch (error) {
    uploadStatus.textContent = error.message;
  } finally {
    upload.disabled = false;
  }
});

initMap();
startLocationUpdates();
setInterval(refreshState, 700);
refreshState();
