// Which quick button's panel is open: one at a time, since they open in the same corner. And how many places
// show the buttons docked (a chat's status bar), while which they don't float as well.
export type QuickPanelName = "voice" | "text";

export const quickPanel = $state<{ open: QuickPanelName | null }>({ open: null });

export const quickDock = $state({ count: 0 });
