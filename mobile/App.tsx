import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Location from 'expo-location';
import { Accelerometer, Magnetometer } from 'expo-sensors';
import * as Speech from 'expo-speech';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import ViewShot, { captureRef, type ViewShotRef } from 'react-native-view-shot';
import { WebView } from 'react-native-webview';
import { cameraAxisBearing } from './cameraBearing';
import { startScreenShare, type ScreenShareHandle } from './screenShare';
import {
  ActivityIndicator,
  Dimensions,
  Image,
  Linking,
  Modal,
  Pressable,
  Platform,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

const DEFAULT_BACKEND = 'http://10.26.49.63:8765';

type NavigationState = {
  active: boolean;
  guidance: string | null;
  message?: string | null;
  event_id: number;
  distance_remaining: number | null;
  route_geometry?: [number, number][];
  destination?: [number, number] | null;
  target_bearing?: number | null;
  off_route?: boolean;
  arrived?: boolean;
  aligned_to_route?: boolean;
};

type PlaceSuggestion = {
  name: string;
  display_name: string;
  latitude: number;
  longitude: number;
};

type SpokenPrompt = {
  text: string;
  key: string;
  priority: number;
};

function bytesToBase64(bytes: Uint8Array) {
  let binary = '';
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

type MapPosition = { latitude: number; longitude: number; timestamp: number };

function buildMapHtml(position: MapPosition | null, route: [number, number][]) {
  const safeRoute = route.filter(([latitude, longitude]) => Number.isFinite(latitude) && Number.isFinite(longitude));
  const initialPosition = position
    ? { latitude: position.latitude, longitude: position.longitude }
    : null;

  return `<!doctype html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
html,body,#map{height:100%;width:100%;margin:0;background:#e8e5dc}.leaflet-control-attribution{font-size:8px!important}
.endpoint{width:24px;height:24px;border:2px solid white;border-radius:50%;color:white;font:700 12px/20px system-ui;text-align:center;box-shadow:0 1px 5px #333}
.start{background:#188a61}.finish{background:#cb4747}.you{width:16px;height:16px;border:3px solid white;border-radius:50%;background:#2878f0;box-shadow:0 1px 6px #333}
</style></head><body><div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const route=${JSON.stringify(safeRoute)};
const initial=${JSON.stringify(initialPosition)};
const fallback=[13.027,77.497];
const map=L.map('map',{zoomControl:true,attributionControl:true,dragging:true,touchZoom:true,scrollWheelZoom:true}).setView(initial?[initial.latitude,initial.longitude]:fallback,16);
L.tileLayer('https://tile.openstreetmap.de/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(map);
const endpoint=(label,kind)=>L.divIcon({className:'',html:'<div class="endpoint '+kind+'">'+label+'</div>',iconSize:[24,24],iconAnchor:[12,12]});
let currentMarker=null;
if(route.length>1){const path=route.map(([lat,lon])=>[lat,lon]);L.polyline(path,{color:'#2878f0',weight:6,opacity:.95,lineCap:'round',lineJoin:'round'}).addTo(map);L.marker(path[0],{icon:endpoint('A','start')}).addTo(map).bindPopup('Start');L.marker(path[path.length-1],{icon:endpoint('B','finish')}).addTo(map).bindPopup('Destination');map.fitBounds(path,{padding:[28,28],maxZoom:17});}
window.updateGps=(next)=>{if(!next)return;const point=[next.latitude,next.longitude];if(currentMarker)currentMarker.setLatLng(point);else currentMarker=L.marker(point,{icon:L.divIcon({className:'',html:'<div class="you"></div>',iconSize:[16,16],iconAnchor:[8,8]})}).addTo(map).bindPopup('Your location');if(route.length<2)map.panTo(point,{animate:true,duration:.4});};
if(initial)window.updateGps(initial);setTimeout(()=>map.invalidateSize(),100);
</script></body></html>`;
}

function OSMMapSurface({
  position,
  route,
}: {
  position: MapPosition | null;
  route: [number, number][];
}) {
  const mapRef = useRef<WebView<{}>>(null);
  const [html] = useState(() => buildMapHtml(position, route));
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!loaded || !position) return;
    const payload = JSON.stringify({ latitude: position.latitude, longitude: position.longitude });
    mapRef.current?.injectJavaScript(`window.updateGps(${payload}); true;`);
  }, [loaded, position]);

  return (
    <WebView<{}>
      ref={mapRef}
      style={StyleSheet.absoluteFill}
      source={{ html, baseUrl: 'https://safestride.local' }}
      originWhitelist={['*']}
      javaScriptEnabled
      domStorageEnabled
      scrollEnabled={false}
      setSupportMultipleWindows={false}
      onLoadEnd={() => setLoaded(true)}
    />
  );
}

