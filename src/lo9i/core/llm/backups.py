"""Backup models: an ordered list the user picks in the app (Settings → Model, /model), tried in turn when a reply's
model fails on the provider's side (llm/errors.py::provider_failed: rate limits, quota, outages), never for what the
request asked. Each is a provider and a model; one on the main model's provider without values of its own uses the
main model's (its key), so a backup on the same account needs no key typed again.

The list is one Store record; its secrets are kept encrypted apart (core/secret_store.py), by backup id. The graph
reads it only when a call fails (`BackupModels`), so saving it needs no rebuild and costs nothing while the main
model answers."""

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from langchain_core.language_models import BaseChatModel
from langgraph.store.base import BaseStore

from lo9i.core import secret_store
from lo9i.core.llm import build_llm, metered
from lo9i.core.llm.choice import ModelChoice, secret_keys
from lo9i.core.secret_store import SecretBox, SecretError
from lo9i.core.usage.meter import TokenMeter

_NAMESPACE = ("settings",)
_KEY = "model:backups"
_SECRETS = "model:backups:secrets"


@dataclass(frozen=True)
class Backup:
    id: str
    provider: str
    model: str
    # The provider's fields, secret ones included; empty on the main model's provider uses the main model's.
    values: dict[str, str] = field(default_factory=dict)

    def choice(self, main: ModelChoice) -> ModelChoice:
        """The choice it's built from: its own values, over the main model's when on the same provider."""
        values = {**main.values, **self.values} if self.provider == main.provider else dict(self.values)
        return ModelChoice(self.provider, self.model, self.model, values)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


async def load(store: BaseStore, box: SecretBox) -> list[Backup]:
    """The backups in the order they're tried. Secrets that can't be read any more come back empty."""
    item = await store.aget(_NAMESPACE, _KEY)
    if item is None:
        return []
    hidden = await _secrets(store, box)
    return [
        Backup(b["id"], b["provider"], b["model"], {**b.get("values", {}), **hidden.get(b["id"], {})})
        for b in item.value.get("backups", [])
    ]


async def save(store: BaseStore, box: SecretBox, backups: Sequence[Backup]) -> None:
    records, hidden = [], {}
    for b in backups:
        secret = secret_keys(ModelChoice(b.provider, b.model, b.model))
        records.append(
            {
                "id": b.id,
                "provider": b.provider,
                "model": b.model,
                "values": {k: v for k, v in b.values.items() if k not in secret},
            }
        )
        if kept := {k: v for k, v in b.values.items() if k in secret and v}:
            hidden[b.id] = kept
    await store.aput(_NAMESPACE, _KEY, {"backups": records})
    await secret_store.put(store, box, _SECRETS, json.dumps(hidden))


async def _secrets(store: BaseStore, box: SecretBox) -> dict[str, dict[str, str]]:
    try:
        text = await secret_store.get(store, box, _SECRETS)
    except SecretError:
        return {}
    return json.loads(text) if text else {}


@dataclass(frozen=True)
class BackupModel:
    """A backup ready to answer: its name for the user, its provider (how it takes images, llm/providers.py) and the
    model, metered as the main one is."""

    name: str
    provider: str
    llm: BaseChatModel


class BackupModels:
    """The backups for a reply whose model failed, built from the saved list each time it's asked for and kept
    while that list stays the same."""

    def __init__(self, store: BaseStore, box: SecretBox, main: ModelChoice, meter: TokenMeter) -> None:
        self._store = store
        self._box = box
        self._main = main
        self._meter = meter
        self._built: dict[tuple, BackupModel] = {}

    async def after(self, model: str) -> list[BackupModel]:
        """The backups to try after `model` failed, in order, leaving out one that is that same model."""
        saved = await load(self._store, self._box)
        return [self._model(b) for b in saved if not (b.provider == self._main.provider and b.model == model)]

    def _model(self, backup: Backup) -> BackupModel:
        key = (backup.provider, backup.model, tuple(sorted(backup.values.items())))
        if key not in self._built:
            llm = metered(build_llm(backup.choice(self._main), backup.model), self._meter)
            self._built[key] = BackupModel(backup.model, backup.provider, llm)
        return self._built[key]
