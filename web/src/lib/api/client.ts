// The daemon's HTTP API for the web UI, grouped like src/assistant/client/daemon_client: the
// conversation on the client, every other area as a group.
import type { components } from "./schema";
import { resumableEvents, type ReconnectPolicy } from "./reconnect";
import type { Transport } from "./transport";
import type {
  BusEvent,
  ConnectedClient,
  Conversation,
  Decision,
  Device,
  EmailProvider,
  EmailSettings,
  EmailStatus,
  Job,
  Me,
  PairingCode,
  RunEvent,
  Session,
  ShownMessage,
  Skill,
  SkillSummary,
  StartupStatus,
  TelegramStatus,
  UsageReport,
} from "./types";

type Schemas = components["schemas"];

// Sent after a run's last event (END in src/assistant/protocol.py).
const END = "end";
// A run is short-lived; if the daemon stays away this long, the reply is reported as lost.
const RUN_RECONNECT: ReconnectPolicy = { delayMs: 1000, attempts: 5 };
// The web UI keeps the bus stream for its whole session, so it waits out a daemon restart.
const BUS_RECONNECT: ReconnectPolicy = { delayMs: 2000 };

export class ConversationsGroup {
  constructor(private readonly transport: Transport) {}

  list(): Promise<Conversation[]> {
    return this.transport.request("GET", "/conversations");
  }

  messages(threadId: string): Promise<ShownMessage[]> {
    return this.transport.request("GET", `/conversations/${encodeURIComponent(threadId)}/messages`);
  }
}

export class IdentityGroup {
  constructor(private readonly transport: Transport) {}

  async name(): Promise<string> {
    return (await this.transport.request<Schemas["AssistantName"]>("GET", "/assistant")).name;
  }

  /** The name as saved (trimmed). Throws ApiError (400) for an invalid one. */
  async rename(name: string): Promise<string> {
    return (await this.transport.request<Schemas["AssistantName"]>("PUT", "/assistant", { name })).name;
  }
}

export class JobsGroup {
  constructor(private readonly transport: Transport) {}

  list(): Promise<Job[]> {
    return this.transport.request("GET", "/jobs");
  }

  setEnabled(name: string, enabled: boolean): Promise<Job> {
    return this.transport.request("PATCH", `/jobs/${encodeURIComponent(name)}`, { enabled });
  }

  async delete(name: string): Promise<void> {
    await this.transport.request("DELETE", `/jobs/${encodeURIComponent(name)}`);
  }
}

export class TelegramGroup {
  constructor(private readonly transport: Transport) {}

  status(): Promise<TelegramStatus> {
    return this.transport.request("GET", "/integrations/telegram");
  }

  /** Checks and saves the bot token, and opens pairing. Throws ApiError (400) for a bad token. */
  connect(token: string): Promise<TelegramStatus> {
    return this.transport.request("POST", "/integrations/telegram", { token });
  }

  startPairing(): Promise<TelegramStatus> {
    return this.transport.request("POST", "/integrations/telegram/pairing");
  }

  async disconnect(): Promise<void> {
    await this.transport.request("DELETE", "/integrations/telegram");
  }
}

export class EmailGroup {
  constructor(private readonly transport: Transport) {}

  /** Mail providers to pick from, so only the address and the password are typed. */
  providers(): Promise<EmailProvider[]> {
    return this.transport.request("GET", "/integrations/email/providers");
  }

  status(): Promise<EmailStatus> {
    return this.transport.request("GET", "/integrations/email");
  }

  /** Checks the login with the server, then saves. Throws ApiError (400) when it fails. */
  connect(settings: EmailSettings): Promise<EmailStatus> {
    return this.transport.request("POST", "/integrations/email", settings);
  }

  setRecipients(addresses: string[]): Promise<EmailStatus> {
    return this.transport.request("PUT", "/integrations/email/recipients", { addresses });
  }

  async disconnect(): Promise<void> {
    await this.transport.request("DELETE", "/integrations/email");
  }
}

export class SkillsGroup {
  constructor(private readonly transport: Transport) {}

  list(): Promise<SkillSummary[]> {
    return this.transport.request("GET", "/skills");
  }

  get(name: string): Promise<Skill> {
    return this.transport.request("GET", `/skills/${encodeURIComponent(name)}`);
  }

  async delete(name: string): Promise<void> {
    await this.transport.request("DELETE", `/skills/${encodeURIComponent(name)}`);
  }
}

export class UsageGroup {
  constructor(private readonly transport: Transport) {}

  report(days: number): Promise<UsageReport> {
    return this.transport.request("GET", `/usage?days=${days}`);
  }
}

export class SystemGroup {
  constructor(private readonly transport: Transport) {}

  startup(): Promise<StartupStatus> {
    return this.transport.request("GET", "/system/startup");
  }

  /** Throws ApiError (400) when macOS refuses or the password dialog is cancelled. */
  enableStartup(): Promise<StartupStatus> {
    return this.transport.request("POST", "/system/startup");
  }

