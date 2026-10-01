/** A name for this browser in the list of paired devices, like "Firefox on Linux". */
export function deviceName(userAgent: string): string {
  return `${browser(userAgent)} on ${system(userAgent)}`;
}

function browser(ua: string): string {
  if (ua.includes("Firefox/")) return "Firefox";
  if (ua.includes("Edg/")) return "Edge";
  if (ua.includes("Chrome/")) return "Chrome";
  if (ua.includes("Safari/")) return "Safari";
  return "Browser";
}

function system(ua: string): string {
  if (/iPhone|iPad/.test(ua)) return "iOS";
  if (ua.includes("Android")) return "Android";
  if (ua.includes("Mac OS X")) return "macOS";
  if (ua.includes("Windows")) return "Windows";
  if (ua.includes("Linux")) return "Linux";
  return "an unknown system";
}
