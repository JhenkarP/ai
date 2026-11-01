const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

const compiled = ts.transpileModule(
  fs.readFileSync(path.join(__dirname, 'VoiceAssistant.tsx'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } },
).outputText;
const place = { name: 'Pharmacy', display_name: 'Pharmacy, Main Road', latitude: 12, longitude: 77 };
const settle = () => new Promise((resolve) => setImmediate(resolve));

function fixture(overrides = {}, granted = true) {
  const slots = [];
  const effects = [];
  const listeners = {};
  const spoken = [];
  let cursor = 0;
  let starts = 0;
  let aborts = 0;
  const props = {
    safetyActive: false, microphoneBusy: false,
    monitoring: false, authorizeCloud: async () => {}, canAnalyze: () => true,
    speak: (text, done) => { spoken.push(text); done?.(); },
    cancelSpeech: () => {}, onListeningChange: () => {},
    search: async () => [place], navigate: async () => {},
    analyze: async () => ({ description: 'Person on the left.', hazard: false }), stop: () => {}, repeat: () => {},
    ...overrides,
  };
  const recognition = {
    abort: () => { aborts += 1; },
    start: () => { starts += 1; listeners.start?.(); },
    isRecognitionAvailable: () => true,
    requestPermissionsAsync: async () => ({ granted }),
  };
  const jsx = (type, props) => ({ type, props });
  const mocks = {
    'react/jsx-runtime': { jsx, jsxs: jsx },
    '@expo/vector-icons/Ionicons': { default: 'Icon' },
    './SceneScheduler': { SceneScheduler: class { start() {} stop() {} } },
    'expo-speech-recognition': {
      ExpoSpeechRecognitionModule: recognition,
      useSpeechRecognitionEvent: (name, callback) => { listeners[name] = callback; },
    },
    react: {
      useRef: (initial) => {
        const index = cursor++;
        return slots[index] ??= { current: initial };
      },
      useState: (initial) => {
        const index = cursor++;
        if (!(index in slots)) slots[index] = initial;
        return [slots[index], (value) => { slots[index] = value; }];
      },
      useEffect: (callback, dependencies) => {
        const index = cursor++;
        if (!slots[index] || dependencies.some((value, position) => value !== slots[index][position])) {
          slots[index] = dependencies;
          effects.push(callback);
        }
      },
    },
    'react-native': { Pressable: 'Pressable', View: 'View', Text: 'Text', Switch: 'Switch',
      AppState: { currentState: 'active', addEventListener: () => ({ remove: () => {} }) },
      StyleSheet: { create: (value) => value } },
  };
  const context = { exports: {}, require: (name) => {
    assert.ok(name in mocks, `Unexpected import: ${name}`);
    return mocks[name];
  } };
  vm.runInNewContext(compiled, context);
  function render() {
    cursor = 0;
    const tree = context.exports.default(props);
    effects.splice(0).forEach((effect) => effect());
    return tree;
  }
  function press(label) {
    const visit = (node) => {
      if (!node || typeof node !== 'object') return undefined;
      if (node.props?.accessibilityLabel === label) return node;
      const children = node.props?.children;
      return (Array.isArray(children) ? children : [children]).map(visit).find(Boolean);
    };
    const button = visit(render());
    assert.ok(button, `Button missing: ${label}`);
    button.props.onPress();
  }
  return {
    props, spoken, render, press, starts: () => starts, aborts: () => aborts,
    result: (text) => listeners.result({ isFinal: true, results: [{ transcript: text }] }),
  };
}

test('greets, searches a spoken destination, and navigates only after yes', async () => {
  const searches = [];
  const routes = [];
  const app = fixture({
    search: async (query) => { searches.push(query); return [place]; },
    navigate: async (selected, isCurrent) => { if (isCurrent()) routes.push(selected); },
  });
  app.press('Talk to SafeStride');
  await settle();
  assert.equal(app.starts(), 1);
  app.result('Take me to the pharmacy');
  await settle();
  assert.deepEqual(searches, ['the pharmacy']);
  assert.equal(routes.length, 0);
  assert.ok(app.spoken.some((text) => text.includes(place.display_name)));
  app.result('yes');
  await settle();
  assert.deepEqual(routes, [place]);
});

