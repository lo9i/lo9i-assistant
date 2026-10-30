// The daemon's HTTP API for the web UI, grouped like src/assistant/client/daemon_client: the
// conversation on the client, every other area as a group.
import type { components } from "./schema";
import { resumableEvents, type ReconnectPolicy } from "./reconnect";
import { LogStreams } from "./logStreams";
import { RunStreams } from "./runStreams";
import type { Transport } from "./transport";
import type {
  Agent,
  AgentFolders,
  Alert,
  ApprovalRequest,
  ApprovalRequired,
  DoctorPage,
  Notification,
  HomePage,
  HomeSection,
  BusEvent,
  ChannelStatus,
  ConnectedClient,
  Conversation,
  ConversationStats,
  Decision,
  Device,
  Dispatched,
  EmailAccount,
  EmailProvider,
  EmailSettings,
  EmailSignIn,
  Episode,
  Fact,
  FileDiff,
  FilePreview,
  FolderContents,
  FolderListing,
  FolderRefresh,
  Handoff,
  HostStatus,
  InstalledFromRepository,
  Job,
  KeptKeys,
  LanguageSetting,
  LogEvent,
  LogLevelSetting,
  LogOptions,
  LogPage,
  LogQuery,
  McpProbe,
  McpServerChange,
  McpServerSettings,
  McpServerStatus,
  Me,
  MemorySnapshot,
  ModelChange,
  ModelOption,
  ModelProvider,
  ModelStatus,
  Page,
  PairingCode,
  PendingEnding,
  PluginSettings,
  PluginSettingsChange,
  PluginSignInStart,
  PluginUpdate,
  PluginUpdateChecks,
  PromptSection,
  Removed,
  Repository,
  RepositoryContents,
  RepositoryPlugins,
  RunEvent,
  DispatchSetting,
  RunInProgress,
  RunningTask,
  ServerValues,
  Session,
  ShownCall,
  ShownConversation,
  ShownMessage,
  ShutdownStatus,
  SignedIn,
  Importables,
  ImportOutcome,
  Skill,
  SkillSummary,
  SpeechStatus,
  StartupStatus,
  TokenReport,
  UpdateStatus,
  UploadedFile,
  UsageReport,
  WebSearchStatus,
} from "./types";

type Schemas = components["schemas"];

// The web UI keeps the bus stream for its whole session, so it waits out a daemon restart.
const BUS_RECONNECT: ReconnectPolicy = { delayMs: 2000 };

export class ConversationsGroup {
  constructor(private readonly transport: Transport) {}

  list(): Promise<Conversation[]> {
    return this.transport.request("GET", "/conversations");
  }

  /** The ids of the conversations whose messages hold every word of `text`, each as the start of a word. */
  async containing(text: string): Promise<string[]> {
    const path = `/conversations/containing?q=${encodeURIComponent(text)}`;
    return (await this.transport.request<Schemas["ConversationsContaining"]>("GET", path)).thread_ids;
  }

  messages(threadId: string): Promise<ShownMessage[]> {
    return this.transport.request("GET", `/conversations/${encodeURIComponent(threadId)}/messages`);
  }

  /** Its messages up to its runs in progress, and those runs, oldest first, to follow from their start (`followRun`)
   * as if the page had been watching them. */
  live(threadId: string): Promise<ShownConversation> {
    return this.transport.request("GET", `/conversations/${encodeURIComponent(threadId)}/live`);
  }

  /** A tool call in full, which `messages` shows only the start of when it's `partial`. Throws ApiError (404) when
   * the conversation has no such call. */
  toolCall(threadId: string, callId: string): Promise<ShownCall> {
    const path = `/conversations/${encodeURIComponent(threadId)}/tool-calls/${encodeURIComponent(callId)}`;
    return this.transport.request("GET", path);
  }

  /** A step inside a tool call in full (a delegate call's, a handed-off agent's), by its place from 0. */
  toolCallStep(threadId: string, callId: string, index: number): Promise<ShownCall> {
    const path = `/conversations/${encodeURIComponent(threadId)}/tool-calls/${encodeURIComponent(callId)}/steps/${index}`;
    return this.transport.request("GET", path);
  }

  /** The conversation the first message of a new one, `text`, continues; "" for the new one. Sends nothing. */
  async route(text: string): Promise<string> {
    return (await this.transport.request<Schemas["Routed"]>("POST", "/routes", { text })).thread_id;
  }

  /** Its messages, tokens and tool calls, and when it started and was last written in; all zero for a new one. */
  stats(threadId: string): Promise<ConversationStats> {
    return this.transport.request("GET", `/conversations/${encodeURIComponent(threadId)}/stats`);
  }

  /** What its run stopped to ask and still waits for, whoever started it; answered with `resume`. */
  async approvals(threadId: string): Promise<ApprovalRequired[]> {
    const path = `/conversations/${encodeURIComponent(threadId)}/approvals`;
    const waiting = await this.transport.request<Schemas["ApprovalRequired"][]>("GET", path);
    return waiting.map((a) => ({ type: "ApprovalRequired", interrupt_id: a.interrupt_id, request: a.request as ApprovalRequest }));
  }

  /** Deletes its messages, its place in the list, and the files sent in it. Fails while a client is on it. */
  async delete(threadId: string): Promise<void> {
    await this.transport.request("DELETE", `/conversations/${encodeURIComponent(threadId)}`);
  }

  /** The skills pinned to the conversation, in the order they were pinned. */
  async pinned(threadId: string): Promise<string[]> {
    return (await this.transport.request<Schemas["PinnedSkills"]>("GET", this.pinPath(threadId))).skills;
  }

