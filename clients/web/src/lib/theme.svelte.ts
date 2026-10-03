// Dark (the default), light, or following the system. Kept per browser; storage can be unavailable.
export type ThemePreference = "dark" | "light" | "system";

const KEY = "lo9i.theme";

class Theme {
  preference = $state<ThemePreference>(read());

  set(preference: ThemePreference): void {
    this.preference = preference;
    try {
      localStorage.setItem(KEY, preference);
    } catch {
      // Kept for this page only.
    }
    this.apply();
  }

  /** Sets data-theme on <html>, and follows the system while the preference is "system". */
  apply(): () => void {
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const update = () => {
      const light = this.preference === "light" || (this.preference === "system" && media.matches);
      if (light) document.documentElement.dataset.theme = "light";
      else delete document.documentElement.dataset.theme;
    };
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }
}

function read(): ThemePreference {
  try {
    const saved = localStorage.getItem(KEY);
    return saved === "light" || saved === "system" ? saved : "dark";
  } catch {
    return "dark";
  }
}

export const theme = new Theme();
