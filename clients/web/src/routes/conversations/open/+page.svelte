<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import Columns2 from "@lucide/svelte/icons/columns-2";
  import List from "@lucide/svelte/icons/list";
  import Rows2 from "@lucide/svelte/icons/rows-2";
  import Plus from "@lucide/svelte/icons/plus";
  import { besideOf, columnsOf, rearranged } from "$lib/chat/cardLayout";
  import { conversationLayout } from "$lib/conversationLayout.svelte";
  import { external, resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import BesidePicker from "$lib/ui/chat/BesidePicker.svelte";
  import Columns from "$lib/ui/chat/board/Columns.svelte";
  import OpenSwitcher from "$lib/ui/chat/OpenSwitcher.svelte";
  import { homePins } from "$lib/ui/homePins.svelte";
  import { leaveInbox, startNewHere } from "$lib/ui/openConversation";
  import PinToHome from "$lib/ui/PinToHome.svelte";
  import TopBar from "$lib/ui/TopBar.svelte";

  const { chats, notices } = useDaemon();
  // The conversation shown, with any beside it as columns; the others open are in the sidebar, every one in Chat's
  // list.
  const snapshot = external(chats.subscribe, () => chats.current?.getSnapshot() ?? null);
  // Chat never shows the inbox: should it come to it all the same, or with none open, the page gives way to the list.
  const shown = $derived(snapshot.current !== null && snapshot.current.threadId !== snapshot.current.inboxId);
  $effect(() => void leaveInbox(snapshot.current));
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  const listed = $derived(conversations.data?.find((c) => c.thread_id === snapshot.current?.threadId));
  // The conversations shown as columns: the one shown, and those beside it.
  const columns = $derived(snapshot.current ? columnsOf(conversationLayout.current, snapshot.current.threadId) : []);
  // Several shown, the page is named after none of them: each column has its own title.
  const title = $derived(columns.length > 1 ? t("board.showing", { count: columns.length }) : listed?.title || t("nav.newConversation"));
  // Pinned to Home, once it's listed: a new conversation is, from its first message.
  const pins = homePins();
  const stacked = $derived(conversationLayout.current.arrange === "stacked");
  let picking = $state(false);

  // A new conversation joins the ones shown together.
  async function startNew(): Promise<void> {
    await startNewHere(chats, conversationLayout);
  }

  /** The conversation picked opens beside the one shown, which stays shown. */
  async function openBeside(threadId: string | null): Promise<void> {
    picking = false;
    const anchor = snapshot.current?.threadId;
    if (threadId === null || anchor === undefined) return;
    try {
      if (!(await chats.opened(threadId))) return notices.notify(t("controller.deleted"), "warning");
      conversationLayout.change(besideOf(conversationLayout.current, anchor, threadId));
    } catch (e) {
      notices.report(e);
    }
  }
</script>

{#if shown}
  <TopBar {title}>
    {#snippet actions()}
      <!-- With several shown, each column has its own Pin to Home. -->
      {#if columns.length < 2 && listed && !listed.inbox}<PinToHome
          pinned={pins.has(listed.thread_id)}
          ontoggle={() => pins.toggle(listed.thread_id)}
        />{/if}
      {#if columns.length > 1}
        <!-- Shows the arrangement it switches to. -->
        <button
          class="btn btn--ghost"
          title={stacked ? t("board.sideBySideHint") : t("board.stackHint")}
          onclick={() => conversationLayout.change(rearranged(conversationLayout.current))}
          >{#if stacked}<Columns2 size={16} />{:else}<Rows2 size={16} />{/if}<span class="hide-narrow"
            >{stacked ? t("board.sideBySide") : t("board.stack")}</span
          ></button
        >
      {/if}
      <button class="btn btn--ghost" title={t("board.openBesideHint")} onclick={() => (picking = true)}
        ><Columns2 size={16} /><span class="hide-narrow">{t("board.openBeside")}</span></button
      >
      <OpenSwitcher />
      <button class="btn btn--ghost" title={t("conversations.allHint")} onclick={() => goto(resolve("/conversations"))}
        ><List size={16} /><span class="hide-narrow">{t("conversations.all")}</span></button
      >
      <button class="btn btn--primary" onclick={startNew}
        ><Plus size={16} /><span class="hide-narrow">{t("nav.newConversation")}</span></button
      >
    {/snippet}
  </TopBar>

  <!-- Side by side the columns take the whole width; stacked, each reads at the page's usual width. -->
  <div class="screen" class:wide={columns.length > 1 && !stacked}><Columns /></div>
  {#if picking}<BesidePicker title={listed?.title || t("nav.newConversation")} shown={columns} onpick={openBeside} />{/if}
{/if}

<style>
  .screen {
    padding: 0 16px 8px;
    height: calc(100dvh - var(--top-bar-height));
    max-width: 1600px;
    margin: 0 auto;
  }
  /* Side by side, the columns take the whole width. */
  .screen.wide {
    max-width: none;
  }
  @media (max-width: 680px) {
    .screen {
      padding: 0 8px 8px;
    }
  }
</style>