function LiveMapInset({
  position,
  route,
}: {
  position: MapPosition | null;
  route: [number, number][];
}) {
  const [now, setNow] = useState(Date.now());
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const routeKey = route.length > 1
    ? `${route.length}:${route[0].join(',')}:${route[route.length - 1].join(',')}`
    : position ? 'current-position' : 'waiting';
  const fresh = position !== null && now - position.timestamp < 10_000;

  return (
    <View style={styles.mapInset}>
      <OSMMapSurface key={`${routeKey}:inset`} position={position} route={route} />
      {!position && <Text style={styles.mapWaiting}>Waiting for GPS</Text>}
      <View style={styles.mapStatus}><View style={[styles.mapStatusDot, fresh && styles.mapStatusDotLive]} /><Text style={styles.mapStatusText}>{fresh ? 'GPS LIVE' : position ? 'GPS STALE' : 'GPS WAIT'}</Text></View>
      <Text style={styles.mapAttribution}>© OpenStreetMap contributors</Text>
      <Pressable style={styles.mapExpandButton} accessibilityRole="button" accessibilityLabel="Expand interactive map" onPress={() => setExpanded(true)}>
        <Text style={styles.mapExpandText}>Expand</Text>
      </Pressable>
      <Modal visible={expanded} animationType="slide" onRequestClose={() => setExpanded(false)}>
        <View style={styles.expandedMap}>
          <OSMMapSurface key={`${routeKey}:full`} position={position} route={route} />
          <Pressable style={styles.mapCloseButton} accessibilityRole="button" onPress={() => setExpanded(false)}>
            <Text style={styles.mapCloseText}>Close map</Text>
          </Pressable>
          <View style={styles.expandedMapStatus}><View style={[styles.mapStatusDot, fresh && styles.mapStatusDotLive]} /><Text style={styles.mapStatusText}>{fresh ? 'GPS LIVE' : position ? 'GPS STALE' : 'GPS WAIT'}</Text></View>
          <Text style={styles.expandedMapAttribution}>© OpenStreetMap contributors</Text>
        </View>
      </Modal>
    </View>
  );
}

