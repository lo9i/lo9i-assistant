import { describe, expect, it } from "vitest";
import type { ConnectedClient, Conversation, Device } from "./api/types";
import { clientLabel, conversationLabel, deviceLabel } from "./sessions";

const client = (fields: Partial<ConnectedClient>): ConnectedClient => ({
  id: "c1",
  kind: "web",
  transport: "10.0.0.2:5000",
  connected_at: "2026-10-01T10:00:00Z",
  device_id: "",
  thread_id: "",
  ...fields,
});
const devices = [{ id: "d1", name: "Laptop" }] as Device[];
const conversations = [{ thread_id: "t1", title: "Trip plans" }] as Conversation[];

describe("sessions", () => {
  it("names the client, its device and its conversation", () => {
    expect(clientLabel(client({ kind: "cli" }))).toBe("Terminal");
    expect(deviceLabel(client({}), devices)).toBe("This host");
    expect(deviceLabel(client({ device_id: "d1" }), devices)).toBe("Laptop");
    expect(conversationLabel(client({}), conversations)).toBe("None yet");
    expect(conversationLabel(client({ thread_id: "t1" }), conversations)).toBe("Trip plans");
    // Started but not saved to the list yet: no messages.
    expect(conversationLabel(client({ thread_id: "t9" }), conversations)).toBe("New conversation");
  });
});
