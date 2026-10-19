import { redirect } from "@sveltejs/kit";
import { resolve } from "$app/paths";

// Chat opens to its list of conversations.
export function load(): never {
  redirect(307, resolve("/conversations"));
}
