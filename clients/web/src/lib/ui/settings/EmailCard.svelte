<script lang="ts">
  import { t } from "$lib/i18n.svelte";
  import SettingsCard from "../Card.svelte";
  import EmailRecipients from "../plugins/EmailRecipients.svelte";

  // What every email account shares, whichever plugin it belongs to.
</script>

<SettingsCard id="email" title={t("emailCard.title")} sub={t("emailCard.sub")}>
  <EmailRecipients />
</SettingsCard>