  /** Takes effect from the next message. Throws ApiError (404) for an unknown skill. */
  async pin(threadId: string, name: string): Promise<string[]> {
    const path = `${this.pinPath(threadId)}/${encodeURIComponent(name)}`;
    return (await this.transport.request<Schemas["PinnedSkills"]>("PUT", path)).skills;
  }

  async unpin(threadId: string, name: string): Promise<string[]> {
    const path = `${this.pinPath(threadId)}/${encodeURIComponent(name)}`;
    return (await this.transport.request<Schemas["PinnedSkills"]>("DELETE", path)).skills;
  }

  /** The agents installed plugins bring: /<command> hands a conversation to one. */
  agents(): Promise<Agent[]> {
    return this.transport.request("GET", "/agents");
  }

  /** The folders to offer for /<command>: the workspace and the ones used before. */
  agentFolders(): Promise<AgentFolders> {
    return this.transport.request("GET", "/agents/folders");
  }

  /** The folders inside `path`, to browse to one; hidden ones (named with a dot) too when `hidden`. Throws ApiError
   * (400) when it isn't a full path or can't be read. */
  childFolders(path: string, hidden = false): Promise<FolderListing> {
    const query = `path=${encodeURIComponent(path)}${hidden ? "&hidden=true" : ""}`;
    return this.transport.request("GET", `/agents/folders/children?${query}`);
  }

  /** The agent the conversation is handed to; null while the assistant answers. */
  async agent(threadId: string): Promise<Handoff | null> {
    const found = await this.transport.request<Schemas["ConversationAgent"]>("GET", this.agentPath(threadId));
    return found.handoff ?? null;
  }

  /** From the next message the agent answers, working in `folder`. Throws ApiError (400) for an unknown agent or folder. */
  async handTo(threadId: string, command: string, folder: string): Promise<Handoff> {
    const found = await this.transport.request<Schemas["ConversationAgent"]>("PUT", this.agentPath(threadId), { command, folder });
    return found.handoff as Handoff;
  }

  /** The assistant answers again from the next message. */
  async takeBack(threadId: string): Promise<void> {
    await this.transport.request("DELETE", this.agentPath(threadId));
  }

  /** Passes a message, and the files sent with it, on to the agent while it works on the conversation's last one;
   * it takes it between its steps. Throws ApiError (409) when it isn't working, or can't take messages while it
   * works. */
  async messageAgent(threadId: string, text: string, files: File[] = []): Promise<void> {
    const form = new FormData();
    form.append("text", text);
    files.forEach((file) => form.append("files", file, file.name));
    await this.transport.request("POST", `${this.agentPath(threadId)}/messages`, form);
  }

  /** Stops the agent's step in progress; it waits for the next message. Throws ApiError (409) as messageAgent. */
  async interruptAgent(threadId: string): Promise<void> {
    await this.transport.request("POST", `${this.agentPath(threadId)}/interrupt`);
  }

  /** The files and folders in `path` of the folder the conversation is handed to ("" for itself), folders first.
   * Throws ApiError: 400 for a path outside it or one it hides, 404 when it isn't handed over or the path is gone. */
  agentFolder(threadId: string, path = ""): Promise<FolderContents> {
    return this.transport.request("GET", `${this.agentPath(threadId)}/folder?path=${encodeURIComponent(path)}`);
  }

  /** A file of that folder as text to preview (none when it isn't text). Throws ApiError as agentFolder. */
  agentFile(threadId: string, path: string): Promise<FilePreview> {
    return this.transport.request("GET", `${this.agentPath(threadId)}/folder/file?path=${encodeURIComponent(path)}`);
  }

  /** Each of `folders` as agentFolder lists it, and what git says changed, in one request that asks git once: the
   * panel's refresh. A folder that can't be read (gone since) says why in its `error`. Throws ApiError (404) when it
   * isn't handed over. */
  agentRefresh(threadId: string, folders: string[]): Promise<FolderRefresh> {
    const query = folders.map((path) => `path=${encodeURIComponent(path)}`).join("&");
    return this.transport.request("GET", `${this.agentPath(threadId)}/folder/refresh?${query}`);
  }

  /** What changed in a file git lists as changed in that folder, as `git diff` shows it (a new file whole). Throws
   * ApiError as agentFolder, 404 for a file git doesn't list as changed. */
  agentDiff(threadId: string, path: string): Promise<FileDiff> {
    return this.transport.request("GET", `${this.agentPath(threadId)}/folder/diff?path=${encodeURIComponent(path)}`);
  }

  /** Moves a file of that folder to the system's trash, never a folder. Throws ApiError as agentFolder, and 403 while
   * deleting is off (FoldersGroup.deleting). */
  async deleteAgentFile(threadId: string, path: string): Promise<void> {
    await this.transport.request("DELETE", `${this.agentPath(threadId)}/folder/file?path=${encodeURIComponent(path)}`);
  }

  private agentPath(threadId: string): string {
    return `/conversations/${encodeURIComponent(threadId)}/agent`;
  }

  private pinPath(threadId: string): string {
    return `/conversations/${encodeURIComponent(threadId)}/pinned`;
  }
}

export class FilesGroup {
  constructor(private readonly transport: Transport) {}

  /** The files in the user's conversations, sent by them or brought by tool results, newest first: those matching
   * `query` (name, type, where it came from or conversation), the `page` of them or all. */
  list(query = "", page?: Page): Promise<UploadedFile[]> {
    return this.transport.request("GET", `/files${pageQuery(page, query ? { q: query } : {})}`);
  }

  /** A file's content, to show or save. Throws ApiError (404) when it isn't there any more. */
  content(file: UploadedFile): Promise<Blob> {
    return this.transport.blob("GET", `/files/content?path=${encodeURIComponent(file.path)}`);
  }
}

export class FoldersGroup {
  constructor(private readonly transport: Transport) {}

