<script lang="ts">
  import SettingsCard from "../Card.svelte";
  import EmailRecipients from "../plugins/EmailRecipients.svelte";

  // What every email account shares, whichever plugin it belongs to.
</script>

<SettingsCard id="email" title="Email" sub="Who the assistant emails without asking, from any account.">
  <EmailRecipients />
</SettingsCard>
