<!-- Chat's views as the conversations page switches them (conversationLayout.svelte.test.ts): the cards view gives
full screen back as it goes, as ConversationBoard does. -->
<script lang="ts">
  import { conversationLayout } from "./conversationLayout.svelte";

  const view = $derived(conversationLayout.current.view);
  const givesBack = () => () => conversationLayout.restore();
</script>

<button onclick={() => conversationLayout.change({ ...conversationLayout.current, view: "list" })}>List</button>
{#if view === "cards"}
  <p {@attach givesBack}>cards</p>
{:else}
  <p>list</p>
{/if}
