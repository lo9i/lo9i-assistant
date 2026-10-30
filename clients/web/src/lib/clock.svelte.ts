// The time now, moved on every half minute while a component shows it, for how long something has been going
// ("is working · 3m"). Call during component setup.
export function clock(everyMs = 30_000): { readonly now: string } {
  let now = $state(new Date().toISOString());
  $effect(() => {
    const timer = setInterval(() => (now = new Date().toISOString()), everyMs);
    return () => clearInterval(timer);
  });
  return {
    get now() {
      return now;
    },
  };
}
