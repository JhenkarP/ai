import AsyncStorage from '@react-native-async-storage/async-storage';
import * as FileSystem from 'expo-file-system/legacy';
import * as Location from 'expo-location';
import * as MediaLibrary from 'expo-media-library';
import { Accelerometer, Magnetometer } from 'expo-sensors';
import * as Speech from 'expo-speech';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import MapView, { Marker, Polyline, PROVIDER_GOOGLE } from 'react-native-maps';
import RecordScreen, { RecordingResult } from 'react-native-record-screen';
import { Camera, useCameraDevice, useCameraPermission } from 'react-native-vision-camera';
import ViewShot, { captureRef, type ViewShotRef } from 'react-native-view-shot';
import { cameraAxisBearing } from './cameraBearing';
import VoiceAssistant from './VoiceAssistant';
import type { SceneAnalysis } from './SceneScheduler';
import { startScreenShare, type ScreenShareHandle } from './screenShare';

const BACKEND_STORAGE_KEY = 'safestride.backendUrl';
import {
  ActivityIndicator,
  Alert as NativeAlert,
  Animated,
  AppState,
  Dimensions,
  Image,
  Linking,
  Modal,
  PermissionsAndroid,
  Pressable,
  Platform,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import type { StyleProp, ViewStyle } from 'react-native';

const DEFAULT_BACKEND = 'http://10.166.204.63:8765';

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
  onDone?: () => void;
  expiresAt?: number;
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

function GoogleMapSurface({
  position,
  route,
}: {
  position: MapPosition | null;
  route: [number, number][];
}) {
  const mapRef = useRef<MapView>(null);
  const coordinates = route
    .filter(([latitude, longitude]) => Number.isFinite(latitude) && Number.isFinite(longitude))
    .map(([latitude, longitude]) => ({ latitude, longitude }));
  const routeKey = coordinates.length > 1
    ? coordinates.map(({ latitude, longitude }) => `${latitude},${longitude}`).join(';')
    : '';

  useEffect(() => {
    if (coordinates.length > 1) {
      mapRef.current?.fitToCoordinates(coordinates, {
        edgePadding: { top: 36, right: 36, bottom: 36, left: 36 },
        animated: true,
      });
    }
  }, [routeKey]);

  useEffect(() => {
    if (!position || coordinates.length > 1) return;
    mapRef.current?.animateToRegion({
      latitude: position.latitude,
      longitude: position.longitude,
      latitudeDelta: 0.006,
      longitudeDelta: 0.006,
    }, 350);
  }, [position?.latitude, position?.longitude, routeKey]);

  const initial = position
    ? { latitude: position.latitude, longitude: position.longitude, latitudeDelta: 0.006, longitudeDelta: 0.006 }
    : { latitude: 13.027, longitude: 77.497, latitudeDelta: 0.03, longitudeDelta: 0.03 };

  return (
    <MapView
      ref={mapRef}
      style={StyleSheet.absoluteFill}
      provider={PROVIDER_GOOGLE}
      initialRegion={initial}
      showsCompass
      showsScale
      toolbarEnabled={false}
      loadingEnabled
    >
      {position && <Marker coordinate={position} title="Your location" pinColor="#2878f0" />}
      {coordinates.length > 1 && <>
        <Polyline coordinates={coordinates} strokeColor="#2878f0" strokeWidth={6} />
        <Marker coordinate={coordinates[0]} title="Start" pinColor="#188a61" />
        <Marker coordinate={coordinates[coordinates.length - 1]} title="Destination" pinColor="#cb4747" />
      </>}
    </MapView>
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
      <GoogleMapSurface key={`${routeKey}:inset`} position={position} route={route} />
      {!position && <Text style={styles.mapWaiting}>Waiting for GPS</Text>}
      <View style={styles.mapStatus}><View style={[styles.mapStatusDot, fresh && styles.mapStatusDotLive]} /><Text style={styles.mapStatusText}>{fresh ? 'GPS LIVE' : position ? 'GPS STALE' : 'GPS WAIT'}</Text></View>
        <Text style={styles.mapAttribution}>Powered by Google, ©2026 Google</Text>
      <Pressable style={styles.mapExpandButton} accessibilityRole="button" accessibilityLabel="Expand interactive map" onPress={() => setExpanded(true)}>
        <Text style={styles.mapExpandText}>Expand</Text>
      </Pressable>
      <Modal visible={expanded} animationType="slide" onRequestClose={() => setExpanded(false)}>
        <View style={styles.expandedMap}>
          <GoogleMapSurface key={`${routeKey}:full`} position={position} route={route} />
          <Pressable style={styles.mapCloseButton} accessibilityRole="button" onPress={() => setExpanded(false)}>
            <Text style={styles.mapCloseText}>Close map</Text>
          </Pressable>
          <View style={styles.expandedMapStatus}><View style={[styles.mapStatusDot, fresh && styles.mapStatusDotLive]} /><Text style={styles.mapStatusText}>{fresh ? 'GPS LIVE' : position ? 'GPS STALE' : 'GPS WAIT'}</Text></View>
          <Text style={styles.expandedMapAttribution}>Powered by Google, ©2026 Google</Text>
        </View>
      </Modal>
    </View>
  );
}

const CLOUD_CONSENT_KEY = 'safestride.cloudConsent';

type SetupState = 'pending' | 'ok' | 'fail';

export default function App() {
  const { hasPermission, requestPermission } = useCameraPermission();
  const device = useCameraDevice('back');
  const camera = useRef<Camera>(null);
  const previewReady = useRef(false);
  const voiceListening = useRef(false);
  const cloudSceneConsent = useRef(false);
  const sceneRequestInFlight = useRef(false);
  const screenCaptureRoot = useRef<ViewShotRef>(null);
  const [backend, setBackendState] = useState(DEFAULT_BACKEND);

  function setBackend(value: string) {
    setBackendState(value);
    void AsyncStorage.setItem(BACKEND_STORAGE_KEY, value);
  }

  useEffect(() => {
    void AsyncStorage.getItem(BACKEND_STORAGE_KEY).then((saved) => {
      if (saved) setBackendState(saved);
    });
    void AsyncStorage.getItem(CLOUD_CONSENT_KEY).then((saved) => {
      if (saved === 'granted') cloudSceneConsent.current = true;
    });
  }, []);
  const [running, setRunning] = useState(false);
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
  const [screenRecordingActive, setScreenRecordingActive] = useState(false);
  const [screenRecordingBusy, setScreenRecordingBusy] = useState(false);
  const [screenRecordingStatus, setScreenRecordingStatus] = useState('Screen recording is off');
  const [screenViewerUrl, setScreenViewerUrl] = useState<string | null>(null);
  const [headingStatus, setHeadingStatus] = useState('Camera direction unavailable');
  const [screen, setScreen] = useState<'loading' | 'welcome' | 'navigate'>('loading');
  const screenFade = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    screenFade.setValue(0);
    Animated.timing(screenFade, { toValue: 1, duration: 350, useNativeDriver: true }).start();
  }, [screen]);
  const [setup, setSetup] = useState<{ location: SetupState; backend: SetupState }>({ location: 'pending', backend: 'pending' });

  async function runSetup() {
    setSetup({ location: 'pending', backend: 'pending' });
    const location = await Location.requestForegroundPermissionsAsync().then((r) => r.granted).catch(() => false);
    setSetup((current) => ({ ...current, location: location ? 'ok' : 'fail' }));
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    const reachable = await fetch(`${backend.replace(/\/$/, '')}/state`, { signal: controller.signal })
      .then((r) => r.ok).catch(() => false).finally(() => clearTimeout(timeout));
    setSetup((current) => ({ ...current, backend: reachable ? 'ok' : 'fail' }));
  }

  useEffect(() => {
    if (hasPermission && device) void runSetup();
  }, [hasPermission, device]);

  useEffect(() => {
    if (screen === 'loading' && setup.location === 'ok' && setup.backend === 'ok') setScreen('welcome');
  }, [setup, screen]);
  const [navigation, setNavigation] = useState<NavigationState>({
    active: false, guidance: null, event_id: 0, distance_remaining: null,
  });
  const lastSafetyEvent = useRef(0);
  const lastNavigationEvent = useRef(0);
  const safetyActiveRef = useRef(false);
  const currentSpeech = useRef<(SpokenPrompt & { token: number }) | null>(null);
  const pendingSpeech = useRef<SpokenPrompt | null>(null);
  const speechToken = useRef(0);
  const autoRerouteInFlight = useRef(false);
  const lastAutoRerouteAt = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const runningRef = useRef(false);
  const socketRef = useRef<WebSocket | null>(null);
  const pendingFrames = useRef(0);
  const captureSessionId = useRef('');
  const locationWatcher = useRef<Location.LocationSubscription | null>(null);
  const screenShareRef = useRef<ScreenShareHandle | null>(null);
  const screenRecordingActiveRef = useRef(false);
  const routeConfirmed = useRef(false);
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
          `${backend.replace(/\/$/, '')}/places?q=${encodeURIComponent(query)}&map_provider=google`,
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
    if (!position || cameraBearingRef.current === null || now - lastHeadingPost.current < 750) return;

    if (headingPostInFlight.current) return;

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
    if (prompt.expiresAt !== undefined && Date.now() > prompt.expiresAt) return;
    const token = ++speechToken.current;
    currentSpeech.current = { ...prompt, token };
    Speech.speak(prompt.text, {
      rate: prompt.priority >= 4 ? 1 : 0.85,
      pitch: prompt.priority >= 4 ? 1 : 0.85,
      onDone: () => finishPrompt(token, true),
      onStopped: () => finishPrompt(token),
      onError: () => finishPrompt(token),
    });
  }

  function finishPrompt(token: number, completed = false) {
    if (currentSpeech.current?.token !== token) return;
    const finished = currentSpeech.current;
    currentSpeech.current = null;
    if (completed && !safetyActiveRef.current && finished.onDone) {
      finished.onDone();
      return;
    }
    const next = pendingSpeech.current;
    if (next && (!safetyActiveRef.current || next.priority >= 5)) {
      pendingSpeech.current = null;
      startPrompt(next);
    }
  }

  function speakPrompt(prompt: SpokenPrompt) {
    if (voiceListening.current && prompt.priority < 5) {
      rememberPrompt(prompt);
      return;
    }
    if (safetyActiveRef.current && prompt.priority < 5) {
      rememberPrompt(prompt);
      return;
    }
    const current = currentSpeech.current;
    if (!current) {
      startPrompt(prompt);
      return;
    }
    if (prompt.priority > current.priority) {
      if (current.priority < 5) rememberPrompt(current);
      currentSpeech.current = null;
      Speech.stop();
      startPrompt(prompt);
      return;
    }
    if (prompt.key !== current.key) rememberPrompt(prompt);
  }

  function updateSafetyState(state: any) {
    const active = Boolean(state?.safety_active) && runningRef.current;
    const wasActive = safetyActiveRef.current;
    safetyActiveRef.current = active;
    setSafetyActive(active);
    setSafetyUrgent(Boolean(state?.safety_urgent));
    setAlert(active ? (state.active_alert ?? 'Safety hazard detected') : 'No active safety alert');
    if (active && !wasActive && currentSpeech.current && currentSpeech.current.priority < 5) {
      rememberPrompt(currentSpeech.current);
      currentSpeech.current = null;
      Speech.stop();
    }
    if (active && !wasActive && cloudSceneConsent.current && !sceneRequestInFlight.current) {
      void describeBlockAhead();
    }
    if (!active && !currentSpeech.current && pendingSpeech.current) {
      const next = pendingSpeech.current;
      pendingSpeech.current = null;
      startPrompt(next);
    }
  }

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
    runningRef.current = false;
    socketRef.current?.close();
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
    if (!routeConfirmed.current) return;
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
    if (next.off_route && destination.trim() && !autoRerouteInFlight.current
      && Date.now() - lastAutoRerouteAt.current >= 30_000) {
      autoRerouteInFlight.current = true;
      lastAutoRerouteAt.current = Date.now();
      setRouteStatus('Off route. Recalculating from your current location…');
      void setRoute().finally(() => {
        autoRerouteInFlight.current = false;
      });
    }
    if (guidance && next.event_id !== lastNavigationEvent.current) {
      lastNavigationEvent.current = next.event_id;
      const lowerGuidance = guidance.toLowerCase();
      const priority = lowerGuidance.includes('arrived') ? 4
        : lowerGuidance.includes('face the road') ? 3
          : lowerGuidance.includes('route ready') ? 1 : 2;
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
    let locationTimeout: ReturnType<typeof setTimeout> | undefined;
    try {
      const position = await Promise.race([
        Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High }),
        new Promise<never>((_, reject) => {
          locationTimeout = setTimeout(() => reject(new Error('GPS is unavailable. Move to an open area and try again.')), 15_000);
        }),
      ]);
      await publishLocation(position);
    } finally {
      if (locationTimeout) clearTimeout(locationTimeout);
    }
    startCameraOrientationUpdates();
    if (!headingWatcher.current) {
      headingWatcher.current = await Location.watchHeadingAsync((heading) => {
        // Declination (true minus magnetic north) comes from a geomagnetic model, so it is
        // valid even while the compass itself is still uncalibrated (accuracy 0).
        if (heading.magHeading >= 0 && heading.trueHeading >= 0) {
          declinationRef.current = ((heading.trueHeading - heading.magHeading + 540) % 360) - 180;
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

  async function setRoute(routeDestination = selectedDestination, routeQuery = destination) {
    if (!routeQuery.trim()) return false;
    try {
      // Keep GPS updating after the route exists, even if monitoring was not started yet.
      await startLocationUpdates();
      const response = await fetch(`${backend.replace(/\/$/, '')}/route`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          destination: routeDestination?.display_name ?? routeQuery.trim(),
          map_provider: 'google',
          destination_coordinates: routeDestination
            ? [routeDestination.latitude, routeDestination.longitude]
            : undefined,
        }),
      });
      if (!response.ok) {
        const body = await response.text();
        const detail = body.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
        throw new Error(detail || `Route failed (${response.status})`);
      }
      const result = await response.json();
      routeConfirmed.current = true;
      applyNavigation({ navigation: result.navigation });
      return true;
    } catch (error) {
      setRouteStatus(error instanceof Error ? error.message : 'Route failed');
      return false;
    }
  }

  function cancelAssistantSpeech() {
    if (pendingSpeech.current?.key.startsWith('assistant:')) pendingSpeech.current = null;
    if (currentSpeech.current?.key.startsWith('assistant:')) {
      currentSpeech.current = null;
      speechToken.current += 1;
      void Speech.stop();
    }
  }

  async function authorizeCloudScene() {
    if (cloudSceneConsent.current) return;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(`${backend.replace(/\/$/, '')}/scene/config`, { signal: controller.signal });
      if (!response.ok || !(await response.json()).configured) {
        throw new Error('Cloud scene analysis is not configured. Set the Gemini key on your backend first.');
      }
    } finally {
      clearTimeout(timeout);
    }
    const accepted = await new Promise<boolean>((resolve) => NativeAlert.alert(
      'Cloud surroundings analysis',
      'Camera snapshots will be sent through your backend to Google Gemini. Periodic mode sends snapshots while monitoring is active. API charges and provider data policies may apply. AI can miss or misidentify hazards.',
      [{ text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
        { text: 'Allow', onPress: () => resolve(true) }],
      { cancelable: true, onDismiss: () => resolve(false) },
    ));
    if (!accepted) throw new Error('Cloud scene analysis cancelled.');
    cloudSceneConsent.current = true;
    void AsyncStorage.setItem(CLOUD_CONSENT_KEY, 'granted');
  }

  async function describeBlockAhead() {
    try {
      const result = await analyzeSurroundings(() => safetyActiveRef.current && runningRef.current);
      speakPrompt({
        text: `${result.description} Suggestion: slow down, check the ground with your cane, and step around it if you can.`,
        key: `scene:block:${Date.now()}`,
        priority: 4,
        expiresAt: Date.now() + 8000,
      });
    } catch {
      // The on-device warning has already been spoken; a failed description is silent.
    }
  }

  async function analyzeSurroundings(isCurrent = () => true): Promise<SceneAnalysis> {
    if (sceneRequestInFlight.current) throw new Error('Scene analysis is already running.');
    sceneRequestInFlight.current = true;
    let path: string | undefined;
    const controller = new AbortController();
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      await authorizeCloudScene();
      if (!isCurrent()) throw new Error('Scene analysis cancelled.');
      if (!runningRef.current) throw new Error('Confirm a destination first. Monitoring starts after that.');
      for (let attempt = 0; attempt < 100 && !previewReady.current && runningRef.current; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
      if (!previewReady.current || !camera.current || !runningRef.current || AppState.currentState !== 'active') {
        throw new Error('Camera preview is not ready. Please try Analyze again.');
      }
      const snapshot = await camera.current.takeSnapshot({ quality: 60 });
      const capturedAt = Date.now();
      path = snapshot.path.startsWith('file://') ? snapshot.path : `file://${snapshot.path}`;
      timeout = setTimeout(() => controller.abort(), 15_000);
      const base64 = await FileSystem.readAsStringAsync(path, { encoding: 'base64' });
      const response = await fetch(`${backend.replace(/\/$/, '')}/scene/analyze`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ image: base64, captured_at: capturedAt / 1000 }),
      });
      if (!response.ok) throw new Error(response.status === 429
        ? 'Please wait before analyzing again.' : 'Cloud scene analysis is unavailable. Please try later.');
      const result = await response.json();
      if (!isCurrent() || !runningRef.current || AppState.currentState !== 'active' || Date.now() - capturedAt > 15_000) {
        throw new Error('The scene result is no longer current. Please analyze again.');
      }
      if (typeof result.description !== 'string' || result.description.length > 700 || typeof result.hazard !== 'boolean') {
        throw new Error('Invalid scene description. Please try again.');
      }
      return result as SceneAnalysis;
    } finally {
      sceneRequestInFlight.current = false;
      if (timeout) clearTimeout(timeout);
      if (path) await FileSystem.deleteAsync(path, { idempotent: true }).catch(() => undefined);
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

  const MAX_PENDING_FRAMES = 2;

  function websocketUrl(httpBackend: string): string {
    try {
      const url = new URL(httpBackend);
      const wsProtocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
      const port = url.port ? String(Number(url.port) + 1) : '';
      return `${wsProtocol}//${url.hostname}${port ? `:${port}` : ''}`;
    } catch {
      return httpBackend.replace(/^http/, 'ws');
    }
  }

  function applyFrameResult(result: { image: string; state: any }) {
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
          priority: state.safety_active ? (state.alert_urgent ? 6 : 5) : 2,
        });
      }
    }
    applyNavigation(state);
  }

  function connectSocket(): Promise<WebSocket> {
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(websocketUrl(backend));
      let opened = false;
      socket.onopen = () => {
        opened = true;
        resolve(socket);
      };
      socket.onmessage = (event) => {
        pendingFrames.current = Math.max(0, pendingFrames.current - 1);
        try {
          applyFrameResult(JSON.parse(event.data as string));
        } catch {
          // a malformed reply just means this frame is skipped; the next one still arrives
        }
      };
      socket.onclose = () => {
        socketRef.current = null;
        if (runningRef.current) {
          setStatus('Reconnecting…');
          setTimeout(() => {
            if (runningRef.current) {
              connectSocket().then((next) => { socketRef.current = next; }).catch(() => {});
            }
          }, 1000);
        }
      };
      socket.onerror = () => {
        if (!opened) reject(new Error('Could not connect to the camera stream'));
        else setStatus('Stream connection error');
      };
    });
  }

  async function captureLoop() {
    // Captures and sends continuously: the next frame does not wait for the previous
    // frame's analysis to come back, only for the camera itself and a small send budget.
    while (runningRef.current) {
      const socket = socketRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN
        || pendingFrames.current >= MAX_PENDING_FRAMES || !camera.current) {
        await new Promise((resolve) => setTimeout(resolve, 60));
        continue;
      }
      try {
        // takeSnapshot grabs the current preview buffer (fast) instead of running the full
        // photo pipeline (autofocus/metering) that takePictureAsync does on every call.
        const snapshot = await camera.current.takeSnapshot({ quality: 50 });
        const path = snapshot.path.startsWith('file://') ? snapshot.path : `file://${snapshot.path}`;
        const base64 = await FileSystem.readAsStringAsync(path, { encoding: 'base64' });
        pendingFrames.current += 1;
        socket.send(JSON.stringify({
          image: base64,
          captured_at: Date.now() / 1000,
          session: captureSessionId.current,
        }));
      } catch (error) {
        setStatus(error instanceof Error ? error.message : 'Capture failed');
        await new Promise((resolve) => setTimeout(resolve, 200));
      }
    }
  }

  async function startMonitoring() {
    runningRef.current = true;
    setRunning(true);
    setStatus('Connecting');
    try {
      await startLocationUpdates();
    } catch (error) {
      stopMonitoring();
      setStatus(error instanceof Error ? error.message : 'Location is required to start monitoring');
      return;
    }
    if (!runningRef.current) return;
    speakPrompt({
      text: cloudSceneConsent.current ? 'Cloud descriptions are on.' : 'Cloud descriptions are off.',
      key: 'cloud:status',
      priority: 1,
    });
    captureSessionId.current = `${Date.now()}`;
    pendingFrames.current = 0;
    try {
      socketRef.current = await connectSocket();
    } catch (error) {
      stopMonitoring();
      setStatus(error instanceof Error ? error.message : 'Could not connect to the camera stream');
      return;
    }
    void captureLoop();
  }

  async function routeFromText() {
    const ok = await setRoute();
    if (!ok) return;
    if (!runningRef.current) await startMonitoring();
    setScreen('navigate');
  }

  function changeDestination() {
    routeConfirmed.current = false;
    stopMonitoring();
    setSelectedDestination(null);
    setDestination('');
    setScreen('welcome');
  }

  function stopMonitoring() {
    runningRef.current = false;
    setRunning(false);
    setStatus('Stopped');
    socketRef.current?.close();
    socketRef.current = null;
    pendingFrames.current = 0;
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

  async function startScreenRecording() {
    if (Platform.OS !== 'android') {
      setScreenRecordingStatus('Screen recording is available in the Android build');
      return;
    }
    setScreenRecordingBusy(true);
    setScreenRecordingStatus('Requesting screen recording permission');
    try {
      const microphonePermission = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
        {
          title: 'Microphone access',
          message: 'Allow SafeStride to include microphone audio in screen recordings.',
          buttonPositive: 'Allow',
          buttonNegative: 'Cancel',
        },
      );
      if (microphonePermission !== PermissionsAndroid.RESULTS.GRANTED) {
        throw new Error('Microphone permission is required to record with sound');
      }

      const result = await RecordScreen.startRecording({ mic: true, fps: 30 });
      if (result === RecordingResult.PermissionError) {
        setScreenRecordingStatus('Screen recording permission was denied');
        return;
      }

      screenRecordingActiveRef.current = true;
      setScreenRecordingActive(true);
      setScreenRecordingStatus('Recording the phone screen with microphone audio');
    } catch (error) {
      setScreenRecordingStatus(error instanceof Error ? error.message : 'Could not start recording');
    } finally {
      setScreenRecordingBusy(false);
    }
  }

  async function stopScreenRecording() {
    if (!screenRecordingActiveRef.current) return;
    setScreenRecordingBusy(true);
    setScreenRecordingStatus('Saving recording to Media');
    try {
      const response = await RecordScreen.stopRecording();
      screenRecordingActiveRef.current = false;
      setScreenRecordingActive(false);
      if (response.status !== 'success') {
        throw new Error('The screen recording could not be saved');
      }

      const outputUri = response.result.outputURL.startsWith('file://')
        ? response.result.outputURL
        : `file://${response.result.outputURL}`;
      setScreenRecordingStatus('Uploading recording to laptop');
      const name = `safestride-${Date.now()}.mp4`;
      const upload = await FileSystem.uploadAsync(
        `${backend.replace(/\/$/, '')}/recordings/upload?name=${encodeURIComponent(name)}`,
        outputUri,
        {
          httpMethod: 'POST',
          uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
          headers: { 'Content-Type': 'video/mp4' },
        },
      );
      if (upload.status !== 200) {
        throw new Error(`Upload failed (${upload.status}). The recording is kept on the phone.`);
      }
      await FileSystem.deleteAsync(outputUri, { idempotent: true }).catch(() => undefined);
      await RecordScreen.clean().catch(() => undefined);
      setScreenRecordingStatus('Saved to laptop: F:\\Mobile\\SafeStride-Recordings');
    } catch (error) {
      setScreenRecordingStatus(error instanceof Error ? error.message : 'Could not save recording');
    } finally {
      setScreenRecordingBusy(false);
    }
  }

  if (!hasPermission) {
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
  if (!device) return <View style={styles.center}><ActivityIndicator color="#8ce3c3" /></View>;

  if (screen === 'loading') {
    const failed = setup.location === 'fail' || setup.backend === 'fail';
    return (
      <SafeAreaView style={styles.center}>
        <Text style={styles.eyebrow}>SAFESTRIDE</Text>
        <Text style={styles.welcomeTitle}>Getting things ready</Text>
        <View style={styles.stats}>
          <SetupRow label="LOCATION" state={setup.location} />
          <SetupRow label="BACKEND" state={setup.backend} />
        </View>
        {!failed && <ActivityIndicator color="#8ce3c3" style={{ marginTop: 16 }} />}
        {failed && (
          <View style={styles.setupActions}>
            <Pressable style={styles.primaryButton} onPress={() => { void runSetup(); }}>
              <Text style={styles.primaryText}>Retry</Text>
            </Pressable>
            <Pressable style={styles.changeButton} onPress={() => setScreen('welcome')}>
              <Text style={styles.changeText}>Continue anyway</Text>
            </Pressable>
          </View>
        )}
      </SafeAreaView>
    );
  }

  return (
    <ViewShot ref={screenCaptureRoot} style={styles.container}>
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
      <Animated.View style={{ opacity: screenFade }}>
      <StatusBar style="light" />
      <View style={styles.header}>
        <View style={styles.headerTitle}>
          <Text style={styles.eyebrow}>SAFESTRIDE MOBILE</Text>
          <Text style={styles.title}>Path awareness</Text>
        </View>
        <View style={[styles.livePill, running && styles.livePillActive]}>
          <Text style={styles.liveText}>{running ? 'LIVE' : 'STANDBY'}</Text>
        </View>
      </View>
      <FadeInView style={[styles.alertBox, styles.alertTop, safetyActive && (safetyUrgent ? styles.alertUrgent : styles.alertCaution)]}>
        <Text style={styles.eyebrow}>{safetyActive ? (safetyUrgent ? 'STOP / URGENT' : 'SAFETY CAUTION') : 'SAFETY CLEAR'}</Text>
        <Text style={styles.alert}>{alert}</Text>
      </FadeInView>
      <VoiceAssistant
        autoGreet={screen === 'welcome'}
        compact={screen === 'navigate'}
        describeStatus={() => `${routeStatus}${navigation.distance_remaining !== null && navigation.distance_remaining !== undefined ? `. ${Math.round(navigation.distance_remaining)} meters remaining` : ''}`}
        changeDestination={changeDestination}
        safetyActive={safetyActive}
        monitoring={running}
        authorizeCloud={authorizeCloudScene}
        canAnalyze={() => AppState.currentState === 'active' && runningRef.current && !voiceListening.current
          && !safetyActiveRef.current && !currentSpeech.current && !pendingSpeech.current && !sceneRequestInFlight.current}
        microphoneBusy={screenRecordingActive || screenRecordingBusy}
        speak={(text, onDone, scene) => speakPrompt({ text, key: `assistant:${Date.now()}`,
          priority: scene?.hazard ? 4 : 1, onDone, expiresAt: scene ? Date.now() + 5000 : undefined })}
        cancelSpeech={cancelAssistantSpeech}
        onListeningChange={(value) => {
          voiceListening.current = value;
          if (value && currentSpeech.current && currentSpeech.current.priority < 5) {
            rememberPrompt(currentSpeech.current);
            currentSpeech.current = null;
            void Speech.stop();
          }
          if (!value && !currentSpeech.current && !safetyActiveRef.current && pendingSpeech.current) {
            const next = pendingSpeech.current;
            pendingSpeech.current = null;
            startPrompt(next);
          }
        }}
        search={async (query) => {
          await startLocationUpdates();
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 15_000);
          try {
            const response = await fetch(`${backend.replace(/\/$/, '')}/places?q=${encodeURIComponent(query)}&map_provider=google`, { signal: controller.signal });
            if (!response.ok) throw new Error('Place search is unavailable. Check your backend connection.');
            const result = await response.json();
            return result.suggestions ?? [];
          } finally {
            clearTimeout(timeout);
          }
        }}
        navigate={async (place, isCurrent) => {
          if (!isCurrent()) return;
          setDestination(place.display_name);
          setSelectedDestination(place);
          const ready = await setRoute(place, place.display_name);
          if (!isCurrent()) return;
          if (!ready) throw new Error('Could not create that route. Please try another destination.');
          if (!runningRef.current) await startMonitoring();
          if (!isCurrent()) { stopMonitoring(); return; }
          if (!runningRef.current) throw new Error('Route created, but monitoring could not connect to the backend.');
          setScreen('navigate');
        }}
        analyze={analyzeSurroundings}
        stop={stopMonitoring}
        repeat={() => speakPrompt({ text: navigation.message ?? navigation.guidance ?? routeStatus, key: `navigation:repeat:${Date.now()}`, priority: 2 })}
      />
      {screen === 'welcome' && (
        <View style={styles.welcomeHero}>
          <Text style={styles.welcomeTitle}>Where would you like to go?</Text>
          <Text style={styles.welcomeSub}>Tap Talk and say the place, or type it below.</Text>
        </View>
      )}
      <View style={screen === 'welcome' ? styles.previewHidden : styles.preview}>
        <Camera
          ref={camera}
          style={StyleSheet.absoluteFill}
          device={device}
          isActive={running}
          photo={true}
          onPreviewStarted={() => { previewReady.current = true; }}
          onPreviewStopped={() => { previewReady.current = false; }}
        />
        {image && <Image source={{ uri: image }} style={styles.annotated} resizeMode="cover" />}
        {!image && <Text style={styles.previewHint}>Annotated feed appears here</Text>}
      </View>
      {screen === 'navigate' && <LiveMapInset position={mapPosition} route={navigation.route_geometry ?? []} />}
      {screen === 'navigate' && (<>
      <FadeInView style={styles.stats}>
        <Stat label="STATUS" value={status} />
        <Stat label="DEPTH" value={depth ? 'ACTIVE' : 'OFF'} />
        <Stat label="FPS" value={fps ? `${fps.toFixed(1)}` : '--'} />
      </FadeInView>
      <Pressable style={[styles.primaryButton, styles.primaryTop, running && styles.stopButton]} onPress={running ? stopMonitoring : startMonitoring}>
        <Text style={styles.primaryText}>{running ? 'Stop monitoring' : 'Start monitoring'}</Text>
      </Pressable>
      <View style={styles.screenRecordingBox}>
        <Text style={styles.screenRecordingStatus}>{screenRecordingStatus}</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={screenRecordingActive ? 'Stop screen recording and save video' : 'Start screen recording'}
          style={[styles.screenRecordingButton, screenRecordingActive && styles.screenShareStop]}
          onPress={screenRecordingActive ? stopScreenRecording : startScreenRecording}
          disabled={screenRecordingBusy}
        >
          <Text style={styles.screenShareButtonText}>
            {screenRecordingBusy ? 'Please wait…' : screenRecordingActive ? 'Stop & save recording' : 'Record screen'}
          </Text>
        </Pressable>
      </View>
      </>)}
      {screen === 'welcome' && (<>
      <Text style={styles.sectionTitle}>WALKING ROUTE</Text>
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
        <Pressable style={styles.routeButton} onPress={() => { void routeFromText(); }}>
          <Text style={styles.routeText}>Route</Text>
        </Pressable>
      </View>
      <Pressable style={styles.googleMapsButton} onPress={openInGoogleMaps}>
        <Text style={styles.googleMapsText}>Open in Google Maps</Text>
      </Pressable>
      {destinationSearching && <Text style={styles.searchStatus}>Searching nearby places…</Text>}
      {destinationSearchProvider && (
        <Text style={styles.searchStatus}>{destinationSearchProvider} results</Text>
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
      </>)}
      {screen === 'navigate' && (
        <Pressable style={styles.changeButton} onPress={changeDestination} accessibilityRole="button" accessibilityLabel="Change destination">
          <Text style={styles.changeText}>Change destination</Text>
        </Pressable>
      )}
      {screen === 'navigate' && (<>
      <FadeInView style={styles.navigationBox}>
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
      </FadeInView>
      </>)}
      {screen === 'navigate' && (<>
      <Text style={styles.sectionTitle}>SETTINGS</Text>
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
      </>)}
      <StatusBar style="auto" />
      </Animated.View>
      </ScrollView>
    </SafeAreaView>
    </ViewShot>
  );
}

function FadeInView({ style, children }: { style?: StyleProp<ViewStyle>; children: ReactNode }) {
  const progress = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(progress, { toValue: 1, duration: 450, useNativeDriver: true }).start();
  }, [progress]);
  return (
    <Animated.View style={[style, {
      opacity: progress,
      transform: [{ translateY: progress.interpolate({ inputRange: [0, 1], outputRange: [14, 0] }) }],
    }]}>
      {children}
    </Animated.View>
  );
}