  /** The files and folders in `path` of the user's home folder ("" for itself), folders first, as the panel shows
   * them beside a conversation not handed to an agent. Throws ApiError as ConversationsGroup.agentFolder. */
  home(path = ""): Promise<FolderContents> {
    return this.transport.request("GET", `/folders/home?path=${encodeURIComponent(path)}`);
  }

  /** A file of the home folder as text to preview (none when it isn't text). Throws ApiError as home. */
  homeFile(path: string): Promise<FilePreview> {
    return this.transport.request("GET", `/folders/home/file?path=${encodeURIComponent(path)}`);
  }

  /** Moves a file of the home folder to the trash, never a folder. Throws ApiError as home, and 403 while deleting is
   * off. */
  async deleteHomeFile(path: string): Promise<void> {
    await this.transport.request("DELETE", `/folders/home/file?path=${encodeURIComponent(path)}`);
  }

  /** Whether the panel may delete files (this folder's or the handed one's); off until the user turns it on. */
  async deleting(): Promise<boolean> {
    return (await this.transport.request<Schemas["FolderDeleting"]>("GET", "/settings/folder-deleting")).enabled;
  }

  async setDeleting(enabled: boolean): Promise<boolean> {
    return (await this.transport.request<Schemas["FolderDeleting"]>("PUT", "/settings/folder-deleting", { enabled })).enabled;
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

  /** The whole reply of the job's run that started `at`; its record keeps only the end of it. */
  async runReply(name: string, at: string): Promise<string> {
    const reply: Schemas["JobRunReply"] = await this.transport.request(
      "GET",
      `/jobs/${encodeURIComponent(name)}/reply?at=${encodeURIComponent(at)}`,
    );
    return reply.text;
  }
}

/** The chat channels installed as plugins (Telegram, Slack): what each shows for setting it up, and its buttons. */
export class ChannelsGroup {
  constructor(private readonly transport: Transport) {}

  list(): Promise<ChannelStatus[]> {
    return this.transport.request("GET", "/channels");
  }

  /** Presses a setup button (a SetupItem of kind "action"). Throws ApiError (409) when the channel isn't connected. */
  async press(name: string, action: string): Promise<void> {
    await this.transport.request("POST", `/channels/${encodeURIComponent(name)}/actions/${encodeURIComponent(action)}`);
  }
}

export class WebSearchGroup {
  constructor(private readonly transport: Transport) {}

  status(): Promise<WebSearchStatus> {
    return this.transport.request("GET", "/integrations/web-search");
  }

  /** Checks the Brave Search API key with one search, then saves it. Throws ApiError (400) when Brave refuses it. */
  setBraveKey(key: string): Promise<WebSearchStatus> {
    return this.transport.request("PUT", "/integrations/web-search/brave-key", { key });
  }

  removeBraveKey(): Promise<WebSearchStatus> {
    return this.transport.request("DELETE", "/integrations/web-search/brave-key");
  }
}

export class SpeechGroup {
  constructor(private readonly transport: Transport) {}

  settings(): Promise<SpeechStatus> {
    return this.transport.request("GET", "/settings/speech");
  }

  /** Used from the next voice message. Throws ApiError (400) for an unknown model or language. */
  /** `decoding`: "accurate" (beam search) or "fast" (greedy); left out, it stays as it is. */
  change(model: string, languages: string[], decoding?: SpeechStatus["decoding"]): Promise<SpeechStatus> {
    return this.transport.request("PUT", "/settings/speech", { model, languages, decoding });
  }

  /** When replies are also spoken ("off", "voice", "always"), and in which voice. */
  changeReplies(spokenReplies: SpeechStatus["spoken_replies"], voice: string): Promise<SpeechStatus> {
    return this.transport.request("PUT", "/settings/speech/replies", { spoken_replies: spokenReplies, voice });
  }

  /** The text read aloud on the host, as WAV. `voice` "" uses the reply voice. */
  speak(text: string, voice = ""): Promise<Blob> {
    return this.transport.blob("POST", "/speech", { text, voice });
  }
}

export class ModelGroup {
  constructor(private readonly transport: Transport) {}

  /** How sure routing a message from the inbox has to be to continue a conversation; below it, a new one starts. */
  dispatch(): Promise<DispatchSetting> {
    return this.transport.request("GET", "/settings/dispatch");
  }

  /** 400 (ApiError): a confidence outside 0 to 1. */
  setDispatch(setting: DispatchSetting): Promise<DispatchSetting> {
    return this.transport.request("PUT", "/settings/dispatch", setting);
  }

  /** Providers to pick from, with the models to suggest. */
  providers(): Promise<ModelProvider[]> {
    return this.transport.request("GET", "/settings/model/providers");
  }

  status(): Promise<ModelStatus> {
    return this.transport.request("GET", "/settings/model");
  }

  /** Checks that both models answer, then uses them. An empty key keeps the current one when the
   * provider stays the same. Throws ApiError (400) when a model doesn't answer. */
  set(change: ModelChange): Promise<ModelStatus> {
    return this.transport.request("PUT", "/settings/model", change);
  }

  /** The provider's models for these values, to pick from; empty when it can't list them. A key left
   * empty uses the saved one. Throws ApiError (400) when the provider refuses the key. */
  available(provider: string, values: Record<string, string>): Promise<ModelOption[]> {
    return this.transport.request("POST", "/settings/model/available", { provider, values });
  }

  /** Back to the model in .env. */
  reset(): Promise<ModelStatus> {
    return this.transport.request("DELETE", "/settings/model");
  }
}

/** The system prompt texts the user edits: the persona, the operating instructions and the channel hints. An
 * edit is used from the next message in each conversation; a `prompts` event tells when one changes. */
export class PromptsGroup {
  constructor(private readonly transport: Transport) {}

  list(): Promise<PromptSection[]> {
    return this.transport.request("GET", "/settings/prompts");
  }

