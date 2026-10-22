import { redirect } from "@sveltejs/kit";
import { resolve } from "$app/paths";

// The app opens on Home.
export function load(): never {
  redirect(307, resolve("/home"));
}
