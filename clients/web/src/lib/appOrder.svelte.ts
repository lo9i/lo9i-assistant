// The order the user dragged the apps (plugin pages) into in the sidebar. Kept per browser; storage can be unavailable.
const KEY = "lo9i.appOrder";

class AppOrder {
  names = $state<string[]>(read());

  // The items sorted by the saved order; ones never placed keep their own order after those placed.
  sort<T extends { name: string }>(items: T[]): T[] {
    const at = (n: string) => {
      const i = this.names.indexOf(n);
      return i < 0 ? Number.MAX_SAFE_INTEGER : i;
    };
    return items
      .map((item, i) => ({ item, i }))
      .sort((a, b) => at(a.item.name) - at(b.item.name) || a.i - b.i)
      .map((x) => x.item);
  }

  // Puts `name` where `target` is in `shown` (the order on screen), and saves it.
  move(shown: string[], name: string, target: string): void {
    if (name === target) return;
    const rest = shown.filter((n) => n !== name);
    const to = rest.indexOf(target);
    const from = shown.indexOf(name);
    const toIndex = shown.indexOf(target);
    rest.splice(from < toIndex ? to + 1 : to, 0, name);
    this.names = rest;
    try {
      localStorage.setItem(KEY, JSON.stringify(rest));
    } catch {
      // Kept for this page only.
    }
  }
}

function read(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((n) => typeof n === "string") : [];
  } catch {
    return [];
  }
}

export const appOrder = new AppOrder();