  disableStartup(): Promise<StartupStatus> {
    return this.transport.request("DELETE", "/system/startup");
  }
}

export class AuthGroup {
  constructor(private readonly transport: Transport) {}

  /** This browser's device. Throws ApiError (401) when it isn't paired. */
  me(): Promise<Me> {
    return this.transport.request("GET", "/auth/me");
  }

  /** Pairs this browser with a code from a trusted client; the daemon sets the token cookie. */
  pair(code: string, name: string): Promise<Device> {
    return this.transport.request("POST", "/auth/pair", { code, name });
  }

  /** Unpairs this browser. */
  async logout(): Promise<void> {
    await this.transport.request("POST", "/auth/logout");
  }
}

export class DevicesGroup {
  constructor(private readonly transport: Transport) {}

  /** Most recently used first. */
  list(): Promise<Device[]> {
    return this.transport.request("GET", "/devices");
  }

  /** A one-time code to enter on another device, replacing any earlier one. */
  openPairing(): Promise<PairingCode> {
    return this.transport.request("POST", "/devices/pairing");
  }

  async revoke(id: string): Promise<void> {
    await this.transport.request("DELETE", `/devices/${encodeURIComponent(id)}`);
  }
}

export class ClientsGroup {
  constructor(private readonly transport: Transport) {}

  list(): Promise<ConnectedClient[]> {
    return this.transport.request("GET", "/clients");
  }
}

export class DaemonClient {
  readonly conversations: ConversationsGroup;
  readonly identity: IdentityGroup;
  readonly jobs: JobsGroup;
  readonly telegram: TelegramGroup;
  readonly email: EmailGroup;
  readonly skills: SkillsGroup;
  readonly usage: UsageGroup;
  readonly system: SystemGroup;
  readonly clients: ClientsGroup;
  readonly auth: AuthGroup;
  readonly devices: DevicesGroup;

  constructor(private readonly transport: Transport) {
    this.conversations = new ConversationsGroup(transport);
    this.identity = new IdentityGroup(transport);
    this.jobs = new JobsGroup(transport);
    this.telegram = new TelegramGroup(transport);
    this.email = new EmailGroup(transport);
    this.skills = new SkillsGroup(transport);
    this.usage = new UsageGroup(transport);
    this.system = new SystemGroup(transport);
    this.clients = new ClientsGroup(transport);
    this.auth = new AuthGroup(transport);
    this.devices = new DevicesGroup(transport);
  }

  /** How the daemon names this client in the runs it announces. */
  get clientId(): string {
    return this.transport.clientId;
  }

  /** Move this client to a new conversation. */
  async newThread(): Promise<string> {
    return (await this.transport.request<Schemas["ThreadCreated"]>("POST", "/threads")).thread_id;
  }

  /** Move this client to an earlier conversation. Throws ApiError (404) for one that has no messages. */
  async resumeThread(threadId: string): Promise<void> {
    await this.transport.request("POST", `/conversations/${encodeURIComponent(threadId)}/resume`);
  }

  async *send(session: Session, text: string, files: File[], signal: AbortSignal): AsyncGenerator<RunEvent> {
    const form = new FormData();
    form.append("channel", session.channel);
    form.append("text", text);
    files.forEach((file) => form.append("files", file, file.name));
    const run = await this.transport.request<Schemas["RunStarted"]>("POST", `${thread(session)}/messages`, form);
    yield* this.followRun(run.run_id, signal);
  }

  async *resume(session: Session, decisions: Record<string, Decision>, signal: AbortSignal): AsyncGenerator<RunEvent> {
    const body = { channel: session.channel, decisions };
    const run = await this.transport.request<Schemas["RunStarted"]>("POST", `${thread(session)}/approvals`, body);
    yield* this.followRun(run.run_id, signal);
  }

  /** Stop the conversation's run in progress, whichever channel started it. */
  async cancel(session: Session): Promise<boolean> {
    return (await this.transport.request<Schemas["CancelResult"]>("POST", `${thread(session)}/cancel`)).cancelled;
  }

  /** A run's events from its first, reconnecting if the connection drops. */
  async *followRun(runId: string, signal: AbortSignal): AsyncGenerator<RunEvent> {
    for await (const event of resumableEvents(this.transport, `/runs/${runId}/events`, RUN_RECONNECT, signal)) {
      if (event.event === END) return;
      yield JSON.parse(event.data) as RunEvent;
    }
  }

  /** Daemon events from now on, for as long as `signal` isn't aborted, resuming after a daemon restart. */
  async *events(signal: AbortSignal): AsyncGenerator<BusEvent> {
    for await (const event of resumableEvents(this.transport, "/events", BUS_RECONNECT, signal, "")) {
      yield { kind: event.event, data: JSON.parse(event.data) };
    }
  }
}

function thread(session: Session): string {
  return `/threads/${encodeURIComponent(session.thread_id)}`;
}