  /** Saving the built-in text drops the edit. Throws ApiError (400) for an empty text. */
  save(name: string, text: string): Promise<PromptSection> {
    return this.transport.request("PUT", `/settings/prompts/${encodeURIComponent(name)}`, { text });
  }

  /** Keeps the edit as it is after its built-in text changed (`built_in_changes`), which isn't said again. */
  keep(name: string): Promise<PromptSection> {
    return this.transport.request("POST", `/settings/prompts/${encodeURIComponent(name)}/kept`);
  }

  /** Back to the built-in text. */
  reset(name: string): Promise<PromptSection> {
    return this.transport.request("DELETE", `/settings/prompts/${encodeURIComponent(name)}`);
  }
}

export class EmailGroup {
  constructor(private readonly transport: Transport) {}

  /** Mail providers to pick from, so only the address and the password are typed. */
  providers(): Promise<EmailProvider[]> {
    return this.transport.request("GET", "/integrations/email/providers");
  }

  /** The default account first. */
  accounts(): Promise<EmailAccount[]> {
    return this.transport.request("GET", "/integrations/email/accounts");
  }

  /** Checks the logins with the servers, then saves. Throws ApiError (400) when they fail. */
  add(settings: EmailSettings): Promise<EmailAccount> {
    return this.transport.request("POST", "/integrations/email/accounts", settings);
  }

  /** Changes the sign-in; an empty password keeps the saved one. Throws ApiError (400) when it fails. */
  update(id: string, settings: EmailSettings): Promise<EmailAccount> {
    return this.transport.request("PUT", this.path(id), settings);
  }

  /** Only the name; the sign-in stays. Throws ApiError (400) when another account has it. */
  rename(id: string, label: string): Promise<EmailAccount> {
    return this.transport.request("PUT", `${this.path(id)}/label`, { label });
  }

  makeDefault(id: string): Promise<EmailAccount> {
    return this.transport.request("PUT", `${this.path(id)}/default`);
  }

  /** Who the assistant emails without asking, from any account, besides the user's own accounts. */
  async recipients(): Promise<string[]> {
    return (await this.transport.request<{ addresses: string[] }>("GET", "/integrations/email/recipients")).addresses;
  }

  async setRecipients(addresses: string[]): Promise<string[]> {
    const body = { addresses };
    return (await this.transport.request<{ addresses: string[] }>("PUT", "/integrations/email/recipients", body)).addresses;
  }

  /** Announce new mail on an installed channel (its name), or nowhere (""). Throws ApiError (400) when reading isn't set up. */
  setNewMailAlerts(id: string, channel: string): Promise<EmailAccount> {
    return this.transport.request("PUT", `${this.path(id)}/alerts`, { channel });
  }

  async remove(id: string): Promise<void> {
    await this.transport.request("DELETE", this.path(id));
  }

  /** The provider's sign-in page (OAuth); the browser comes back to `redirect_uri`, the /oauth page. */
  async startSignIn(body: EmailSignIn): Promise<string> {
    return (await this.transport.request<{ url: string }>("POST", "/integrations/email/oauth/start", body)).url;
  }

  private path(id: string): string {
    return `/integrations/email/accounts/${encodeURIComponent(id)}`;
  }
}

export class OAuthGroup {
  constructor(private readonly transport: Transport) {}

  /** The /oauth page's last step, for an email account or a remote MCP server: works in a browser
   * that isn't paired; the one-time state is the proof. */
  finish(state: string, code: string): Promise<SignedIn> {
    return this.transport.request("POST", "/oauth/finish", { state, code });
  }
}

export class RepositoriesGroup {
  constructor(private readonly transport: Transport) {}

  /** Everything removed plugins left kept: each plugin's keys while it isn't installed again (no `repository`),
   * and each private repository's token nothing needs any more (no `plugin`). */
  keptKeys(): Promise<KeptKeys[]> {
    return this.transport.request("GET", "/plugins/keys");
  }

  /** Delete what a removed plugin left kept: its keys, its private repository's token. */
  async forgetKeys(kept: KeptKeys): Promise<void> {
    await this.transport.request("POST", "/plugins/keys/forget", kept);
  }

  /** The repositories plugins are listed from: the official extras first, then the ones the user added. */
  list(): Promise<Repository[]> {
    return this.transport.request("GET", "/repositories");
  }

  /** Lists a repository's plugins too; `token` reads a private one. Fails when it's listed already, can't be read, or offers none. */
  add(url: string, token = ""): Promise<Repository> {
    return this.transport.request("POST", "/repositories", token ? { url, token } : { url });
  }

  /** Stops listing it; what was installed from it stays. The extras can't be removed. */
  async remove(url: string): Promise<void> {
    await this.transport.request("POST", "/repositories/remove", { url });
  }

  /** What every listed repository offers, each plugin saying whether it's installed; one that can't be read has an error.
   * `cached`: as each one offered it when last read, at once, reaching only those never read. */
  plugins(cached = false): Promise<RepositoryPlugins[]> {
    return this.transport.request("GET", cached ? "/repositories/plugins?cached=true" : "/repositories/plugins");
  }

  /** The plugins (MCP servers and skills) a repository offers, the assistant's extras when no url is given. */
  browse(url?: string): Promise<RepositoryContents> {
    return this.transport.request("POST", "/repositories/browse", url ? { url } : {});
  }

  /** Installs from a repository, the assistant's extras when no url is given. Servers carry the values for their fields; secret ones go straight to the daemon. */
  install(skills: string[], servers: ServerValues[], url?: string): Promise<InstalledFromRepository> {
    return this.transport.request("POST", "/repositories/install", url ? { skills, servers, url } : { skills, servers });
  }

