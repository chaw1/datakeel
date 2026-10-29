export async function warmImage(url: string): Promise<void> {
  const image = new Image();
  const loaded = new Promise<void>((resolve) => {
    image.onload = () => {
      resolve();
    };
    image.onerror = () => {
      resolve();
    };
  });
  image.src = url;
  if (typeof image.decode === "function")
    await image.decode().catch(() => undefined);
  else await loaded;
}

interface CacheEntry<T> {
  promise: Promise<T>;
  value?: T;
}

/** Cache typed task details (including revisions) and decoded media together. */
export class TaskPrefetchCache<T> {
  private readonly entries = new Map<string, CacheEntry<T>>();

  constructor(
    private readonly load: (taskId: string) => Promise<T>,
    private readonly mediaUrl: (task: T) => string | null,
    private readonly warm: (url: string) => Promise<void> = warmImage,
  ) {}

  peek(taskId: string) {
    return this.entries.get(taskId)?.value ?? null;
  }

  get(taskId: string): Promise<T> {
    const found = this.entries.get(taskId);
    if (found) {
      this.entries.delete(taskId);
      this.entries.set(taskId, found);
      return found.promise;
    }
    const entry: CacheEntry<T> = {
      promise: this.load(taskId).then(async (task) => {
        const url = this.mediaUrl(task);
        if (url) await this.warm(url);
        if (this.entries.get(taskId) === entry) entry.value = task;
        return task;
      }),
    };
    this.entries.set(taskId, entry);
    while (this.entries.size > 8) {
      const oldest = this.entries.keys().next().value;
      if (oldest !== undefined) this.entries.delete(oldest);
    }
    void entry.promise.catch(() => {
      if (this.entries.get(taskId) === entry) this.entries.delete(taskId);
    });
    return entry.promise;
  }

  prefetch(taskIds: readonly string[], currentIndex: number) {
    for (const taskId of taskIds.slice(currentIndex + 1, currentIndex + 3)) {
      void this.get(taskId).catch(() => undefined);
    }
  }

  invalidate(taskId: string) {
    this.entries.delete(taskId);
  }

  clear() {
    this.entries.clear();
  }

  set(taskId: string, task: T) {
    this.entries.set(taskId, { promise: Promise.resolve(task), value: task });
  }
}
