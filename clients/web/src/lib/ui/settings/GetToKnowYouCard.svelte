<script lang="ts">
  import { startGetToKnowYou } from "$lib/chat/getToKnowYou";
  import { useDaemon } from "$lib/daemon.svelte";
  import SettingsCard from "../Card.svelte";

  const { chat } = useDaemon();
</script>

<SettingsCard id="get-to-know-you" title="Get to know you" sub="A few questions, and a look at your public profiles if you like, so replies fit you.">
  <p class="text-meta">Every question can be skipped. Found on the web, nothing is saved until you confirm it. What it learns shows on this page.</p>
  <div>
    <button class="btn btn--primary" onclick={() => startGetToKnowYou(chat)}>Start</button>
  </div>
</SettingsCard>

<style>
  p {
    margin: 0;
  }
</style>
