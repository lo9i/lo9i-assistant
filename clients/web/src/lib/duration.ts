/** How long between two times, roughly: "under a minute", "12 min", "2 h 5 min", "3 days". */
export function duration(from: string, to: string): string {
  const minutes = Math.floor((new Date(to).getTime() - new Date(from).getTime()) / 60000);
  if (minutes < 1) return "under a minute";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "1 day" : `${days} days`;
}

/** "just now", "12 min ago", "3 days ago". */
export function ago(at: string, now: string): string {
  const since = duration(at, now);
  return since === "under a minute" ? "just now" : `${since} ago`;
}