  /** Installed plugins the extras have a newer version of, as of the daemon's last check. Empty while checks are off. */
  updates(): Promise<PluginUpdate[]> {
    return this.transport.request("GET", "/repositories/updates");
  }

  /** Whether the daemon checks the extras for plugin updates in the background. */
  updateChecks(): Promise<PluginUpdateChecks> {
    return this.transport.request("GET", "/settings/plugin-updates");
  }

  setUpdateChecks(enabled: boolean): Promise<PluginUpdateChecks> {
    return this.transport.request("PUT", "/settings/plugin-updates", { enabled });
  }
}

export class McpGroup {
  constructor(private readonly transport: Transport) {}

  /** Install the server again from its repository, keeping the values and choices made here. */
  updateFromRepository(name: string): Promise<McpServerStatus> {
    return this.transport.request("POST", `/mcp/servers/${encodeURIComponent(name)}/update`);
  }

  servers(): Promise<McpServerStatus[]> {
    return this.transport.request("GET", "/mcp/servers");
  }

  /** Connects once and lists the server's tools, or says it asks to sign in, without saving it.
   * Throws ApiError (400) when it fails. */
  probe(settings: McpServerSettings): Promise<McpProbe> {
    return this.transport.request("POST", "/mcp/probe", settings);
  }

  /** A remote server's sign-in page; the browser comes back to `redirectUri`, the /oauth page.
   * Throws ApiError (400) when the server doesn't ask to sign in or can't be reached. */
  async startSignIn(name: string, redirectUri: string): Promise<string> {
    const path = `/mcp/servers/${encodeURIComponent(name)}/sign-in`;
    return (await this.transport.request<{ url: string }>("POST", path, { redirect_uri: redirectUri })).url;
  }

  /** The provider's sign-in page for a plugin that signs in with the user's own OAuth app (`oauth` in its
   * FoundServer); the browser comes back to `redirect_uri`, the /oauth page. An empty client ID signs in again with
   * the app it signed in with. Throws ApiError (400) when it doesn't sign in or there's no client ID. */
  async startPluginSignIn(name: string, body: PluginSignInStart): Promise<string> {
    const path = `/plugins/${encodeURIComponent(name)}/sign-in`;
    return (await this.transport.request<{ url: string }>("POST", path, body)).url;
  }

  /** An installed plugin's fields with their values; a secret one only says whether it's set. Throws ApiError (400)
   * for a server added by hand. */
  pluginSettings(name: string): Promise<PluginSettings> {
    return this.transport.request("GET", `/plugins/${encodeURIComponent(name)}/settings`);
  }

  /** New values for its fields: one left out keeps its value, and so does a secret one given empty unless it's in
   * `clear`. Its check runs first: throws ApiError (400) with what it says when it refuses them, saving nothing. */
  changePluginSettings(name: string, change: PluginSettingsChange): Promise<PluginSettings> {
    return this.transport.request("PUT", `/plugins/${encodeURIComponent(name)}/settings`, change);
  }

  /** Forgets the plugin's sign-in. */
  signOutPlugin(name: string): Promise<McpServerStatus> {
    return this.transport.request("DELETE", `/plugins/${encodeURIComponent(name)}/sign-in`);
  }

  /** Throws ApiError (400) for invalid settings or a name in use. */
  add(settings: McpServerSettings): Promise<McpServerStatus> {
    return this.transport.request("POST", "/mcp/servers", settings);
  }

  /** Fields left out keep their value. */
  change(name: string, change: McpServerChange): Promise<McpServerStatus> {
    return this.transport.request("PATCH", `/mcp/servers/${encodeURIComponent(name)}`, change);
  }

  /** Its data stays, for installing it again, unless `deleteData`. */
  /** Its data stays unless `deleteData`; what it left kept (its keys) comes back, to ask whether to keep it. */
  async remove(name: string, deleteData = false): Promise<KeptKeys | null> {
    const query = deleteData ? "?delete_data=true" : "";
    const removed: Removed = await this.transport.request("DELETE", `/mcp/servers/${encodeURIComponent(name)}${query}`);
    return removed.kept ?? null;
  }
}

/** MCP servers and skills that keep failing, listed until dismissed or working again, and the health check's new or
 * growing causes, until dismissed. */
export class AlertsGroup {
  constructor(private readonly transport: Transport) {}

  list(): Promise<Alert[]> {
    return this.transport.request("GET", "/alerts");
  }

  async dismiss(area: Alert["area"], name: string): Promise<void> {
    await this.transport.request("POST", `/alerts/${area}/${encodeURIComponent(name)}/dismiss`);
  }
}

/** The daemon's health checks (core/doctor/): the latest report, checking today now, and known noise. */
export class DoctorGroup {
  constructor(private readonly transport: Transport) {}

  get(): Promise<DoctorPage> {
    return this.transport.request("GET", "/doctor");
  }

  /** Checks today so far in the background; its report comes with a `doctor` event. */
  check(): Promise<DoctorPage> {
    return this.transport.request("POST", "/doctor/check");
  }

  /** The cause is noise: left out from now on. Throws ApiError (404) for one the latest check didn't find. */
  markKnown(causeId: string): Promise<DoctorPage> {
    return this.transport.request("PUT", `/doctor/known/${encodeURIComponent(causeId)}`);
  }

  /** The cause shows again from the next check. */
  forgetKnown(causeId: string): Promise<DoctorPage> {
    return this.transport.request("DELETE", `/doctor/known/${encodeURIComponent(causeId)}`);
  }
}

/** The notifications feed: job results and background work that ended, newest first (core/notifications.py). */
export class NotificationsGroup {
  constructor(private readonly transport: Transport) {}

  /** The `page` of them, or all. */
  list(page?: Page): Promise<Notification[]> {
    return this.transport.request("GET", `/notifications${pageQuery(page)}`);
  }

