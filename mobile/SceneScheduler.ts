export type SceneAnalysis = {
  description: string;
  hazard: boolean;
  provider: string;
  analyzed_at: number;
};

type Options = {
  intervalMs: number;
  canRun: () => boolean;
  analyze: () => Promise<SceneAnalysis>;
  onResult: (result: SceneAnalysis) => void;
  onError: (error: unknown) => void;
};

export class SceneScheduler {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = true;
  private lastDescription = '';
  private lastSpokenAt = -Infinity;
  private failed = false;

  constructor(private options: Options) {}

  start() {
    this.stopped = false;
    this.schedule(this.options.intervalMs);
  }

  stop() {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  private schedule(delay: number) {
    if (!this.stopped) this.timer = setTimeout(() => { void this.tick(); }, delay);
  }

  private async tick() {
    if (this.stopped) return;
    if (!this.options.canRun()) {
      this.schedule(this.options.intervalMs);
      return;
    }
    let delay = this.options.intervalMs;
    try {
      const result = await this.options.analyze();
      if (this.stopped || !this.options.canRun()) return;
      this.failed = false;
      if (result.description !== this.lastDescription || Date.now() - this.lastSpokenAt >= 60_000) {
        this.lastDescription = result.description;
        this.lastSpokenAt = Date.now();
        this.options.onResult(result);
      }
    } catch (error) {
      if (!this.stopped && !this.failed) this.options.onError(error);
      this.failed = true;
      delay = Math.max(60_000, this.options.intervalMs);
    } finally {
      this.schedule(delay);
    }
  }
}