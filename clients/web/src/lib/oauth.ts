// Signing in (OAuth: email accounts, remote MCP servers): the provider sends the browser back to the
// /oauth page, which finishes the sign-in with the daemon.
import { resolve } from "$app/paths";

/** Where the provider sends the browser back: this web app's /oauth page, on the address it's open at. */
export function redirectUri(): string {
  return `${window.location.origin}${resolve("/oauth")}`;
}
