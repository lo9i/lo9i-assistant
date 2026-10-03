<script lang="ts">
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import { GET_TO_KNOW_ME } from "$lib/chat/commands";
  import { useDaemon } from "$lib/daemon.svelte";
  import SettingsCard from "../Card.svelte";

  const { chat } = useDaemon();

  // Starts in this tab's conversation, like /get-to-know-me in the chat.
  async function start(): Promise<void> {
    void chat.send(GET_TO_KNOW_ME, []);
    await goto(resolve("/conversations/open"));
  }
</script>

<SettingsCard id="get-to-know-you" title="Get to know you" sub="A few questions, and a look at your public profiles if you like, so replies fit you.">
  <p class="text-meta">Every question can be skipped. Found on the web, nothing is saved until you confirm it. What it learns shows in About you.</p>
  <div>
    <button class="btn btn--primary" onclick={start}>Start</button>
  </div>
</SettingsCard>

<style>
  p {
    margin: 0;
  }
</style>
