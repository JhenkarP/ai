export type ScreenShareHandle = { stop: () => Promise<void> };

type ScreenShareCallbacks = {
  onStatus: (status: string) => void;
  onViewerUrl: (url: string) => void;
  onStopped: () => void;
  captureFrame: () => Promise<string>;
};

const delay = (milliseconds: number) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function postJson(url: string, body: unknown) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`Screen-share request failed (${response.status})`);
  return response.json();
}

export async function startScreenShare(
  backend: string,
  callbacks: ScreenShareCallbacks,
): Promise<ScreenShareHandle> {
  const base = backend.replace(/\/$/, '');
  const session = await postJson(`${base}/screen/session`, {});
  const token = String(session.token ?? '');
  if (!token) throw new Error('Backend did not create a screen-share session');

  const backendUrl = new URL(base);
  const viewerBase = `${backendUrl.protocol}//localhost${backendUrl.port ? `:${backendUrl.port}` : ''}`;
  callbacks.onViewerUrl(`${viewerBase}/screen?token=${encodeURIComponent(token)}`);
  callbacks.onStatus('Starting live app preview');

  let stopped = false;

  const stop = async () => {
    if (stopped) return;
    stopped = true;
    callbacks.onStopped();
    try {
      await postJson(`${base}/screen/stop`, { token });
    } catch {}
  };

  void (async () => {
    while (!stopped) {
      try {
        const image = await callbacks.captureFrame();
        await postJson(`${base}/screen/frame`, { token, image });
        callbacks.onStatus('Live app preview');
      } catch (error) {
        if (!stopped) callbacks.onStatus(error instanceof Error ? error.message : 'App preview failed');
      }
      await delay(700);
    }
  })();

  return { stop };
}