  async markRead(): Promise<void> {
    await this.transport.request("POST", "/notifications/read");
  }

  async dismiss(id: string): Promise<void> {
    await this.transport.request("DELETE", `/notifications/${encodeURIComponent(id)}`);
  }

  async clear(): Promise<void> {
    await this.transport.request("DELETE", "/notifications");
  }
}

/** Home: its sections with their last results, built by the assistant from the plugins (core/home/). */
export class HomeGroup {
  constructor(private readonly transport: Transport) {}

  get(): Promise<HomePage> {
    return this.transport.request("GET", "/home");
  }

  /** Builds the sections again in the background; unforced, nothing happens while the last refresh is under ten
   * minutes old. Each section's result is announced as a `home` event. */
  refresh(force = false): Promise<HomePage> {
    return this.transport.request("POST", "/home/refresh", { force });
  }

  /** This tab shows Home: the daemon refreshes it now and then until `unwatch`, or until this tab's event stream
   * closes. */
  async watch(): Promise<void> {
    await this.transport.request("PUT", "/home/watch");
  }

  async unwatch(): Promise<void> {
    await this.transport.request("DELETE", "/home/watch");
  }

  /** New and changed sections are built in the background. Throws ApiError (400) for sections that can't be saved. */
  saveSections(sections: HomeSection[]): Promise<HomePage> {
    return this.transport.request("PUT", "/home/sections", { sections });
  }

  /** Back to the built-in sections. */
  resetSections(): Promise<HomePage> {
    return this.transport.request("DELETE", "/home/sections");
  }

  /** The conversations pinned to Home, which its Conversations card shows, the first pinned first. */
  async pins(): Promise<string[]> {
    return (await this.transport.request<Schemas["HomePins"]>("GET", "/home/pins")).threads;
  }

  /** Pins it after the others. Throws ApiError: 404 for no such conversation, 400 for the inbox. */
  async pin(threadId: string): Promise<string[]> {
    return (await this.transport.request<Schemas["HomePins"]>("PUT", `/home/pins/${encodeURIComponent(threadId)}`)).threads;
  }

  async unpin(threadId: string): Promise<string[]> {
    return (await this.transport.request<Schemas["HomePins"]>("DELETE", `/home/pins/${encodeURIComponent(threadId)}`)).threads;
  }
}

/** Coding agents' tasks running in the background, with their latest steps. */
export class TasksGroup {
  constructor(private readonly transport: Transport) {}

  running(): Promise<RunningTask[]> {
    return this.transport.request("GET", "/agent-tasks/running");
  }
}

export class RunsGroup {
  constructor(private readonly transport: Transport) {}

  /** Replies in progress in any conversation; `run` and `run_finished` events tell when this changes. */
  inProgress(): Promise<RunInProgress[]> {
    return this.transport.request("GET", "/runs");
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

  /** Saved skills only: a built-in one is refused. */
  update(name: string, description: string, instructions: string): Promise<Skill> {
    return this.transport.request("PUT", `/skills/${encodeURIComponent(name)}`, { description, instructions });
  }

  /** What it left kept (its private repository's token) comes back, to ask whether to keep it. */
  async delete(name: string): Promise<KeptKeys | null> {
    const removed: Removed = await this.transport.request("DELETE", `/skills/${encodeURIComponent(name)}`);
    return removed.kept ?? null;
  }

  /** Install the skill again from its repository, replacing changes made here. */
  updateInstalled(name: string): Promise<Skill> {
    return this.transport.request("POST", `/skills/${encodeURIComponent(name)}/update`);
  }

  /** Claude Code's and Codex's skills on the daemon's computer, each with whether it was imported or changed since. */
  importable(): Promise<Importables> {
    return this.transport.request("GET", "/skill-imports");
  }

  /** Import the skills picked by id, updating those imported before; each outcome says how it went. */
  importSkills(ids: string[], replace = false): Promise<ImportOutcome[]> {
    return this.transport.request("POST", "/skill-imports", { ids, replace });
  }
}

export class MemoryGroup {
  constructor(private readonly transport: Transport) {}

  /** What the assistant knows about the user: profile sections, facts and recent conversations. */
  snapshot(): Promise<MemorySnapshot> {
    return this.transport.request("GET", "/memory");
  }

  /** Replaces one profile section with the user's own list (at most 8 items). */
  setProfileSection(section: string, items: string[]): Promise<MemorySnapshot> {
    return this.transport.request("PUT", `/memory/profile/${encodeURIComponent(section)}`, { items });
  }

  /** Every saved fact, newest first. */
  facts(): Promise<Fact[]> {
    return this.transport.request("GET", "/memory/facts");
  }

  /** It gets a new id. Throws ApiError: 404 when it's gone, 400 for empty text. */
  editFact(id: string, text: string): Promise<Fact> {
    return this.transport.request("PUT", `/memory/facts/${encodeURIComponent(id)}`, { text });
  }

  async deleteFact(id: string): Promise<void> {
    await this.transport.request("DELETE", `/memory/facts/${encodeURIComponent(id)}`);
  }

  /** Every summary of a past conversation, newest first. */
  episodes(): Promise<Episode[]> {
    return this.transport.request("GET", "/memory/episodes");
  }

  /** It gets a new id. Throws ApiError: 404 when it's gone, 400 for empty text. */
  editEpisode(id: string, text: string): Promise<Episode> {
    return this.transport.request("PUT", `/memory/episodes/${encodeURIComponent(id)}`, { text });
  }

  async deleteEpisode(id: string): Promise<void> {
    await this.transport.request("DELETE", `/memory/episodes/${encodeURIComponent(id)}`);
  }
}

export class UsageGroup {
  constructor(private readonly transport: Transport) {}

  report(days: number): Promise<UsageReport> {
    return this.transport.request("GET", `/usage?days=${days}`);
  }

