<script lang="ts">
  import type { FoundServer } from "$lib/api/types";
  import { resource } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import ChannelSetup from "./ChannelSetup.svelte";
  import EmailAccounts from "./EmailAccounts.svelte";
  import PluginSignIn from "./PluginSignIn.svelte";

  // An installed plugin's setup: an email plugin's accounts, a chat channel's items, signing in with the user's own
  // OAuth app. In its details on
  // the Plugins page, and in the conversation when the agent opens it (open_plugin_setup) or right after
  // installing it from there.
  let { server }: { server: FoundServer } = $props();
  const channels = resource((c) => c.channels.list(), ["channels"]);
  const channel = $derived(server.channel ? channels.data?.find((c) => c.name === server.name) : undefined);
</script>

{#if channel}
  <ChannelSetup {channel} />
{:else if server.channel}
  <p class="text-meta">{t("pluginSetup.starting", { name: server.name })}</p>
{/if}
{#if server.email}<EmailAccounts plugin={server.name} title={t("email.accounts")} />{/if}
{#if server.oauth}<PluginSignIn plugin={server.name} provider={server.oauth} />{/if}
