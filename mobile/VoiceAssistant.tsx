import Ionicons from '@expo/vector-icons/Ionicons';
import { ExpoSpeechRecognitionModule, useSpeechRecognitionEvent } from 'expo-speech-recognition';
import { useEffect, useRef, useState } from 'react';
import { AppState, Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import { SceneScheduler, type SceneAnalysis } from './SceneScheduler';

export type VoicePlace = {
  name: string;
  display_name: string;
  latitude: number;
  longitude: number;
};

type Props = {
  autoGreet?: boolean;
  compact?: boolean;
  describeStatus: () => string;
  changeDestination: () => void;
  safetyActive: boolean;
  monitoring: boolean;
  authorizeCloud: () => Promise<void>;
  canAnalyze: () => boolean;
  microphoneBusy: boolean;
  speak: (text: string, onDone?: () => void, scene?: SceneAnalysis) => void;
  cancelSpeech: () => void;
  search: (query: string) => Promise<VoicePlace[]>;
  navigate: (place: VoicePlace, isCurrent: () => boolean) => Promise<void>;
  onListeningChange: (listening: boolean) => void;
  analyze: (isCurrent?: () => boolean) => Promise<SceneAnalysis>;
  stop: () => void;
  repeat: () => void;
};

export default function VoiceAssistant(props: Props) {
  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('Hello. Where would you like to go?');
  const [transcript, setTranscript] = useState('');
  const [periodic, setPeriodic] = useState(false);
  const [intervalSeconds, setIntervalSeconds] = useState(15);
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  const candidates = useRef<VoicePlace[]>([]);
  const candidateIndex = useRef(0);
  const confirmation = useRef(false);
  const generation = useRef(0);
  const periodicRequest = useRef(0);
  const active = useRef(false);
  const processing = useRef(false);
  const greeted = useRef(false);
  const callbacks = useRef(props);
  callbacks.current = props;

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) => setForeground(state === 'active'));
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    if (!periodic || !props.monitoring || !foreground || props.safetyActive) return;
    const scheduler = new SceneScheduler({
      intervalMs: intervalSeconds * 1000,
      canRun: () => !active.current && !processing.current && callbacks.current.canAnalyze(),
      analyze: () => callbacks.current.analyze(),
      onResult: (result) => say(result.description, undefined, result),
      onError: (error) => say(error instanceof Error ? error.message : 'Periodic analysis is unavailable. Retrying later.'),
    });
    scheduler.start();
    return () => scheduler.stop();
  }, [periodic, props.monitoring, foreground, props.safetyActive, intervalSeconds]);

  useEffect(() => {
    callbacks.current.onListeningChange(listening);
  }, [listening]);

  useEffect(() => {
    if (!props.autoGreet || greeted.current) return;
    greeted.current = true;
    say('Hello. I am SafeStride. Where would you like to go?', () => { void listen(); });
    // Greet once when the app opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => {
    generation.current += 1;
    active.current = false;
    ExpoSpeechRecognitionModule.abort();
  }, []);

  useEffect(() => {
    if (!props.safetyActive) return;
    const token = ++generation.current;
    active.current = false;
    processing.current = false;
    ExpoSpeechRecognitionModule.abort();
    callbacks.current.cancelSpeech();
    void Promise.resolve().then(() => {
      if (token !== generation.current) return;
      setListening(false);
      setBusy(false);
      setMessage('Safety warning. Voice assistant paused.');
    });
  }, [props.safetyActive]);

  useSpeechRecognitionEvent('start', () => setListening(true));
  useSpeechRecognitionEvent('end', () => {
    setListening(false);
    callbacks.current.onListeningChange(false);
    if (active.current && !processing.current) {
      active.current = false;
      setMessage('I did not hear a destination. Please try again.');
    }
  });
  useSpeechRecognitionEvent('error', (event) => {
    if (event.error === 'aborted' || !active.current) return;
    active.current = false;
    setListening(false);
    callbacks.current.onListeningChange(false);
    say(event.error === 'not-allowed'
      ? 'Microphone permission is needed for voice input.'
      : 'I could not hear you. Please try again.');
  });
  useSpeechRecognitionEvent('result', (event) => {
    if (!active.current || processing.current) return;
    const text = event.results[0]?.transcript?.trim();
    if (!text) return;
    setTranscript(text);
    if (event.isFinal) {
      active.current = false;
      processing.current = true;
      setListening(false);
      callbacks.current.onListeningChange(false);
      void handleText(text);
    }
  });

  function say(text: string, after?: () => void, scene?: SceneAnalysis) {
    const token = generation.current;
    setMessage(text);
    callbacks.current.speak(text, after ? () => {
      if (token === generation.current && !callbacks.current.safetyActive) after();
    } : undefined, scene);
  }

  async function listen() {
    const token = generation.current;
    try {
      if (callbacks.current.safetyActive) throw new Error('Wait until the safety warning clears.');
      if (callbacks.current.microphoneBusy) throw new Error('Stop screen recording before using the microphone.');
      if (!ExpoSpeechRecognitionModule.isRecognitionAvailable()) {
        throw new Error('Enable Google speech recognition in your phone settings.');
      }
      const permission = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
      if (!permission.granted) throw new Error('Allow microphone access in Settings to use voice input.');
      if (token !== generation.current || callbacks.current.safetyActive) return;
      processing.current = false;
      active.current = true;
      callbacks.current.onListeningChange(true);
      setTranscript('');
      setMessage(confirmation.current ? 'Listening for confirmation' : 'Listening for your destination');
      ExpoSpeechRecognitionModule.start({
        lang: 'en-IN', interimResults: true, continuous: false, maxAlternatives: 1,
        androidIntentOptions: { EXTRA_LANGUAGE_MODEL: 'web_search' },
      });
    } catch (error) {
      active.current = false;
      callbacks.current.onListeningChange(false);
      say(error instanceof Error ? error.message : 'Voice input is unavailable.');
    }
  }

  function talk() {
    if (listening || busy) {
      cancel();
      return;
    }
    generation.current += 1;
    callbacks.current.cancelSpeech();
    if (!greeted.current) {
      greeted.current = true;
      say('Hello. I am SafeStride. Where would you like to go?', () => { void listen(); });
    } else {
      void listen();
    }
  }

  function cancel() {
    generation.current += 1;
    periodicRequest.current += 1;
    active.current = false;
    processing.current = false;
    confirmation.current = false;
    candidates.current = [];
    ExpoSpeechRecognitionModule.abort();
    callbacks.current.cancelSpeech();
    setListening(false);
    callbacks.current.onListeningChange(false);
    setBusy(false);
    setPeriodic(false);
    setMessage('Voice assistant stopped.');
  }

  function askConfirmation() {
    const place = candidates.current[candidateIndex.current];
    if (!place) return;
    confirmation.current = true;
    say(`Did you mean ${place.display_name}? Say yes, next, or no.`, () => { void listen(); });
  }

  async function analyze() {
    const token = ++generation.current;
    active.current = false;
    processing.current = true;
    ExpoSpeechRecognitionModule.abort();
    callbacks.current.cancelSpeech();
    setListening(false);
    setBusy(true);
    setMessage('Analyzing surroundings');
    try {
      if (callbacks.current.safetyActive) throw new Error('Wait until the safety warning clears.');
      const result = await callbacks.current.analyze(() => token === generation.current);
      if (token === generation.current) say(result.description, undefined, result);
    } catch (error) {
      if (token === generation.current) say(error instanceof Error ? error.message : 'Analysis unavailable.');
    } finally {
      if (token === generation.current) {
        processing.current = false;
        setBusy(false);
      }
    }
  }

  async function togglePeriodic(enabled: boolean) {
    const request = ++periodicRequest.current;
    if (!enabled) {
      setPeriodic(false);
      say('Periodic surroundings analysis is off.');
      return;
    }
    const token = generation.current;
    try {
      await callbacks.current.authorizeCloud();
      if (token !== generation.current || request !== periodicRequest.current) return;
      setPeriodic(true);
      say(callbacks.current.monitoring
        ? 'Periodic surroundings analysis is on.'
        : 'Periodic analysis is enabled. It will run when monitoring starts.');
    } catch (error) {
      if (token === generation.current) say(error instanceof Error ? error.message : 'Cloud analysis is unavailable.');
    }
  }

  async function handleText(text: string) {
    const token = generation.current;
    const command = text.toLowerCase().replace(/[.!?]/g, '').trim();
    if (/^(start|enable|turn on) (periodic|automatic) (analysis|analy[sz]e)$/.test(command)) {
      processing.current = false;
      await togglePeriodic(true);
      return;
    }
    if (/^(stop|disable|turn off) (periodic|automatic) (analysis|analy[sz]e)$/.test(command)) {
      processing.current = false;
      await togglePeriodic(false);
      return;
    }
    if (/^(stop|cancel|stop navigation|stop monitoring)$/.test(command)) {
      cancel();
      callbacks.current.stop();
      say('Monitoring stopped.');
      return;
    }
    if (/^(analy[sz]e|describe surroundings|describe my surroundings|what is ahead|what do you see)$/.test(command)) {
      await analyze();
      return;
    }
    if (/^(where am i|how far|status|where are we|how much further)$/.test(command)) {
      processing.current = false;
      say(callbacks.current.describeStatus());
      return;
    }
    if (/^(change|new|different) destination$/.test(command)) {
      processing.current = false;
      cancel();
      callbacks.current.changeDestination();
      say('Where would you like to go?', () => { void listen(); });
      return;
    }
    if (/^(repeat|repeat direction|repeat directions)$/.test(command)) {
      processing.current = false;
      callbacks.current.repeat();
      return;
    }
    setBusy(true);
    try {
      if (confirmation.current) {
        if (/^(yes|yeah|correct|confirm|yes please|go ahead)$/.test(command)) {
          const place = candidates.current[candidateIndex.current];
          if (!place) throw new Error('Please say your destination again.');
          confirmation.current = false;
          setMessage(`Starting your route to ${place.name}`);
          await callbacks.current.navigate(place, () => token === generation.current);
          if (token === generation.current) say(`Route ready to ${place.name}. Monitoring is active.`);
          return;
        }
        if (/^(next|next one|another|another one)$/.test(command)) {
          if (candidateIndex.current + 1 < candidates.current.length) {
            candidateIndex.current += 1;
            askConfirmation();
          } else {
            confirmation.current = false;
            say('No more matches. Where would you like to go?', () => { void listen(); });
          }
          return;
        }
        if (/^(no|nope|wrong|different destination)$/.test(command)) {
          confirmation.current = false;
          say('Where would you like to go?', () => { void listen(); });
          return;
        }
        say('Please say yes to confirm, next for another match, or no.', () => { void listen(); });
        return;
      }
      const query = text.replace(/^(?:please\s+)?(?:take me to|navigate to|go to|directions to)\s+/i, '').trim();
      setMessage(`Finding ${query}`);
      const places = await callbacks.current.search(query);
      if (token !== generation.current) return;
      if (!places.length) throw new Error('I could not find that place. Please say the name and area again.');
      candidates.current = places;
      candidateIndex.current = 0;
      askConfirmation();
    } catch (error) {
      if (token === generation.current) say(error instanceof Error ? error.message : 'Please try again.');
    } finally {
      if (token === generation.current) {
        processing.current = false;
        setBusy(false);
      }
    }
  }

  return (
    <View style={styles.section}>
      {!props.compact && <Text style={styles.heading}>Your walking assistant</Text>}
      <Text style={styles.message} accessibilityLiveRegion="polite">{message}</Text>
      {transcript !== '' && <Text style={styles.transcript}>{transcript}</Text>}
      <View style={styles.controls}>
        <Pressable accessibilityRole="button" accessibilityLabel={listening || busy ? 'Cancel voice input' : 'Talk to SafeStride'}
          accessibilityState={{ disabled: props.safetyActive }} disabled={props.safetyActive}
          onPress={talk} style={[styles.control, styles.talk, listening && styles.listening, props.safetyActive && styles.disabled]}>
          <Ionicons name={listening ? 'mic' : busy ? 'close' : 'mic-outline'} size={30} color="#081b14" />
          <Text style={styles.darkLabel}>{listening ? 'Listening' : busy ? 'Cancel' : 'Talk'}</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Analyze surroundings"
          accessibilityState={{ disabled: busy || props.safetyActive }} disabled={busy || props.safetyActive}
          onPress={() => { void analyze(); }} style={[styles.control, (busy || props.safetyActive) && styles.disabled]}>
          <Ionicons name="scan-outline" size={30} color="#f3faf7" /><Text style={styles.label}>Analyze</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel="Stop assistant and monitoring"
          onPress={() => { cancel(); callbacks.current.stop(); }} style={[styles.control, styles.stop]}>
          <Ionicons name="stop" size={30} color="#fff" /><Text style={styles.label}>Stop</Text>
        </Pressable>
      </View>
      <View style={styles.periodicRow}>
        <Text style={styles.label}>Periodic surroundings</Text>
        <Switch value={periodic} onValueChange={(enabled) => { void togglePeriodic(enabled); }}
          accessibilityLabel="Periodic cloud surroundings analysis" trackColor={{ true: '#8ce3c3', false: '#53636b' }} />
      </View>
      {periodic && <>
        <View style={styles.controls} accessibilityRole="radiogroup" accessibilityLabel="Scene analysis interval">
          {[15, 30, 60].map((seconds) => <Pressable key={seconds} accessibilityRole="radio"
            accessibilityLabel={`Analyze every ${seconds} seconds`} accessibilityState={{ checked: intervalSeconds === seconds }}
            onPress={() => setIntervalSeconds(seconds)} style={[styles.interval, intervalSeconds === seconds && styles.selectedInterval]}>
            <Text style={intervalSeconds === seconds ? styles.darkLabel : styles.label}>{seconds}s</Text>
          </Pressable>)}
        </View>
        <Text style={styles.transcript} accessibilityLiveRegion="polite">
          {!props.monitoring ? 'Waiting for monitoring' : !foreground ? 'Paused in background'
            : props.safetyActive ? 'Paused for safety warning' : 'Periodic analysis on'}
        </Text>
      </>}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { paddingVertical: 18, borderBottomWidth: 1, borderBottomColor: '#30463f', gap: 12 },
  heading: { color: '#f3faf7', fontSize: 22, fontWeight: '700' },
  message: { color: '#e1eee8', fontSize: 18, lineHeight: 26 },
  transcript: { color: '#a5bdb1', fontSize: 16 },
  controls: { flexDirection: 'row', gap: 10 },
  control: { flex: 1, minHeight: 92, borderRadius: 8, backgroundColor: '#25473a', alignItems: 'center', justifyContent: 'center', gap: 8, padding: 8 },
  talk: { backgroundColor: '#8ce3c3' },
  listening: { backgroundColor: '#f1ce68' },
  stop: { backgroundColor: '#a52f38' },
  disabled: { opacity: 0.45 },
  label: { color: '#fff', fontSize: 17, fontWeight: '700' },
  darkLabel: { color: '#081b14', fontSize: 17, fontWeight: '700' },
  periodicRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  interval: { flex: 1, minHeight: 48, borderRadius: 6, backgroundColor: '#25473a', alignItems: 'center', justifyContent: 'center' },
  selectedInterval: { backgroundColor: '#8ce3c3' },
});