// The daemon events the chat reacts to, like clients/terminal/src/lo9i_terminal/tui/live.py.
import type { EventHub } from "../api/eventHub";
import type { RunAnnounced, RunFinished, SentOn } from "../api/types";
import { voiceCall } from "../voiceCall.svelte";
import type { ChatController } from "./controller";

/** The chats a run event goes to: one, or every open one. */
type Chats = { all(): ChatController[] };

/** What a live voice call's events say (core/voice/): what was said kept in a conversation, or a call that ended. */
type VoiceCallEvent = { thread_id: string; call_id?: string; live?: boolean };

/** Shows runs started elsewhere, goes where a message held while an update installed was sent on after it, and
 * reports replies left running; shows what a live voice call said once it's kept, and ends this tab's call when the
 * daemon says it ended; shows the note a change of a conversation's model leaves. Returns what stops it. */
export function followRuns(hub: EventHub, chats: Chats): () => void {
  const stops = [
    hub.on(["run"], (data) => chats.all().forEach((chat) => chat.mirror(data as RunAnnounced))),
    hub.on(["run_finished"], (data) => chats.all().forEach((chat) => chat.runFinished(data as RunFinished))),
    hub.on(["sent_on"], (data) => chats.all().forEach((chat) => void chat.sentOn(data as SentOn))),
    hub.on(["voice_said"], (data) => chats.all().forEach((chat) => void chat.voiceSaid((data as VoiceCallEvent).thread_id))),
    hub.on(["conversation_model"], (data) =>
      chats.all().forEach((chat) => void chat.modelChanged((data as { thread_id: string }).thread_id)),
    ),
    hub.on(["voice_call"], (data) => {
      const call = data as VoiceCallEvent;
      if (!call.live && call.call_id) voiceCall.ended(call.call_id);
    }),
  ];
  return () => stops.forEach((stop) => stop());
}
