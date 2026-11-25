"""The backup models from any client (core/llm/backups.py): listed, added once they answer, removed and put in the
order they're tried. Secret values never leave the daemon: clients only learn which are set, and whether a backup
uses the main model's values."""

from dataclasses import dataclass

from lo9i.core.agent.base import ServiceBase
from lo9i.core.agent.model import ModelSettingsError, check_answers, check_fields, ensure_package
from lo9i.core.i18n import said
from lo9i.core.llm import backups
from lo9i.core.llm.backups import Backup
from lo9i.core.llm.choice import ModelChoice, secret_keys
from lo9i.core.llm.providers import provider
from lo9i.core.usage.meter import TokenMeter

__all__ = ["BackupModelStatus", "BackupModelsMixin"]


@dataclass
class BackupModelStatus:
    id: str
    provider: str
    model: str
    # The values that aren't secret, like a server URL.
    values: dict[str, str]
    # The secret values it has of its own, by key.
    secrets_set: list[str]
    # On the main model's provider, it takes the main model's values where it has none of its own.
    uses_main_values: bool


class BackupModelsMixin(ServiceBase):
    async def backup_models(self) -> list[BackupModelStatus]:
        """In the order they're tried."""
        return [self._backup_status(b) for b in await backups.load(self._storage.store, self.secrets)]

    async def add_backup_model(self, provider_id: str, values: dict[str, str], model: str) -> list[BackupModelStatus]:
        """Checks that it answers, then adds it last. On the main model's provider, fields left empty take the main
        model's values. Raises ModelSettingsError."""
        known = provider(provider_id)
        if known is None:
            raise ModelSettingsError(said("Unknown provider {provider_id}.", provider_id=provider_id))
        if not model.strip():
            raise ModelSettingsError(said("Pick a model for the backup."))
        given = {k: v.strip() for k, v in values.items() if k in {f.key for f in known.fields} and v.strip()}
        backup = Backup(backups.new_id(), known.id, model.strip(), given)
        checked = backup.choice(self._model)
        check_fields(known, checked)
        await ensure_package(known)
        await check_answers(checked, [backup.model], TokenMeter(self._storage.usage, "check"))
        saved = await backups.load(self._storage.store, self.secrets)
        await backups.save(self._storage.store, self.secrets, [*saved, backup])
        return await self.backup_models()

    async def remove_backup_model(self, backup_id: str) -> list[BackupModelStatus]:
        saved = await backups.load(self._storage.store, self.secrets)
        await backups.save(self._storage.store, self.secrets, [b for b in saved if b.id != backup_id])
        return await self.backup_models()

    async def order_backup_models(self, ids: list[str]) -> list[BackupModelStatus]:
        """Puts the backups in this order; those not named keep theirs after them. Raises ModelSettingsError for an
        id that isn't a backup."""
        saved = {b.id: b for b in await backups.load(self._storage.store, self.secrets)}
        unknown = next((i for i in ids if i not in saved), None)
        if unknown is not None:
            raise ModelSettingsError(said("No backup model {backup_id}.", backup_id=unknown))
        named = list(dict.fromkeys(ids))
        ordered = [saved[i] for i in named] + [b for i, b in saved.items() if i not in named]
        await backups.save(self._storage.store, self.secrets, ordered)
        return await self.backup_models()

    def _backup_status(self, backup: Backup) -> BackupModelStatus:
        secret = secret_keys(ModelChoice(backup.provider, backup.model, backup.model))
        return BackupModelStatus(
            id=backup.id,
            provider=backup.provider,
            model=backup.model,
            values={k: v for k, v in backup.values.items() if k not in secret},
            secrets_set=sorted(k for k, v in backup.values.items() if k in secret and v),
            uses_main_values=backup.provider == self._model.provider,
        )
