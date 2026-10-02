"""Pure three-way merge of local records, remote records, and the last agreed base.

Rules, per uid:

* identical content on both sides            -> in sync
* only one side changed since the base       -> that side wins
* remote "changed" but is older than local   -> stale snapshot, keep local
* both changed, one of them is a deletion    -> the edit wins (no data loss)
* both edited                                -> policy picks a winner, and the
                                                loser is kept as a conflict copy
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from termvault.sync.constants import CONFLICT_COPY_SUFFIX, DEFAULT_POLICY
from termvault.sync.records import SyncRecord

IN_SYNC = "in_sync"
PUBLISH = "publish"
CREATE = "create"
UPDATE = "update"
DELETE = "delete"
TOMBSTONE = "tombstone"
CONFLICT = "conflict"

LOCAL_CHANGING_ACTIONS = frozenset({CREATE, UPDATE, DELETE, TOMBSTONE, CONFLICT})


@dataclass(frozen=True)
class MergeAction:
    uid: str
    action: str
    reason: str
    title: str = ""
    apply: SyncRecord | None = None
    copy: SyncRecord | None = None

    @property
    def changes_local(self) -> bool:
        return self.action in LOCAL_CHANGING_ACTIONS and (
            self.apply is not None or self.copy is not None
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "uid": self.uid,
            "action": self.action,
            "reason": self.reason,
            "title": self.title,
            "applies_remote": self.apply is not None,
            "conflict_copy": self.copy.title if self.copy is not None else None,
        }


@dataclass
class MergePlan:
    actions: list[MergeAction] = field(default_factory=list)
    policy: str = DEFAULT_POLICY

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(action.action for action in self.actions))

    @property
    def local_changes(self) -> list[MergeAction]:
        return [action for action in self.actions if action.changes_local]

    @property
    def conflicts(self) -> list[MergeAction]:
        return [action for action in self.actions if action.action == CONFLICT]

    @property
    def outgoing(self) -> list[MergeAction]:
        return [action for action in self.actions if action.action == PUBLISH]

    def to_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "counts": self.counts,
            "actions": [
                action.to_dict() for action in self.actions if action.action != IN_SYNC
            ],
        }


def _display_title(*records: SyncRecord | None) -> str:
    for record in records:
        if record is not None and not record.is_deleted and record.title:
            return record.title
    return "(deleted entry)"


def _remote_apply_action(local: SyncRecord | None, remote: SyncRecord) -> str:
    if remote.is_deleted:
        return DELETE if local is not None and not local.is_deleted else TOMBSTONE
    if local is None or local.is_deleted:
        return CREATE
    return UPDATE


def _pick_winner(local: SyncRecord, remote: SyncRecord, policy: str) -> str:
    if policy == "local":
        return "local"
    if policy == "remote":
        return "remote"
    # Compare (time, hash) so every device independently picks the same winner.
    local_key = (local.change_time, local.content_hash)
    remote_key = (remote.change_time, remote.content_hash)
    return "remote" if remote_key > local_key else "local"


def merge_one(
    uid: str,
    local: SyncRecord | None,
    remote: SyncRecord | None,
    base: str | None,
    *,
    policy: str = DEFAULT_POLICY,
    conflict_copies: bool = True,
    new_uid: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> MergeAction:
    title = _display_title(local, remote)

    if remote is None:
        if local is None:
            return MergeAction(uid, IN_SYNC, "unknown on both sides", title)
        return MergeAction(uid, PUBLISH, "only on this device", title)

    if local is None:
        action = _remote_apply_action(None, remote)
        reason = "deleted on another device" if remote.is_deleted else "new on another device"
        return MergeAction(uid, action, reason, title, apply=remote)

    if local.content_hash == remote.content_hash:
        return MergeAction(uid, IN_SYNC, "identical", title)

    local_changed = base != local.content_hash
    remote_changed = base != remote.content_hash

    if not local_changed:
        if remote.change_time >= local.change_time or local.is_deleted:
            action = _remote_apply_action(local, remote)
            return MergeAction(uid, action, "changed on another device", title, apply=remote)
        return MergeAction(uid, PUBLISH, "other device has an older copy", title)

    if not remote_changed:
        return MergeAction(uid, PUBLISH, "changed on this device", title)

    if local.is_deleted:
        return MergeAction(
            uid, CREATE, "edited elsewhere after local delete (edit wins)", title, apply=remote
        )
    if remote.is_deleted:
        return MergeAction(uid, PUBLISH, "edited here after remote delete (edit wins)", title)

    winner = _pick_winner(local, remote, policy)
    if winner == "remote":
        copy = local.as_conflict_copy(new_uid(), CONFLICT_COPY_SUFFIX) if conflict_copies else None
        return MergeAction(
            uid, CONFLICT, f"both edited; kept other device's version ({policy})", title,
            apply=remote, copy=copy,
        )
    copy = remote.as_conflict_copy(new_uid(), CONFLICT_COPY_SUFFIX) if conflict_copies else None
    return MergeAction(
        uid, CONFLICT, f"both edited; kept this device's version ({policy})", title,
        apply=None, copy=copy,
    )


def plan_merge(
    local: dict[str, SyncRecord],
    remote: dict[str, SyncRecord],
    base: dict[str, str],
    *,
    policy: str = DEFAULT_POLICY,
    conflict_copies: bool = True,
    new_uid: Callable[[], str] = lambda: uuid.uuid4().hex,
) -> MergePlan:
    plan = MergePlan(policy=policy)
    for uid in sorted(set(local) | set(remote)):
        plan.actions.append(
            merge_one(
                uid,
                local.get(uid),
                remote.get(uid),
                base.get(uid),
                policy=policy,
                conflict_copies=conflict_copies,
                new_uid=new_uid,
            )
        )
    return plan
