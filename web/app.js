const feed = document.querySelector('#feed');
const wrap = document.querySelector('.feed-wrap');
const start = document.querySelector('#start');
const stop = document.querySelector('#stop');
const testVoice = document.querySelector('#test-voice');
const videoFile = document.querySelector('#video-file');
const upload = document.querySelector('#upload');
const uploadStatus = document.querySelector('#upload-status');
const voice = document.querySelector('#voice');
const destination = document.querySelector('#destination');
const routeButton = document.querySelector('#route');
let poller = null;
let locationWatcher = null;
let lastAlertId = 0;
let lastHapticAlertId = 0;
let lastNavigationEventId = 0;

function setText(selector, text) { document.querySelector(selector).textContent = text; }

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

function startLocationUpdates() {
  if (!('geolocation' in navigator)) {
    setText('#alert-help', 'Location is not supported by this browser');
    return;
  }
  locationWatcher = navigator.geolocation.watchPosition(async (position) => {
    const { latitude, longitude, accuracy, heading, speed } = position.coords;
    try {
      await fetch('/location', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          latitude,
          longitude,
          accuracy,
          heading,
          speed,
          timestamp: position.timestamp,
        }),
      });
    } catch (_) {
      setText('#alert-help', 'Camera active; location update failed');
    }
  }, () => {
    setText('#alert-help', 'Camera active; location permission is unavailable');
  }, { enableHighAccuracy: true, maximumAge: 2000, timeout: 10000 });
}

function stopLocationUpdates() {
  if (locationWatcher !== null) {
    navigator.geolocation.clearWatch(locationWatcher);
    locationWatcher = null;
  }
}

async function refreshState() {
  try {
    const response = await fetch('/state', { cache: 'no-store' });
    const data = await response.json();
    const live = data.connected;
    document.querySelector('#connection-dot').classList.toggle('live', live);
    setText('#connection-label', live ? 'Connected' : 'Offline');
    setText('#mode-badge', live ? 'LIVE' : 'STANDBY');
    document.querySelector('#mode-badge').classList.toggle('live', live);
    setText('#status', data.status);
    setText('#objects', data.detections);
    setText('#fps', data.fps ? `${data.fps} fps` : '--');
    setText('#depth', data.depth ? 'ACTIVE' : 'OFF');
    const alert = document.querySelector('#alert-card');
    const safetyActive = Boolean(data.alert && data.alert_time &&
      Date.now() / 1000 - data.alert_time < 4);
    alert.classList.toggle('danger', safetyActive && data.alert.startsWith('Stop'));
    setText('#alert', data.alert || 'No active alert');
    setText('#alert-help', data.alert ? 'Spoken alert dispatched' : 'The path is being watched.');
    if (safetyActive && data.urgent && data.alert_id !== lastHapticAlertId) {
      lastHapticAlertId = data.alert_id;
      if ('vibrate' in navigator) navigator.vibrate([120, 80, 120]);
    }
    if (safetyActive) speak(data.alert, data.alert_id);
    if (data.navigation) {
      const nav = data.navigation;
      setText('#route-status', nav.active
        ? (nav.guidance || 'Route active')
        : 'No active route');
      if (!safetyActive) speakNavigation(nav.message, nav.event_id);
    }
  } catch (_) {
    setText('#connection-label', 'Offline');
  }
}

routeButton.addEventListener('click', async () => {
  const query = destination.value.trim();
  if (!query) {
    setText('#route-status', 'Enter a destination first.');
    return;
  }
  routeButton.disabled = true;
  setText('#route-status', 'Finding a walking route...');
  try {
    const response = await fetch('/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ destination: query }),
    });
    if (!response.ok) throw new Error((await response.text()) || 'Route request failed');
    const result = await response.json();
    setText('#route-status', result.navigation.destination_name || 'Route ready. Start walking.');
  } catch (error) {
    setText('#route-status', error.message);
  } finally {
    routeButton.disabled = false;
  }
});

start.addEventListener('click', () => {
  feed.src = `/stream?source=0&stamp=${Date.now()}`;
  wrap.classList.add('active');
  start.disabled = true;
  stop.disabled = false;
  startLocationUpdates();
  poller = setInterval(refreshState, 500);
  refreshState();
});

stop.addEventListener('click', () => {
  feed.src = '';
  wrap.classList.remove('active');
  start.disabled = false;
  stop.disabled = true;
  stopLocationUpdates();
  clearInterval(poller);
  setText('#status', 'Camera stopped');
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
    feed.src = '';
    wrap.classList.remove('active');
    start.disabled = false;
    stop.disabled = true;
    uploadStatus.textContent = `${result.name} ready. Press Start monitoring.`;
    setText('#status', 'Uploaded video ready');
  } catch (error) {
    uploadStatus.textContent = error.message;
  } finally {
    upload.disabled = false;
  }
});