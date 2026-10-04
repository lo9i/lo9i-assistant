import { describe as group, expect, it } from "vitest";
import type { ChannelStatus } from "./api/types";
import { alertOptions, lineOf, stateOf, titleOf } from "./channels";

const channel = (enabled: boolean, connected: boolean): ChannelStatus => ({ name: "telegram", enabled, connected, items: [] });

group("channels", () => {
  it("says whether a channel is off, connected or waiting", () => {
    expect([stateOf(channel(false, false)), stateOf(channel(true, true)), stateOf(channel(true, false))]).toEqual([
      "Off",
      "Connected",
      "Not connected",
    ]);
    expect(titleOf("telegram")).toBe("Telegram");
  });

  it("shows a text item with its label when it has one", () => {
    expect(lineOf({ kind: "text", label: "", value: "Bot: @lo9i_bot" })).toBe("Bot: @lo9i_bot");
    expect(lineOf({ kind: "text", label: "Paired", value: "Ani" })).toBe("Paired: Ani");
  });

  it("offers new mail alerts on installed channels, keeping the one set", () => {
    expect(alertOptions(["telegram"], "").map((o) => o.value)).toEqual(["", "telegram"]);
    expect(alertOptions(["telegram"], "slack").map((o) => o.value)).toEqual(["", "telegram", "slack"]);
    expect(alertOptions([], "")[0].label).toBe("Don't announce");
  });
});
