/** A profile section's key as a heading: "how_to_reply" → "How to reply". */
export function sectionLabel(section: string): string {
  return section.charAt(0).toUpperCase() + section.slice(1).replace(/_/g, " ");
}
