// The app's own text in English or Spanish (WEB.md, Text and languages). Each text has a key, the same in
// locales/en.json and locales/es.json (i18n.test.ts fails when one has a key the other lacks); components show it with
// t("area.key", { name: value }). A text with a count is an object of plural forms (one, other), picked by `count` as
// the language counts. The language is the one chosen in Settings → General, which the daemon keeps for every app
// (core/language.py); auto, until the user picks one, follows this browser's: Spanish when it prefers Spanish, else
// English. The last choice is kept in this browser too, so the first paint (and the pairing page, before the daemon
// answers) is already in it. Dates and numbers are written with Intl in the same language.
import en from "./locales/en.json";
import es from "./locales/es.json";

export type Locale = "en" | "es";
export type LanguageChoice = "auto" | Locale;
export type Values = Record<string, string | number>;

type Plural = { one: string; other: string };
type Keys<T, P extends string = ""> = {
  [K in keyof T & string]: T[K] extends string | Plural ? `${P}${K}` : Keys<T[K], `${P}${K}.`>;
}[keyof T & string];
/** Every text's key, from the English texts. */
export type Key = Keys<typeof en>;

type Messages = { [key: string]: string | Messages };

const MESSAGES: Record<Locale, Messages> = { en, es };
const KEY = "lo9i.language";

class Language {
  choice = $state<LanguageChoice>(saved());
  // What text shows in: auto settled by the browser's language.
  locale = $derived<Locale>(settle(this.choice));

  /** The choice the daemon keeps, or the one just picked. */
  use(choice: LanguageChoice): void {
    this.choice = choice;
    try {
      localStorage.setItem(KEY, choice);
    } catch {
      // Kept for this page only.
    }
    if (typeof document !== "undefined") document.documentElement.lang = this.locale;
  }
}

export const language = new Language();

/** The text of `key` in the language shown, its {placeholders} filled from `values`. */
export function t(key: Key, values?: Values): string {
  const found = lookup(MESSAGES[language.locale], key) ?? lookup(en, key) ?? key;
  return fill(typeof found === "string" ? found : counted(found, values?.count), values);
}

export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(language.locale, options).format(value);
}

/** `date` (a Date, ISO text or a timestamp) as the language writes it. */
export function formatDate(date: Date | string | number, options?: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat(language.locale, options).format(new Date(date));
}

/** A language's name by its code ("es", "pt-BR"), in the language shown: "Spanish", "español". */
export function languageName(code: string): string {
  return new Intl.DisplayNames([language.locale], { type: "language" }).of(code) ?? code;
}

/** "a, b and c", or "a, b y c": English as the app writes it, without a comma before "and". */
export function formatList(items: string[]): string {
  return new Intl.ListFormat(language.locale === "en" ? "en-GB" : language.locale, { type: "conjunction" }).format(items);
}

function lookup(messages: Messages, key: string): string | Messages | undefined {
  let found: string | Messages | undefined = messages;
  for (const part of key.split(".")) {
    if (typeof found !== "object") return undefined;
    found = found[part];
  }
  return found;
}

function counted(forms: Messages, count: string | number | undefined): string {
  const category = new Intl.PluralRules(language.locale).select(Number(count ?? 0));
  const form = forms[category] ?? forms.other;
  return typeof form === "string" ? form : "";
}

function fill(text: string, values: Values | undefined): string {
  if (!values) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) => (name in values ? String(values[name]) : whole));
}

function saved(): LanguageChoice {
  try {
    const choice = localStorage.getItem(KEY);
    return choice === "en" || choice === "es" ? choice : "auto";
  } catch {
    return "auto";
  }
}

function settle(choice: LanguageChoice): Locale {
  if (choice !== "auto") return choice;
  const preferred = typeof navigator === "undefined" ? "" : navigator.language;
  return preferred.toLowerCase().startsWith("es") ? "es" : "en";
}