  /** Tokens and cost of the model calls, grouped every way the report offers. */
  tokens(days: number): Promise<TokenReport> {
    return this.transport.request("GET", `/usage/tokens?days=${days}`);
  }
}

export class SystemGroup {
  constructor(private readonly transport: Transport) {}

  host(): Promise<HostStatus> {
    return this.transport.request("GET", "/system/host");
  }

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

  /** Installs an out-of-date start at boot again (`outdated`), behind macOS's password dialog; a daemon it started
   * restarts once no run is in progress. */
  reinstallStartup(): Promise<StartupStatus> {
    return this.transport.request("POST", "/system/startup/reinstall");
  }

  /** The daemon restarts once no run is in progress. */
  restart(): Promise<ShutdownStatus> {
    return this.transport.request("POST", "/system/restart");
  }

  /** The daemon stops once no run is in progress. Throws ApiError (409) when its service manager would
   * start it again. */
  stop(): Promise<ShutdownStatus> {
    return this.transport.request("POST", "/system/stop");
  }

  /** The restart or stop waiting for runs to end; `ending` is "" when none is. */
  ending(): Promise<PendingEnding> {
    return this.transport.request("GET", "/system/ending");
  }

  /** The daemon keeps running. Throws ApiError (409) when nothing waits, or it already went ahead. */
  takeBackEnding(): Promise<PendingEnding> {
    return this.transport.request("DELETE", "/system/ending");
  }

  /** Cancels the runs the restart or stop waits for, so it goes ahead; returns how many. Throws ApiError (409)
   * when nothing waits. */
  async endNow(): Promise<number> {
    const cancelled: Schemas["CancelledRuns"] = await this.transport.request("POST", "/system/ending/now");
    return cancelled.cancelled;
  }

  /** The version the daemon runs and, as of the last check, what's new (src/assistant/daemon/updates.py). */
  updateStatus(): Promise<UpdateStatus> {
    return this.transport.request("GET", "/system/update");
  }

  /** Reaches the repository to see what's new. */
  checkForUpdate(): Promise<UpdateStatus> {
    return this.transport.request("POST", "/system/update/check");
  }

  /** Starts installing what's new; the daemon restarts once it's installed. Throws ApiError (409) when there's
   * nothing to install or it can't be installed there, saying why. */
  update(): Promise<UpdateStatus> {
    return this.transport.request("POST", "/system/update");
  }
}

export class LanguageGroup {
  constructor(private readonly transport: Transport) {}

  /** The language of the apps' own text: auto follows this browser's. */
  get(): Promise<LanguageSetting> {
    return this.transport.request("GET", "/settings/language");
  }

  /** Throws ApiError (400) for an unknown language. */
  set(language: LanguageSetting["language"]): Promise<LanguageSetting> {
    return this.transport.request("PUT", "/settings/language", { language });
  }
}

export class LogsGroup {
  constructor(
    private readonly transport: Transport,
    private readonly following: LogStreams,
  ) {}

  /** The log files (the process output too), levels and components to pick from. */
  options(): Promise<LogOptions> {
    return this.transport.request("GET", "/logs");
  }

  /** The lowest level the daemon records. */
  level(): Promise<LogLevelSetting> {
    return this.transport.request("GET", "/settings/log-level");
  }

  /** Applied at once. Throws ApiError (400) for an unknown level. */
  setLevel(level: string): Promise<LogLevelSetting> {
    return this.transport.request("PUT", "/settings/log-level", { level });
  }

  /** The latest matching entries, oldest first. Throws ApiError (400) for an unknown component, 404 for an unknown file. */
  page(name: string, query: LogQuery): Promise<LogPage> {
    return this.transport.request("GET", `${logPath(name)}?${logParams(query)}`);
  }