test('microphone denial does not start recognition', async () => {
  const app = fixture({}, false);
  app.press('Talk to SafeStride');
  await settle();
  assert.equal(app.starts(), 0);
  assert.ok(app.spoken.some((text) => text.includes('microphone access')));
});

test('hazard interruption discards an outstanding place search', async () => {
  let resolveSearch;
  const app = fixture({ search: () => new Promise((resolve) => { resolveSearch = resolve; }) });
  app.press('Talk to SafeStride');
  await settle();
  app.result('pharmacy');
  app.props.safetyActive = true;
  app.render();
  resolveSearch([place]);
  await settle();
  assert.ok(app.aborts() > 0);
  assert.ok(!app.spoken.some((text) => text.includes('Did you mean')));
});

test('Stop cancels pending confirmation and stops monitoring', async () => {
  let stopped = false;
  let navigated = false;
  const app = fixture({ stop: () => { stopped = true; }, navigate: async () => { navigated = true; } });
  app.press('Talk to SafeStride');
  await settle();
  app.result('pharmacy');
  await settle();
  app.press('Stop assistant and monitoring');
  app.result('yes');
  await settle();
  assert.equal(stopped, true);
  assert.equal(navigated, false);
});

const schedulerCode = ts.transpileModule(
  fs.readFileSync(path.join(__dirname, 'SceneScheduler.ts'), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.CommonJS } },
).outputText;

function scheduledFixture(overrides = {}) {
  const tasks = new Map();
  let now = 0;
  let nextId = 0;
  let calls = 0;
  const spoken = [];
  const errors = [];
  const context = {
    exports: {}, Date: { now: () => now },
    setTimeout: (callback, delay) => {
      const id = ++nextId;
      tasks.set(id, { callback, at: now + delay });
      return id;
    },
    clearTimeout: (id) => tasks.delete(id),
  };
  vm.runInNewContext(schedulerCode, context);
  const options = {
    intervalMs: 15_000, canRun: () => true,
    analyze: async () => { calls += 1; return { description: 'Possible stairs ahead.', hazard: true }; },
    onResult: (result) => spoken.push(result.description), onError: (error) => errors.push(error),
    ...overrides,
  };
  const scheduler = new context.exports.SceneScheduler(options);
  scheduler.start();
  return {
    scheduler, options, spoken, errors, calls: () => calls, tasks,
    advance: async (milliseconds) => {
      now += milliseconds;
      for (const [id, task] of [...tasks]) {
        if (task.at <= now) { tasks.delete(id); task.callback(); }
      }
      await settle();
    },
  };
}

test('periodic analysis skips unsafe/busy conditions and suppresses unchanged speech', async () => {
  let ready = false;
  const app = scheduledFixture({ canRun: () => ready });
  await app.advance(15_000);
  assert.equal(app.calls(), 0);
  ready = true;
  await app.advance(15_000);
  await app.advance(15_000);
  assert.equal(app.calls(), 2);
  assert.equal(app.spoken.length, 1);
  await app.advance(60_000);
  assert.equal(app.spoken.length, 2);
  app.scheduler.stop();
});

test('stopping periodic analysis discards an in-flight result without scheduling another call', async () => {
  let resolve;
  let calls = 0;
  const app = scheduledFixture({ analyze: () => { calls += 1; return new Promise((done) => { resolve = done; }); } });
  await app.advance(15_000);
  await app.advance(90_000);
  assert.equal(calls, 1);
  app.scheduler.stop();
  resolve({ description: 'Old scene', hazard: true });
  await settle();
  assert.equal(app.spoken.length, 0);
  assert.equal(app.tasks.size, 0);
});

test('provider failures back off for a minute and announce unavailability once', async () => {
  let calls = 0;
  const app = scheduledFixture({ analyze: async () => { calls += 1; throw new Error('Unavailable'); } });
  await app.advance(15_000);
  await app.advance(15_000);
  assert.equal(calls, 1);
  await app.advance(45_000);
  assert.equal(calls, 2);
  assert.equal(app.errors.length, 1);
  app.scheduler.stop();
});