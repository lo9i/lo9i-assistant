// An MCP server's form (core/mcp/elicitation.py) as the chat's dialog fills it in: what each field starts with, and
// what's sent. The daemon checks the answer again against the form; this only keeps the dialog honest.
import type { FormField } from "./api/types";

/** What a field holds while it's filled in: text for what's typed, a flag, or the options picked. */
export type FieldValue = string | boolean | string[];

export function startValue(field: FormField): FieldValue {
  if (field.type === "boolean") return field.default === true;
  if (field.type === "choices") return Array.isArray(field.default) ? field.default.map(String) : [];
  return field.default === undefined || field.default === null ? "" : String(field.default);
}

/** The content to send, and the titles of the required fields left empty. Empty fields aren't sent. */
export function formContent(
  fields: FormField[],
  values: Record<string, FieldValue>,
): { content: Record<string, unknown>; missing: string[] } {
  const content: Record<string, unknown> = {};
  const missing: string[] = [];
  for (const field of fields) {
    const value = values[field.key];
    const empty = value === "" || value === undefined || (Array.isArray(value) && value.length === 0);
    if (empty && field.type !== "boolean") {
      if (field.required) missing.push(field.title);
      continue;
    }
    content[field.key] = field.type === "number" || field.type === "integer" ? Number(value) : value;
  }
  return { content, missing };
}
