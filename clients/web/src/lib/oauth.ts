// Signing in (OAuth: email accounts, remote MCP servers): the provider sends the browser back to the
// /oauth page, which finishes the sign-in with the daemon.
import { resolve } from "$app/paths";

/** Where the provider sends the browser back: this web app's /oauth page, on the address it's open at. */
export function redirectUri(): string {
  return `${window.location.origin}${resolve("/oauth")}`;
}

/** Whether the web app is open on the computer lo9i runs on, the only place a provider sends the browser back to
 * when signing in with lo9i's own app (core/integrations/email/oauth.py::local_redirect). */
export function onThisComputer(location: Pick<Location, "protocol" | "hostname"> = window.location): boolean {
  return location.protocol === "http:" && ["localhost", "127.0.0.1"].includes(location.hostname);
}