export default function App() {
  const [permission, requestPermission] = useCameraPermissions();
  const camera = useRef<CameraView>(null);
  const screenCaptureRoot = useRef<ViewShotRef>(null);
  const [backend, setBackend] = useState(DEFAULT_BACKEND);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [image, setImage] = useState<string | null>(null);
  const [status, setStatus] = useState('Ready');
  const [alert, setAlert] = useState('No active safety alert');
  const [safetyActive, setSafetyActive] = useState(false);
  const [safetyUrgent, setSafetyUrgent] = useState(false);
  const [depth, setDepth] = useState(false);
  const [fps, setFps] = useState(0);
  const [destination, setDestination] = useState('');
  const [destinationSuggestions, setDestinationSuggestions] = useState<PlaceSuggestion[]>([]);
  const [destinationSearching, setDestinationSearching] = useState(false);
  const [destinationSearchProvider, setDestinationSearchProvider] = useState<string | null>(null);
  const [selectedDestination, setSelectedDestination] = useState<PlaceSuggestion | null>(null);
  const [routeStatus, setRouteStatus] = useState('No active route');
  const [locationStatus, setLocationStatus] = useState('Location inactive');
  const [mapPosition, setMapPosition] = useState<MapPosition | null>(null);
  const [screenShareActive, setScreenShareActive] = useState(false);
  const [screenShareStarting, setScreenShareStarting] = useState(false);
  const [screenShareStatus, setScreenShareStatus] = useState('Screen share is off');
  const [screenViewerUrl, setScreenViewerUrl] = useState<string | null>(null);
  const [headingStatus, setHeadingStatus] = useState('Camera direction unavailable');
  const [navigation, setNavigation] = useState<NavigationState>({
    active: false, guidance: null, event_id: 0, distance_remaining: null,
  });
  const lastSafetyEvent = useRef(0);
  const lastNavigationEvent = useRef(0);
  const safetyActiveRef = useRef(false);
  const currentSpeech = useRef<(SpokenPrompt & { token: number }) | null>(null);
  const pendingSpeech = useRef<SpokenPrompt | null>(null);
  const speechToken = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runningRef = useRef(false);
  const locationWatcher = useRef<Location.LocationSubscription | null>(null);
  const screenShareRef = useRef<ScreenShareHandle | null>(null);
  const headingWatcher = useRef<Location.LocationSubscription | null>(null);
  const accelerometerWatcher = useRef<{ remove: () => void } | null>(null);
  const magnetometerWatcher = useRef<{ remove: () => void } | null>(null);
  const accelerationRef = useRef<{ x: number; y: number; z: number; receivedAt: number } | null>(null);
  const magneticFieldRef = useRef<{ x: number; y: number; z: number; receivedAt: number } | null>(null);
  const declinationRef = useRef<number | null>(null);
  const cameraBearingRef = useRef<number | null>(null);
  const headingTimestampRef = useRef<number | null>(null);
  const currentPosition = useRef<Location.LocationObject | null>(null);
  const lastHeadingPost = useRef(0);
  const headingPostInFlight = useRef(false);

  useEffect(() => {
    const query = destination.trim();
    if (query.length < 3 || selectedDestination?.display_name === query) {
      setDestinationSuggestions([]);
      setDestinationSearching(false);
      setDestinationSearchProvider(null);
      return;
    }

    const controller = new AbortController();
    const timeout = setTimeout(async () => {
      setDestinationSearching(true);
      try {
        const response = await fetch(
          `${backend.replace(/\/$/, '')}/places?q=${encodeURIComponent(query)}`,
          { signal: controller.signal },
        );
        if (!response.ok) throw new Error(`Place search failed (${response.status})`);
        const result = await response.json();
        if (!controller.signal.aborted) {
          setDestinationSuggestions(result.suggestions ?? []);
          setDestinationSearchProvider(result.provider ?? null);
        }
      } catch {
        if (!controller.signal.aborted) setDestinationSuggestions([]);
      } finally {
        if (!controller.signal.aborted) setDestinationSearching(false);
      }
    }, 1000);

    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [backend, destination, selectedDestination]);

  useEffect(() => () => {
    void screenShareRef.current?.stop();
  }, []);

  function cardinalDirection(degrees: number) {
    return ['north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest'][
      Math.round(degrees / 45) % 8
    ];
  }

  function refreshCameraBearing() {
    const acceleration = accelerationRef.current;
    const magneticField = magneticFieldRef.current;
    const declination = declinationRef.current;
    const now = Date.now();
    if (!acceleration || !magneticField || declination === null
      || now - acceleration.receivedAt > 1500 || now - magneticField.receivedAt > 1500) {
      cameraBearingRef.current = null;
      headingTimestampRef.current = null;
      return;
    }

    const bearing = cameraAxisBearing(magneticField, acceleration, declination);
    cameraBearingRef.current = bearing;
    headingTimestampRef.current = bearing === null ? null : now;
    publishCameraHeading();
  }

  function publishCameraHeading() {
    const position = currentPosition.current;
    const now = Date.now();
    if (!position || cameraBearingRef.current === null || headingPostInFlight.current
      || now - lastHeadingPost.current < 750) return;

    lastHeadingPost.current = now;
    headingPostInFlight.current = true;
    void publishLocation(position)
      .catch((error) => setLocationStatus(error instanceof Error ? error.message : 'Location update failed'))
      .finally(() => { headingPostInFlight.current = false; });
  }

  function startCameraOrientationUpdates() {
    if (accelerometerWatcher.current || magnetometerWatcher.current) return;
    Accelerometer.setUpdateInterval(100);
    Magnetometer.setUpdateInterval(100);
    accelerometerWatcher.current = Accelerometer.addListener(({ x, y, z }) => {
      accelerationRef.current = { x, y, z, receivedAt: Date.now() };
      refreshCameraBearing();
    });
    magnetometerWatcher.current = Magnetometer.addListener(({ x, y, z }) => {
      magneticFieldRef.current = { x, y, z, receivedAt: Date.now() };
      refreshCameraBearing();
    });
  }

  function stopCameraOrientationUpdates() {
    accelerometerWatcher.current?.remove();
    magnetometerWatcher.current?.remove();
    accelerometerWatcher.current = null;
    magnetometerWatcher.current = null;
    accelerationRef.current = null;
    magneticFieldRef.current = null;
    declinationRef.current = null;
    cameraBearingRef.current = null;
    headingTimestampRef.current = null;
  }

  function rememberPrompt(prompt: SpokenPrompt) {
    if (!pendingSpeech.current || prompt.priority >= pendingSpeech.current.priority) {
      pendingSpeech.current = prompt;
    }
  }

  function startPrompt(prompt: SpokenPrompt) {
    const token = ++speechToken.current;
    currentSpeech.current = { ...prompt, token };
    Speech.speak(prompt.text, {
      rate: prompt.priority >= 4 ? 1 : 0.85,
      pitch: prompt.priority >= 4 ? 1 : 0.85,
      onDone: () => finishPrompt(token),
      onStopped: () => finishPrompt(token),
      onError: () => finishPrompt(token),
    });
  }

  function finishPrompt(token: number) {
    if (currentSpeech.current?.token !== token) return;
    currentSpeech.current = null;
    const next = pendingSpeech.current;
    if (next && !safetyActiveRef.current) {
      pendingSpeech.current = null;
      startPrompt(next);
    }
  }

  function speakPrompt(prompt: SpokenPrompt) {
    if (safetyActiveRef.current && prompt.priority < 4) {
      rememberPrompt(prompt);
      return;
    }
    const current = currentSpeech.current;
    if (!current) {
      startPrompt(prompt);
      return;
    }
    if (prompt.priority > current.priority) {
      if (current.priority < 4) rememberPrompt(current);
      currentSpeech.current = null;
      Speech.stop();
      startPrompt(prompt);
      return;
    }
    if (prompt.key !== current.key) rememberPrompt(prompt);
  }

  function updateSafetyState(state: any) {
    const active = Boolean(state?.safety_active);
    const wasActive = safetyActiveRef.current;
    safetyActiveRef.current = active;
    setSafetyActive(active);
    setSafetyUrgent(Boolean(state?.safety_urgent));
    setAlert(active ? (state.active_alert ?? 'Safety hazard detected') : 'No active safety alert');
    if (active && !wasActive && currentSpeech.current && currentSpeech.current.priority < 4) {
      rememberPrompt(currentSpeech.current);
      currentSpeech.current = null;
      Speech.stop();
    }
    if (!active && !currentSpeech.current && pendingSpeech.current) {
      const next = pendingSpeech.current;
      pendingSpeech.current = null;
      startPrompt(next);
    }
  }

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
    locationWatcher.current?.remove();
    headingWatcher.current?.remove();
    stopCameraOrientationUpdates();
    speechToken.current += 1;
    currentSpeech.current = null;
    pendingSpeech.current = null;
    Speech.stop();
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      refreshCameraBearing();
      const heading = cameraBearingRef.current;
      const timestamp = headingTimestampRef.current;
      if (heading === null || timestamp === null) {
        setHeadingStatus('Camera direction unavailable');
        return;
      }
      const ageSeconds = Math.floor((Date.now() - timestamp) / 1000);
      setHeadingStatus(ageSeconds > 5
        ? 'Camera direction unavailable'
        : `Camera facing ${cardinalDirection(heading)} (${Math.round(heading)} degrees)`);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  function applyNavigation(state: any) {
    const position = currentPosition.current;
    if (!position || Date.now() - position.timestamp > 10_000) {
      setRouteStatus('GPS position is stale. Stop until location updates resume.');
      return;
    }
    const next = state?.navigation;
    if (!next) return;
    setNavigation(next);
    const guidance = next.message ?? next.guidance;
    setRouteStatus(next.active ? (guidance ?? 'Route active') : 'No active route');
    if (guidance && next.event_id !== lastNavigationEvent.current) {
      lastNavigationEvent.current = next.event_id;
      const lowerGuidance = guidance.toLowerCase();
      const priority = lowerGuidance.includes('face the road') ? 3
        : lowerGuidance.includes('arrived') || lowerGuidance.includes('route ready') ? 1 : 2;
      speakPrompt({ text: guidance, key: `navigation:${next.event_id}`, priority });
    }
  }

  async function publishLocation(position: Location.LocationObject) {
    currentPosition.current = position;
    setMapPosition({
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      timestamp: position.timestamp,
    });
    const { latitude, longitude, accuracy, speed } = position.coords;
    const facing = cameraBearingRef.current;
    const headingTimestamp = headingTimestampRef.current;
    setLocationStatus(`${latitude.toFixed(5)}, ${longitude.toFixed(5)}`);
    const response = await fetch(`${backend.replace(/\/$/, '')}/location`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        latitude, longitude, accuracy, heading: facing, heading_timestamp: headingTimestamp,
        heading_age_ms: headingTimestamp === null ? null : Math.max(0, Date.now() - headingTimestamp),
        speed, timestamp: position.timestamp,
      }),
    });
    if (!response.ok) throw new Error(`Location update rejected (${response.status})`);
    const state = await fetch(`${backend.replace(/\/$/, '')}/state`).then((result) => result.json());
    applyNavigation(state);
  }

  async function ensureCurrentLocation() {
    let permission = await Location.getForegroundPermissionsAsync();
    if (permission.status !== Location.PermissionStatus.GRANTED) {
      permission = await Location.requestForegroundPermissionsAsync();
    }
    if (permission.status !== Location.PermissionStatus.GRANTED) {
      setLocationStatus('Location permission denied');
      throw new Error('Allow location permission before creating a route');
    }
    setLocationStatus('Finding current location');
    await publishLocation(await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }));
    startCameraOrientationUpdates();
    if (!headingWatcher.current) {
      headingWatcher.current = await Location.watchHeadingAsync((heading) => {
        if (heading.accuracy > 0 && heading.magHeading >= 0 && heading.trueHeading >= 0) {
          declinationRef.current = heading.trueHeading - heading.magHeading;
        }
        refreshCameraBearing();
      });
    }
  }

  async function startLocationUpdates() {
    await ensureCurrentLocation();
    if (!locationWatcher.current) {
      locationWatcher.current = await Location.watchPositionAsync(
        { accuracy: Location.Accuracy.High, distanceInterval: 0, timeInterval: 1000 },
        async (position) => {
          try {
            await publishLocation(position);
          } catch (error) {
            setLocationStatus(error instanceof Error ? error.message : 'Location update failed');
          }
        },
      );
    }
  }

  async function setRoute() {
    if (!destination.trim()) return;
    try {
      await ensureCurrentLocation();
      const response = await fetch(`${backend.replace(/\/$/, '')}/route`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          destination: selectedDestination?.display_name ?? destination.trim(),
          destination_coordinates: selectedDestination
            ? [selectedDestination.latitude, selectedDestination.longitude]
            : undefined,
        }),
      });
      if (!response.ok) {
        const body = await response.text();
        const detail = body.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
        throw new Error(detail || `Route failed (${response.status})`);
      }
      const result = await response.json();
      applyNavigation({ navigation: result.navigation });
    } catch (error) {
      setRouteStatus(error instanceof Error ? error.message : 'Route failed');
    }
  }

  async function openInGoogleMaps() {
    const query = selectedDestination?.display_name ?? destination.trim();
    if (!query) return;
    try {
      await Linking.openURL(`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`);
    } catch {
      setRouteStatus('Could not open Google Maps');
    }
  }

  async function sendFrame() {
    if (!runningRef.current || busy || !camera.current) return;
    setBusy(true);
    try {
      const photo = await camera.current.takePictureAsync({
        base64: true,
        quality: 0.65,
        skipProcessing: true,
      });
      if (!photo?.base64) throw new Error('Camera returned no frame');
      const response = await fetch(`${backend.replace(/\/$/, '')}/frame`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: photo.base64 }),
      });
      if (!response.ok) throw new Error(`Backend error ${response.status}`);
      const result = await response.json();
      setImage(`data:image/jpeg;base64,${result.image}`);
      const state = result.state;
      setStatus(state.status ?? 'Monitoring');
      setDepth(Boolean(state.depth));
      setFps(Number(state.fps) || 0);
      updateSafetyState(state);
      if (state.alert_id !== lastSafetyEvent.current) {
        lastSafetyEvent.current = state.alert_id;
        if (state.alert) {
          speakPrompt({
            text: state.alert,
            key: `safety:${state.alert_id}`,
            priority: state.alert_urgent ? 5 : 4,
          });
        }
      }
      applyNavigation(state);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Connection failed');
    } finally {
      setBusy(false);
      if (runningRef.current) timer.current = setTimeout(sendFrame, 180);
    }
  }

  async function startMonitoring() {
    runningRef.current = true;
    setRunning(true);
    setStatus('Connecting');
    await startLocationUpdates();
    timer.current = setTimeout(sendFrame, 250);
  }

  function stopMonitoring() {
    runningRef.current = false;
    setRunning(false);
    setStatus('Stopped');
    locationWatcher.current?.remove();
    locationWatcher.current = null;
    headingWatcher.current?.remove();
    headingWatcher.current = null;
    stopCameraOrientationUpdates();
    speechToken.current += 1;
    currentSpeech.current = null;
    pendingSpeech.current = null;
    safetyActiveRef.current = false;
    setSafetyActive(false);
    setSafetyUrgent(false);
    setAlert('No active safety alert');
    Speech.stop();
    if (timer.current) clearTimeout(timer.current);
  }

  async function stopScreenSharing() {
    const share = screenShareRef.current;
    screenShareRef.current = null;
    setScreenShareActive(false);
    setScreenViewerUrl(null);
    setScreenShareStatus('Screen share stopped');
    await share?.stop();
  }

  async function startScreenSharing() {
    if (Platform.OS !== 'android') {
      setScreenShareStatus('Screen sharing is available in the Android build');
      return;
    }
    setScreenShareStarting(true);
    setScreenShareStatus('Starting live app preview');
    try {
      const share = await startScreenShare(backend, {
        onStatus: setScreenShareStatus,
        onViewerUrl: setScreenViewerUrl,
        captureFrame: async () => {
          const target = screenCaptureRoot.current;
          if (!target) throw new Error('App view is not ready to capture');
          const { width, height } = Dimensions.get('window');
          const outputWidth = 480;
          return captureRef(target, {
            format: 'jpg',
            quality: 0.42,
            result: 'base64',
            width: outputWidth,
            height: Math.round(outputWidth * height / width),
          });
        },
        onStopped: () => {
          screenShareRef.current = null;
          setScreenShareActive(false);
          setScreenViewerUrl(null);
        },
      });
      screenShareRef.current = share;
      setScreenShareActive(true);
    } catch (error) {
      setScreenViewerUrl(null);
      setScreenShareStatus(error instanceof Error ? error.message : 'Could not start screen share');
    } finally {
      setScreenShareStarting(false);
    }
  }

  if (!permission) return <View style={styles.center}><ActivityIndicator color="#8ce3c3" /></View>;
  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.center}>
        <Text style={styles.eyebrow}>SAFESTRIDE MOBILE</Text>
        <Text style={styles.title}>Camera access is required</Text>
        <Pressable style={styles.primaryButton} onPress={requestPermission}>
          <Text style={styles.primaryText}>Allow camera</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  return (
    <ViewShot ref={screenCaptureRoot} style={styles.container}>
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
      <StatusBar style="light" />
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>SAFESTRIDE MOBILE</Text>
          <Text style={styles.title}>Path awareness</Text>
        </View>
        <View style={[styles.livePill, running && styles.livePillActive]}>
          <Text style={styles.liveText}>{running ? 'LIVE' : 'STANDBY'}</Text>
        </View>
      </View>
      <View style={styles.preview}>
        <CameraView ref={camera} style={StyleSheet.absoluteFill} facing="back" />
        {image && <Image source={{ uri: image }} style={styles.annotated} resizeMode="cover" />}
        {!image && <Text style={styles.previewHint}>Annotated feed appears here</Text>}
      </View>
      <TextInput
        value={backend}
        onChangeText={setBackend}
        autoCapitalize="none"
        autoCorrect={false}
        placeholder="Backend URL"
        placeholderTextColor="#71808b"
        style={styles.input}
      />
      <View style={styles.screenShareBox}>
        <View style={styles.screenShareHeader}>
          <Text style={styles.eyebrow}>LIVE SCREEN SHARE</Text>
          <Text style={styles.screenShareStatus}>{screenShareStatus}</Text>
        </View>
        <Pressable
          style={[styles.screenShareButton, screenShareActive && styles.screenShareStop]}
          onPress={screenShareActive ? stopScreenSharing : startScreenSharing}
          disabled={screenShareStarting}
        >
          <Text style={styles.screenShareButtonText}>
            {screenShareStarting ? 'Starting…' : screenShareActive ? 'Stop screen share' : 'Share app screen'}
          </Text>
        </Pressable>
        {screenViewerUrl && (
          <View>
            <Text style={styles.screenShareNote}>Open this private link on your laptop while sharing is active:</Text>
            <Text selectable style={styles.screenViewerUrl}>{screenViewerUrl}</Text>
          </View>
        )}
      </View>
      <View style={styles.routeRow}>
        <TextInput
          value={destination}
          onChangeText={(value) => {
            setDestination(value);
            setSelectedDestination(null);
            setDestinationSearchProvider(null);
          }}
          placeholder="Search nearby places or type a destination"
          placeholderTextColor="#71808b"
          style={[styles.input, styles.destinationInput]}
        />
        <Pressable style={styles.routeButton} onPress={setRoute}>
          <Text style={styles.routeText}>Route</Text>
        </Pressable>
      </View>
      <Pressable style={styles.googleMapsButton} onPress={openInGoogleMaps}>
        <Text style={styles.googleMapsText}>Open in Google Maps</Text>
      </Pressable>
      {destinationSearching && <Text style={styles.searchStatus}>Searching nearby places…</Text>}
      {destinationSearchProvider && (
        <Text style={styles.searchStatus}>
          'OpenStreetMap results (Photon)'
        </Text>
      )}
      {destinationSuggestions.length > 0 && (
        <View style={styles.suggestionList}>
          {destinationSuggestions.map((suggestion) => (
            <Pressable
              key={`${suggestion.latitude}:${suggestion.longitude}`}
              style={styles.suggestionItem}
              onPress={() => {
                setDestination(suggestion.display_name);
                setSelectedDestination(suggestion);
                setDestinationSuggestions([]);
              }}
            >
              <Text style={styles.suggestionName}>{suggestion.name}</Text>
              <Text style={styles.suggestionAddress} numberOfLines={2}>{suggestion.display_name}</Text>
            </Pressable>
          ))}
        </View>
      )}
      <LiveMapInset position={mapPosition} route={navigation.route_geometry ?? []} />
      <View style={styles.navigationBox}>
        <Text style={styles.eyebrow}>NAVIGATION</Text>
        <Text style={styles.navigationText}>{routeStatus}</Text>
        {navigation.distance_remaining !== null && (
          <Text style={styles.locationText}>
            {navigation.arrived ? 'Arrived' : `${Math.round(navigation.distance_remaining)} m remaining`}
          </Text>
        )}
        {navigation.off_route && <Text style={styles.routeWarning}>Off route</Text>}
        {navigation.target_bearing !== null && navigation.target_bearing !== undefined && (
          <Text style={styles.locationText}>
            Road direction: {cardinalDirection(navigation.target_bearing)} ({Math.round(navigation.target_bearing)} degrees)
          </Text>
        )}
        <Text style={styles.locationText}>{locationStatus}</Text>
        <Text style={styles.locationText}>{headingStatus}</Text>
      </View>
      <View style={styles.stats}>
        <Stat label="STATUS" value={status} />
        <Stat label="DEPTH" value={depth ? 'ACTIVE' : 'OFF'} />
        <Stat label="FPS" value={fps ? `${fps.toFixed(1)}` : '--'} />
      </View>
      <View style={[styles.alertBox, safetyActive && (safetyUrgent ? styles.alertUrgent : styles.alertCaution)]}>
        <Text style={styles.eyebrow}>{safetyActive ? (safetyUrgent ? 'STOP / URGENT' : 'SAFETY CAUTION') : 'SAFETY CLEAR'}</Text>
        <Text style={styles.alert}>{alert}</Text>
      </View>
      <Pressable style={[styles.primaryButton, running && styles.stopButton]} onPress={running ? stopMonitoring : startMonitoring}>
        <Text style={styles.primaryText}>{running ? 'Stop monitoring' : 'Start monitoring'}</Text>
      </Pressable>
      <StatusBar style="auto" />
      </ScrollView>
    </SafeAreaView>
    </ViewShot>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <View style={styles.stat}><Text style={styles.statLabel}>{label}</Text><Text style={styles.statValue}>{value}</Text></View>;
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: '#0b1418', alignItems: 'center', justifyContent: 'center', padding: 28 },
  container: {
    flex: 1,
    backgroundColor: '#0b1418',
    paddingHorizontal: 18,
    paddingTop: 12,
  },
  content: { paddingBottom: 28 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 },
  eyebrow: { color: '#8ce3c3', fontSize: 11, fontWeight: '700', letterSpacing: 1.5 },
  title: { color: '#f1f7f4', fontSize: 30, fontWeight: '700', marginTop: 5 },
  livePill: { borderColor: '#53636b', borderWidth: 1, paddingHorizontal: 12, paddingVertical: 7 },
  livePillActive: { borderColor: '#8ce3c3' },
  liveText: { color: '#8ce3c3', fontSize: 11, fontWeight: '700' },
  preview: { backgroundColor: '#162329', borderColor: '#31434a', borderWidth: 1, borderRadius: 8, height: 310, overflow: 'hidden', alignItems: 'center', justifyContent: 'center' },
  annotated: { width: '100%', height: '100%' },
  previewHint: { color: '#9aabb2', fontSize: 14 },
  mapInset: { height: 180, width: '100%', overflow: 'hidden', borderColor: '#31434a', borderWidth: 1, borderRadius: 7, backgroundColor: '#24343a', marginTop: 12 },
  mapStatus: { position: 'absolute', top: 5, left: 5, flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'rgba(11,20,24,0.86)', paddingHorizontal: 6, paddingVertical: 4, borderRadius: 3 },
  mapStatusDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#ffb86b' },
  mapStatusDotLive: { backgroundColor: '#8ce3c3' },
  mapStatusText: { color: '#f1f7f4', fontSize: 9, fontWeight: '800' },
  mapWaiting: { position: 'absolute', alignSelf: 'center', top: 92, color: '#f1f7f4', fontSize: 10, fontWeight: '700' },
  mapAttribution: { position: 'absolute', right: 3, bottom: 2, backgroundColor: 'rgba(255,255,255,0.82)', color: '#24343a', fontSize: 8, paddingHorizontal: 3 },
  mapExpandButton: { position: 'absolute', top: 5, right: 5, backgroundColor: 'rgba(11,20,24,0.88)', paddingHorizontal: 8, paddingVertical: 5, borderRadius: 4 },
  mapExpandText: { color: '#ffffff', fontSize: 10, fontWeight: '800' },
  expandedMap: { flex: 1, backgroundColor: '#ffffff' },
  mapCloseButton: { position: 'absolute', top: 48, right: 14, backgroundColor: '#0b1418', paddingHorizontal: 12, paddingVertical: 9, borderRadius: 5, elevation: 4 },
  mapCloseText: { color: '#ffffff', fontSize: 13, fontWeight: '700' },
  expandedMapStatus: { position: 'absolute', top: 48, left: 14, flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: 'rgba(11,20,24,0.88)', paddingHorizontal: 8, paddingVertical: 7, borderRadius: 4 },
  expandedMapAttribution: { position: 'absolute', right: 5, bottom: 5, backgroundColor: 'rgba(255,255,255,0.9)', color: '#24343a', fontSize: 10, paddingHorizontal: 4, paddingVertical: 2 },
  screenShareBox: { backgroundColor: '#142127', borderLeftColor: '#8ce3c3', borderLeftWidth: 3, padding: 12, marginTop: 12, borderRadius: 4 },
  screenShareHeader: { gap: 5, marginBottom: 9 },
  screenShareStatus: { color: '#bac8cc', fontSize: 12 },
  screenShareButton: { alignItems: 'center', backgroundColor: '#8ce3c3', paddingVertical: 11, borderRadius: 5 },
  screenShareStop: { backgroundColor: '#dc7668' },
  screenShareButtonText: { color: '#0b1418', fontWeight: '800' },
  screenShareNote: { color: '#9aabb2', fontSize: 11, marginTop: 9 },
  screenViewerUrl: { color: '#8ce3c3', fontSize: 11, marginTop: 5 },
  input: { backgroundColor: '#142127', borderColor: '#31434a', borderWidth: 1, color: '#f1f7f4', marginTop: 14, paddingHorizontal: 13, paddingVertical: 12, borderRadius: 6 },
  routeRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  searchStatus: { color: '#9aabb2', fontSize: 12, marginTop: 8 },
  suggestionList: { backgroundColor: '#142127', borderColor: '#31434a', borderWidth: 1, marginTop: 4 },
  suggestionItem: { paddingHorizontal: 12, paddingVertical: 10, borderBottomColor: '#31434a', borderBottomWidth: StyleSheet.hairlineWidth },
  suggestionName: { color: '#f1f7f4', fontSize: 14, fontWeight: '700' },
  suggestionAddress: { color: '#9aabb2', fontSize: 11, marginTop: 3 },
  destinationInput: { flex: 1 },
  routeButton: { backgroundColor: '#294b4b', borderRadius: 6, marginTop: 14, paddingHorizontal: 15, paddingVertical: 14 },
  routeText: { color: '#8ce3c3', fontWeight: '800' },
  googleMapsButton: { alignSelf: 'flex-start', paddingVertical: 10, paddingHorizontal: 2 },
  googleMapsText: { color: '#8ce3c3', fontSize: 13, fontWeight: '700', textDecorationLine: 'underline' },
  stats: { flexDirection: 'row', gap: 8, marginTop: 12 },
  stat: { flex: 1, backgroundColor: '#142127', padding: 11, borderRadius: 6 },
  statLabel: { color: '#8a9aa1', fontSize: 10, fontWeight: '700' },
  statValue: { color: '#f1f7f4', fontSize: 15, fontWeight: '700', marginTop: 5 },
  alertBox: { backgroundColor: '#142127', borderLeftColor: '#8ce3c3', borderLeftWidth: 3, padding: 14, marginTop: 12, marginBottom: 14 },
  alertUrgent: { borderLeftColor: '#ff625e', backgroundColor: '#301b1b' },
  alertCaution: { borderLeftColor: '#f2bd57', backgroundColor: '#2b281d' },
  alert: { color: '#f1f7f4', fontSize: 17, fontWeight: '600', marginTop: 7 },
  navigationBox: { backgroundColor: '#142127', borderLeftColor: '#8ca9e3', borderLeftWidth: 3, padding: 14, marginTop: 12, marginBottom: 14 },
  navigationText: { color: '#f1f7f4', fontSize: 16, fontWeight: '600', marginTop: 7 },
  locationText: { color: '#8a9aa1', fontSize: 12, marginTop: 7 },
  routeWarning: { color: '#ffb86b', fontSize: 13, fontWeight: '800', marginTop: 7 },
  primaryButton: { alignItems: 'center', backgroundColor: '#8ce3c3', borderRadius: 6, paddingVertical: 15 },
  stopButton: { backgroundColor: '#dc7668' },
  primaryText: { color: '#0b1418', fontSize: 16, fontWeight: '800' },
});
