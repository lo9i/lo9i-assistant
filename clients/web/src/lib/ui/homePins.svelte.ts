// The conversations pinned to Home (core/home/pins.py), the same on every device, for the buttons that pin and
// unpin them. Call during component setup.
import { resource, useDaemon } from "$lib/daemon.svelte";
import { t } from "$lib/i18n.svelte";

export type HomePins = {
  /** Their ids, the first pinned first; empty until loaded. */
  readonly list: string[];
  has(threadId: string): boolean;
  /** Pins it, or unpins it when it is. */
  toggle(threadId: string): Promise<void>;
};

export function homePins(): HomePins {
  const { client, notices } = useDaemon();
  // Pins are saved with Home, whose changes come as `home` events.
  const pins = resource((c) => c.home.pins(), ["home"]);
  const list = () => pins.data ?? [];
  return {
    get list() {
      return list();
    },
    has: (threadId) => list().includes(threadId),
    async toggle(threadId) {
      const pinned = list().includes(threadId);
      try {
        pins.data = pinned ? await client.home.unpin(threadId) : await client.home.pin(threadId);
        notices.notify(pinned ? t("pins.unpinned") : t("pins.pinned"));
      } catch (e) {
        notices.report(e);
      }
    },
  };
}
