<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import List from "@lucide/svelte/icons/list";
  import Plus from "@lucide/svelte/icons/plus";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import ChatPanel from "$lib/ui/chat/ChatPanel.svelte";
  import OpenSwitcher from "$lib/ui/chat/OpenSwitcher.svelte";
  import { homePins } from "$lib/ui/homePins.svelte";
  import { leaveInbox } from "$lib/ui/openConversation";
  import PinToHome from "$lib/ui/PinToHome.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { chats } = useDaemon();
  // The conversation shown; the others open beside it are in the sidebar, every one in Chat's list.
  const snapshot = external(chats.subscribe, () => chats.current?.getSnapshot() ?? null);
  // Chat never shows the inbox: should it come to it all the same, or with none open, the page gives way to the list.
  const shown = $derived(snapshot.current !== null && snapshot.current.threadId !== snapshot.current.inboxId);
  $effect(() => void leaveInbox(snapshot.current));
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  const listed = $derived(conversations.data?.find((c) => c.thread_id === snapshot.current?.threadId));
  const title = $derived(listed?.title || t("nav.newConversation"));
  // Pinned to Home, once it's listed: a new conversation is, from its first message.
  const pins = homePins();

  async function startNew(): Promise<void> {
    await chats.startNew();
  }
</script>

{#if shown}
  <TopBar {title}>
    {#snippet actions()}
      {#if listed && !listed.inbox}<PinToHome pinned={pins.has(listed.thread_id)} ontoggle={() => pins.toggle(listed.thread_id)} />{/if}
      <OpenSwitcher />
      <button class="btn btn--ghost" title={t("conversations.allHint")} onclick={() => goto(resolve("/conversations"))}
        ><List size={16} /><span class="hide-narrow">{t("conversations.all")}</span></button
      >
      <button class="btn btn--primary" onclick={startNew}
        ><Plus size={16} /><span class="hide-narrow">{t("nav.newConversation")}</span></button
      >
    {/snippet}
  </TopBar>

  <div class="screen"><ChatPanel /></div>
{/if}

<style>
  .screen {
    padding: 0 16px 8px;
    height: calc(100dvh - var(--top-bar-height));
    max-width: 1600px;
    margin: 0 auto;
  }
  @media (max-width: 680px) {
    .screen {
      padding: 0 8px 8px;
    }
  }
</style>
