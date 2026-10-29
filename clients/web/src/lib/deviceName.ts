import { t } from "./i18n.svelte";

/** A name for this browser in the list of paired devices, like "Firefox on Linux". */
export function deviceName(userAgent: string): string {
  return t("devices.browserOn", { browser: browser(userAgent), system: system(userAgent) });
}

function browser(ua: string): string {
  if (ua.includes("Firefox/")) return "Firefox";
  if (ua.includes("Edg/")) return "Edge";
  if (ua.includes("Chrome/")) return "Chrome";
  if (ua.includes("Safari/")) return "Safari";
  return t("devices.browser");
}

function system(ua: string): string {
  if (/iPhone|iPad/.test(ua)) return "iOS";
  if (ua.includes("Android")) return "Android";
  if (ua.includes("Mac OS X")) return "macOS";
  if (ua.includes("Windows")) return "Windows";
  if (ua.includes("Linux")) return "Linux";
  return t("devices.unknownSystem");
}