function SetupRow({ label, state }: { label: string; state: SetupState }) {
  const text = state === 'ok' ? 'Ready' : state === 'fail' ? 'Failed' : 'Checking…';
  return <View style={styles.stat}><Text style={styles.statLabel}>{label}</Text><Text style={styles.statValue}>{text}</Text></View>;
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
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18, gap: 12 },
  headerTitle: { flex: 1, minWidth: 0 },
  eyebrow: { color: '#8ce3c3', fontSize: 11, fontWeight: '700', letterSpacing: 1.5 },
  title: { color: '#f1f7f4', fontSize: 26, fontWeight: '700', marginTop: 5 },
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
  screenRecordingBox: { backgroundColor: '#142127', borderLeftColor: '#e5b35d', borderLeftWidth: 3, padding: 12, marginTop: 10, borderRadius: 4, gap: 9 },
  screenRecordingStatus: { color: '#bac8cc', fontSize: 12 },
  screenRecordingButton: { alignItems: 'center', backgroundColor: '#e5b35d', paddingVertical: 11, borderRadius: 5 },
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
  alertTop: { marginTop: 0, marginBottom: 12 },
  primaryTop: { marginTop: 12 },
  sectionTitle: { color: '#8a9aa1', fontSize: 11, fontWeight: '700', letterSpacing: 1.5, marginTop: 22 },
  welcomeHero: { paddingVertical: 8, gap: 6 },
  welcomeTitle: { color: '#f1f7f4', fontSize: 28, fontWeight: '800' },
  welcomeSub: { color: '#9aabb2', fontSize: 14, lineHeight: 20 },
  previewHidden: { height: 2, opacity: 0.01, overflow: 'hidden' },
  changeButton: { alignItems: 'center', backgroundColor: '#294b4b', borderRadius: 6, paddingVertical: 13, marginTop: 14 },
  changeText: { color: '#8ce3c3', fontWeight: '800', fontSize: 15 },
  setupActions: { alignSelf: 'stretch', gap: 10, marginTop: 14 },
});