  /** A page, then each new matching entry, until `signal` aborts; after the event stream opens again, a new page.
   * They come down the event stream (`DaemonClient.events`), which must be read for them to come. */
  follow(name: string, query: LogQuery, signal: AbortSignal): AsyncGenerator<LogEvent> {
    return this.following.follow(name, query, signal);
  }
}

function logPath(name: string): string {
  return `/logs/${encodeURIComponent(name)}`;
}

function pageQuery(page: Page | undefined, params: Record<string, string> = {}): string {
  const query = new URLSearchParams(params);
  if (page) {
    query.set("offset", String(page.offset));
    query.set("limit", String(page.limit));
  }
  return query.size ? `?${query}` : "";
}

function logParams(query: LogQuery): string {
  const params = new URLSearchParams({ lines: String(query.lines) });
  if (query.level) params.set("level", query.level);
  if (query.component) params.set("component", query.component);
  return params.toString();
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
  readonly files: FilesGroup;
  readonly folders: FoldersGroup;
  readonly identity: IdentityGroup;
  readonly jobs: JobsGroup;
  readonly channels: ChannelsGroup;
  readonly speech: SpeechGroup;
  readonly webSearch: WebSearchGroup;
  readonly email: EmailGroup;
  readonly oauth: OAuthGroup;
  readonly model: ModelGroup;
  readonly prompts: PromptsGroup;
  readonly mcp: McpGroup;
  readonly alerts: AlertsGroup;
  readonly doctor: DoctorGroup;
  readonly notifications: NotificationsGroup;
  readonly home: HomeGroup;
  readonly tasks: TasksGroup;
  readonly runs: RunsGroup;
  readonly repositories: RepositoriesGroup;
  readonly skills: SkillsGroup;
  readonly memory: MemoryGroup;
  readonly usage: UsageGroup;
  readonly system: SystemGroup;
  readonly clients: ClientsGroup;
  readonly auth: AuthGroup;
  readonly devices: DevicesGroup;
  readonly logs: LogsGroup;
  readonly language: LanguageGroup;

  /** The runs and logs this client follows, over the event stream `transport` reads: a tab's other clients
   * (partClientId) share its own's, since only it reads a stream. */
  constructor(
    private readonly transport: Transport,
    readonly following: RunStreams = new RunStreams(transport),
    readonly followingLogs: LogStreams = new LogStreams(transport),
  ) {
    this.conversations = new ConversationsGroup(transport);
    this.files = new FilesGroup(transport);
    this.folders = new FoldersGroup(transport);
    this.identity = new IdentityGroup(transport);
    this.jobs = new JobsGroup(transport);
    this.channels = new ChannelsGroup(transport);
    this.speech = new SpeechGroup(transport);
    this.webSearch = new WebSearchGroup(transport);
    this.email = new EmailGroup(transport);
    this.oauth = new OAuthGroup(transport);
    this.model = new ModelGroup(transport);
    this.prompts = new PromptsGroup(transport);
    this.mcp = new McpGroup(transport);
    this.alerts = new AlertsGroup(transport);
    this.doctor = new DoctorGroup(transport);
    this.notifications = new NotificationsGroup(transport);
    this.home = new HomeGroup(transport);
    this.tasks = new TasksGroup(transport);
    this.runs = new RunsGroup(transport);
    this.repositories = new RepositoriesGroup(transport);
    this.skills = new SkillsGroup(transport);
    this.memory = new MemoryGroup(transport);
    this.usage = new UsageGroup(transport);
    this.system = new SystemGroup(transport);
    this.clients = new ClientsGroup(transport);
    this.auth = new AuthGroup(transport);
    this.devices = new DevicesGroup(transport);
    this.logs = new LogsGroup(transport, followingLogs);
    this.language = new LanguageGroup(transport);
  }

  /** How the daemon names this client in the runs it announces. */
  get clientId(): string {
    return this.transport.clientId;
  }

  /** Move this client to the inbox, which routes each message to its conversation, and return its id. */
  async inboxThread(): Promise<string> {
    return (await this.transport.request<Schemas["ThreadCreated"]>("POST", "/threads/inbox")).thread_id;
  }

  /** Move this client to a new conversation. */
  async newThread(): Promise<string> {
    return (await this.transport.request<Schemas["ThreadCreated"]>("POST", "/threads")).thread_id;
  }

  /** Move this client to an earlier conversation. Throws ApiError (404) for one that has no messages. */
  async resumeThread(threadId: string): Promise<void> {
    await this.transport.request("POST", `/conversations/${encodeURIComponent(threadId)}/resume`);
  }

  /** Close this client's conversation without moving to another, as when it's closed in the sidebar. */
  async leaveThread(): Promise<void> {
    await this.transport.request("POST", "/threads/leave");
  }

  async *send(session: Session, text: string, files: File[], signal: AbortSignal): AsyncGenerator<RunEvent> {
    const form = new FormData();
    form.append("channel", session.channel);
    form.append("text", text);
    files.forEach((file) => form.append("files", file, file.name));
    const run = await this.transport.request<Schemas["RunStarted"]>("POST", `${thread(session)}/messages`, form);
    yield* this.followRun(run.run_id, signal);
  }

  /** Sends a message the inbox sent on (a Dispatched event) in `session`'s conversation, as it was written. Its
   * text, and for a coding task its agent, are announced with the run, so other clients show it. */
  async *sendDispatched(session: Session, dispatched: Dispatched, signal: AbortSignal): AsyncGenerator<RunEvent> {
    const body = { channel: session.channel, text: dispatched.text, brief: dispatched.brief ?? "" };
    const run = await this.transport.request<Schemas["RunStarted"]>(
      "POST",
      `${thread(session)}/dispatched/${encodeURIComponent(dispatched.id)}`,
      body,
    );
    yield* this.followRun(run.run_id, signal);
  }

  /** Asks in the inbox (`session`) where a message it sent on goes instead, the last one when `dispatchId` is empty;
   * a Dispatched event says where it went. */
  async *moveDispatched(session: Session, dispatchId: string, signal: AbortSignal): AsyncGenerator<RunEvent> {
    const body = { channel: session.channel, id: dispatchId };
    const run = await this.transport.request<Schemas["RunStarted"]>("POST", `${thread(session)}/moves`, body);
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

  /** A run's events from its first, over the event stream (`events`), which must be read for them to come. */
  async *followRun(runId: string, signal: AbortSignal): AsyncGenerator<RunEvent> {
    for await (const batch of this.followRunBatches(runId, signal)) yield* batch;
  }

  /** `followRun`'s events in the batches they arrived in: following a run from its start, its past events come at
   * once, and the chat applies them in one go instead of updating the page for each. */
  followRunBatches(runId: string, signal: AbortSignal): AsyncGenerator<RunEvent[]> {
    return this.following.follow(runId, signal);
  }

  /** Daemon events from now on, for as long as `signal` isn't aborted, resuming after a daemon restart.
   * `onOpen` is called each time the stream opens, after a restart too. The events of the runs and logs this client
   * follows come down it as well, and go to them (`following`, `followingLogs`) instead. */
  async *events(signal: AbortSignal, onOpen?: () => void, onLost?: () => void): AsyncGenerator<BusEvent> {
    const opened = () => {
      onOpen?.();
      this.following.reopened();
      this.followingLogs.reopened();
    };
    for await (const event of resumableEvents(this.transport, "/events", BUS_RECONNECT, signal, "", opened, onLost)) {
      const data = JSON.parse(event.data) as Record<string, unknown>;
      if (this.following.receive(event.event, data) || this.followingLogs.receive(event.event, data)) continue;
      yield { kind: event.event, data };
    }
  }
}

function thread(session: Session): string {
  return `/threads/${encodeURIComponent(session.thread_id)}`;
}
