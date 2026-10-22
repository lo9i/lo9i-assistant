// Which floating button's panel is open: one at a time, since they show in the same corner.
export type QuickPanelName = "voice" | "text";

export const quickPanel = $state<{ open: QuickPanelName | null }>({ open: null });
