const feed = document.querySelector('#feed');
const wrap = document.querySelector('.feed-wrap');
const start = document.querySelector('#start');
const stop = document.querySelector('#stop');
const testVoice = document.querySelector('#test-voice');
const videoFile = document.querySelector('#video-file');
const upload = document.querySelector('#upload');
const uploadStatus = document.querySelector('#upload-status');
const voice = document.querySelector('#voice');
let poller = null;
let lastAlertId = 0;

function setText(selector, text) { document.querySelector(selector).textContent = text; }

function speak(text, alertId = null) {
  if (!voice.checked || !('speechSynthesis' in window) || !text) return;
  if (alertId !== null && alertId === lastAlertId) return;
  if (alertId !== null) lastAlertId = alertId;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}

testVoice.addEventListener('click', () => {
  if (!('speechSynthesis' in window)) {
    setText('#alert-help', 'Speech is not supported by this browser');
    return;
  }
  speak('SafeStride voice alerts are working');
  setText('#alert-help', 'Voice test sent to the browser audio output');
});

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
    alert.classList.toggle('danger', Boolean(data.alert && data.alert.startsWith('Stop')));
    setText('#alert', data.alert || 'No active alert');
    setText('#alert-help', data.alert ? 'Spoken alert dispatched' : 'The path is being watched.');
    speak(data.alert, data.alert_id);
  } catch (_) {
    setText('#connection-label', 'Offline');
  }
}

start.addEventListener('click', () => {
  feed.src = `/stream?source=0&stamp=${Date.now()}`;
  wrap.classList.add('active');
  start.disabled = true;
  stop.disabled = false;
  poller = setInterval(refreshState, 500);
  refreshState();
});

stop.addEventListener('click', () => {
  feed.src = '';
  wrap.classList.remove('active');
  start.disabled = false;
  stop.disabled = true;
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