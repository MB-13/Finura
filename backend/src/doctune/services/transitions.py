"""The project status machine (docs/plan/01-architecture.md §5).

Pure data + checks, shared by the async API and the sync workers. Nothing else may decide
whether a status change is legal.
"""

from enum import StrEnum

from doctune.models.enums import ProjectStatus as S


class Actor(StrEnum):
    user = "user"
    api = "api"
    worker = "worker"
    notebook = "notebook"
    monitor = "monitor"


A = Actor

# (from, to) -> actors allowed to make that change
ALLOWED: dict[tuple[S, S], frozenset[Actor]] = {
    (S.draft, S.uploaded): frozenset({A.api}),
    (S.uploaded, S.draft): frozenset({A.api}),  # last document removed
    (S.uploaded, S.parsing): frozenset({A.user}),
    (S.parsing, S.awaiting_style): frozenset({A.worker}),
    (S.parsing, S.failed): frozenset({A.worker}),
    # more documents can be added before any generation starts
    (S.awaiting_style, S.uploaded): frozenset({A.api}),
    (S.awaiting_style, S.previewing): frozenset({A.user}),
    (S.previewing, S.awaiting_style): frozenset({A.worker, A.user}),
    (S.awaiting_style, S.generating): frozenset({A.user}),
    (S.generating, S.in_review): frozenset({A.worker}),
    (S.generating, S.failed): frozenset({A.worker}),
    (S.generating, S.awaiting_style): frozenset({A.user}),
    (S.in_review, S.awaiting_style): frozenset({A.user}),
    (S.in_review, S.generating): frozenset({A.user}),  # complete a run that was finished early
    (S.in_review, S.awaiting_run): frozenset({A.user}),
    (S.awaiting_run, S.training): frozenset({A.notebook}),
    (S.awaiting_run, S.paused): frozenset({A.notebook}),  # e.g. no GPU before training starts
    (S.training, S.paused): frozenset({A.notebook, A.monitor}),
    (S.paused, S.training): frozenset({A.notebook}),
    (S.training, S.evaluating): frozenset({A.notebook}),
    (S.evaluating, S.ready): frozenset({A.notebook}),
    (S.awaiting_run, S.in_review): frozenset({A.user}),
    (S.training, S.in_review): frozenset({A.user}),
    (S.paused, S.in_review): frozenset({A.user}),
    (S.evaluating, S.failed): frozenset({A.notebook, A.worker}),
    (S.training, S.failed): frozenset({A.notebook, A.worker}),
    # automatic backends (Kaggle): a launch can fail before the kernel ever started, and a paused run can be given up
    (S.awaiting_run, S.failed): frozenset({A.worker}),
    (S.paused, S.failed): frozenset({A.worker}),
}

# a failed project can go back to wherever the failure says is safe
RETRY_TARGETS: frozenset[S] = frozenset({S.uploaded, S.awaiting_style, S.in_review, S.paused})


class InvalidTransitionError(Exception):
    def __init__(self, from_status: S, to_status: S, actor: Actor):
        super().__init__(f"{actor} cannot move a project from {from_status} to {to_status}")
        self.from_status, self.to_status, self.actor = from_status, to_status, actor


def check(from_status: S, to_status: S, actor: Actor) -> None:
    if from_status == S.failed and actor == A.user and to_status in RETRY_TARGETS:
        return
    if actor not in ALLOWED.get((from_status, to_status), frozenset()):
        raise InvalidTransitionError(from_status, to_status, actor)


def is_allowed(from_status: S, to_status: S, actor: Actor) -> bool:
    try:
        check(from_status, to_status, actor)
    except InvalidTransitionError:
        return False
    return True


# what the UI may offer in each status (buttons are enabled from this, never re-derived client-side)
ACTIONS: dict[S, tuple[str, ...]] = {
    S.draft: ("upload", "rename", "delete"),
    S.uploaded: ("upload", "remove_document", "process", "rename", "delete"),
    S.parsing: ("rename", "delete"),
    S.awaiting_style: ("upload", "remove_document", "edit_style", "preview", "generate", "rename", "delete"),
    S.previewing: ("rename", "delete"),
    S.generating: ("finish_generation", "cancel_generation", "rename", "delete"),
    S.in_review: ("edit_dataset", "export_dataset", "approve_dataset", "restyle", "rename", "delete"),
    S.awaiting_run: ("rotate_token", "cancel_training", "rename", "delete"),
    S.training: ("cancel_training", "rename", "delete"),
    S.paused: ("rotate_token", "download_checkpoint", "cancel_training", "playground", "rename", "delete"),
    S.evaluating: ("rename", "delete"),
    S.ready: ("download", "playground", "export_dataset", "rename", "delete"),
    S.failed: ("retry", "rename", "delete"),
}


def allowed_actions(status: S, *, retry_available: bool = False) -> list[str]:
    actions = list(ACTIONS[status])
    if status == S.failed and not retry_available:
        actions.remove("retry")
    return actions
