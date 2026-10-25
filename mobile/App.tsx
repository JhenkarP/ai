import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Location from 'expo-location';
import * as Speech from 'expo-speech';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
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
  off_route?: boolean;
  arrived?: boolean;
  aligned_to_route?: boolean;
};

function bytesToBase64(bytes: Uint8Array) {
  let binary = '';
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

export default function App() {
  const [permission, requestPermission] = useCameraPermissions();
  const camera = useRef<CameraView>(null);
  const [backend, setBackend] = useState(DEFAULT_BACKEND);
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [image, setImage] = useState<string | null>(null);
  const [status, setStatus] = useState('Ready');
  const [alert, setAlert] = useState('No active alert');
  const [depth, setDepth] = useState(false);
  const [fps, setFps] = useState(0);
  const [destination, setDestination] = useState('');
  const [routeStatus, setRouteStatus] = useState('No active route');
  const [locationStatus, setLocationStatus] = useState('Location inactive');
  const [headingStatus, setHeadingStatus] = useState('Facing unavailable');
  const [navigation, setNavigation] = useState<NavigationState>({
    active: false, guidance: null, event_id: 0, distance_remaining: null,
  });
  const lastAlert = useRef('');
  const lastNavigationEvent = useRef(0);
  const navigationActive = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runningRef = useRef(false);
  const locationWatcher = useRef<Location.LocationSubscription | null>(null);
  const headingWatcher = useRef<Location.LocationSubscription | null>(null);
  const headingRef = useRef<number | null>(null);
  const lastSpokenCardinal = useRef('');

  function cardinalDirection(degrees: number) {
    return ['north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest'][
      Math.round(degrees / 45) % 8
    ];
  }

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
    locationWatcher.current?.remove();
    headingWatcher.current?.remove();
    Speech.stop();
  }, []);

  function applyNavigation(state: any) {
    const next = state?.navigation;
    if (!next) return;
    setNavigation(next);
    const guidance = next.message ?? next.guidance;
    navigationActive.current = Boolean(next.active);
    setRouteStatus(next.active ? (guidance ?? 'Route active') : 'No active route');
    if (guidance && next.event_id !== lastNavigationEvent.current && !state?.urgent) {
      lastNavigationEvent.current = next.event_id;
      Speech.speak(guidance, { rate: 0.85, pitch: 0.85 });
    }
  }

  async function publishLocation(position: Location.LocationObject) {
    const { latitude, longitude, accuracy, heading, speed } = position.coords;
    const facing = headingRef.current ?? heading;
    setLocationStatus(`${latitude.toFixed(5)}, ${longitude.toFixed(5)}`);
    if (facing !== null && facing !== undefined && facing >= 0) {
      setHeadingStatus(`Facing ${cardinalDirection(facing)} (${Math.round(facing)} degrees)`);
    }
    await fetch(`${backend.replace(/\/$/, '')}/location`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ latitude, longitude, accuracy, heading: facing, speed, timestamp: position.timestamp }),
    });
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
    if (!headingWatcher.current) {
      headingWatcher.current = await Location.watchHeadingAsync((heading) => {
        const facing = heading.trueHeading >= 0 ? heading.trueHeading : heading.magHeading;
        if (facing >= 0) {
          headingRef.current = facing;
          const cardinal = cardinalDirection(facing);
          setHeadingStatus(`Facing ${cardinal} (${Math.round(facing)} degrees)`);
          if (navigationActive.current && cardinal !== lastSpokenCardinal.current) {
            lastSpokenCardinal.current = cardinal;
            Speech.speak(`You are facing ${cardinal}.`, { rate: 0.85, pitch: 0.85 });
          }
        }
      });
    }
  }

  async function startLocationUpdates() {
    await ensureCurrentLocation();
    if (!locationWatcher.current) {
      locationWatcher.current = await Location.watchPositionAsync(
        { accuracy: Location.Accuracy.High, distanceInterval: 5, timeInterval: 3000 },
        async (position) => {
          try {
            await publishLocation(position);
          } catch (_) {
            setLocationStatus('Location update failed');
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
        body: JSON.stringify({ destination: destination.trim() }),
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
      setAlert(state.alert ?? 'No active alert');
      setDepth(Boolean(state.depth));
      setFps(Number(state.fps) || 0);
      applyNavigation(state);
      if (state.alert && state.alert !== lastAlert.current) {
        lastAlert.current = state.alert;
        Speech.stop();
        Speech.speak(state.alert, { rate: 0.95, pitch: 1.0 });
      }
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
    if (timer.current) clearTimeout(timer.current);
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
      <View style={styles.routeRow}>
        <TextInput
          value={destination}
          onChangeText={setDestination}
          placeholder="Destination, e.g. NIE campus"
          placeholderTextColor="#71808b"
          style={[styles.input, styles.destinationInput]}
        />
        <Pressable style={styles.routeButton} onPress={setRoute}>
          <Text style={styles.routeText}>Route</Text>
        </Pressable>
      </View>
      <View style={styles.navigationBox}>
        <Text style={styles.eyebrow}>NAVIGATION</Text>
        <Text style={styles.navigationText}>{routeStatus}</Text>
        {navigation.distance_remaining !== null && (
          <Text style={styles.locationText}>
            {navigation.arrived ? 'Arrived' : `${Math.round(navigation.distance_remaining)} m remaining`}
          </Text>
        )}
        {navigation.off_route && <Text style={styles.routeWarning}>Off route</Text>}
        <Text style={styles.locationText}>{locationStatus}</Text>
        <Text style={styles.locationText}>{headingStatus}</Text>
      </View>
      <View style={styles.stats}>
        <Stat label="STATUS" value={status} />
        <Stat label="DEPTH" value={depth ? 'ACTIVE' : 'OFF'} />
        <Stat label="FPS" value={fps ? `${fps.toFixed(1)}` : '--'} />
      </View>
      <View style={styles.alertBox}>
        <Text style={styles.eyebrow}>CURRENT PRIORITY</Text>
        <Text style={styles.alert}>{alert}</Text>
      </View>
      <Pressable style={[styles.primaryButton, running && styles.stopButton]} onPress={running ? stopMonitoring : startMonitoring}>
        <Text style={styles.primaryText}>{running ? 'Stop monitoring' : 'Start monitoring'}</Text>
      </Pressable>
      <StatusBar style="auto" />
      </ScrollView>
    </SafeAreaView>
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
  input: { backgroundColor: '#142127', borderColor: '#31434a', borderWidth: 1, color: '#f1f7f4', marginTop: 14, paddingHorizontal: 13, paddingVertical: 12, borderRadius: 6 },
  routeRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  destinationInput: { flex: 1 },
  routeButton: { backgroundColor: '#294b4b', borderRadius: 6, marginTop: 14, paddingHorizontal: 15, paddingVertical: 14 },
  routeText: { color: '#8ce3c3', fontWeight: '800' },
  stats: { flexDirection: 'row', gap: 8, marginTop: 12 },
  stat: { flex: 1, backgroundColor: '#142127', padding: 11, borderRadius: 6 },
  statLabel: { color: '#8a9aa1', fontSize: 10, fontWeight: '700' },
  statValue: { color: '#f1f7f4', fontSize: 15, fontWeight: '700', marginTop: 5 },
  alertBox: { backgroundColor: '#142127', borderLeftColor: '#8ce3c3', borderLeftWidth: 3, padding: 14, marginTop: 12, marginBottom: 14 },
  alert: { color: '#f1f7f4', fontSize: 17, fontWeight: '600', marginTop: 7 },
  navigationBox: { backgroundColor: '#142127', borderLeftColor: '#8ca9e3', borderLeftWidth: 3, padding: 14, marginTop: 12, marginBottom: 14 },
  navigationText: { color: '#f1f7f4', fontSize: 16, fontWeight: '600', marginTop: 7 },
  locationText: { color: '#8a9aa1', fontSize: 12, marginTop: 7 },
  routeWarning: { color: '#ffb86b', fontSize: 13, fontWeight: '800', marginTop: 7 },
  primaryButton: { alignItems: 'center', backgroundColor: '#8ce3c3', borderRadius: 6, paddingVertical: 15 },
  stopButton: { backgroundColor: '#dc7668' },
  primaryText: { color: '#0b1418', fontSize: 16, fontWeight: '800' },
});
