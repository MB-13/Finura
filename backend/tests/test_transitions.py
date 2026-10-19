import itertools

import pytest

from doctune.models.enums import ProjectStatus as S
from doctune.services.transitions import (
    ACTIONS,
    ALLOWED,
    RETRY_TARGETS,
    Actor,
    InvalidTransitionError,
    allowed_actions,
    check,
    is_allowed,
)


@pytest.mark.parametrize(("from_status", "to_status", "actor"), list(itertools.product(S, S, Actor)))
def test_every_triple_matches_the_table(from_status: S, to_status: S, actor: Actor) -> None:
    expected = actor in ALLOWED.get((from_status, to_status), frozenset()) or (
        from_status == S.failed and actor == Actor.user and to_status in RETRY_TARGETS
    )
    assert is_allowed(from_status, to_status, actor) is expected


def test_happy_path_is_reachable() -> None:
    path = [
        (S.draft, S.uploaded, Actor.api),
        (S.uploaded, S.parsing, Actor.user),
        (S.parsing, S.awaiting_style, Actor.worker),
        (S.awaiting_style, S.previewing, Actor.user),
        (S.previewing, S.awaiting_style, Actor.worker),
        (S.awaiting_style, S.generating, Actor.user),
        (S.generating, S.in_review, Actor.worker),
        (S.in_review, S.awaiting_run, Actor.user),
        (S.awaiting_run, S.training, Actor.notebook),
        (S.training, S.paused, Actor.monitor),
        (S.paused, S.training, Actor.notebook),
        (S.training, S.evaluating, Actor.notebook),
        (S.evaluating, S.ready, Actor.notebook),
    ]
    for from_status, to_status, actor in path:
        check(from_status, to_status, actor)


@pytest.mark.parametrize(
    ("from_status", "to_status", "actor"),
    [
        (S.awaiting_run, S.training, Actor.user),  # only the notebook starts training
        (S.parsing, S.awaiting_style, Actor.user),  # only the worker finishes parsing
        (S.draft, S.ready, Actor.notebook),
        (S.ready, S.draft, Actor.user),
    ],
)
def test_illegal_moves_raise(from_status: S, to_status: S, actor: Actor) -> None:
    with pytest.raises(InvalidTransitionError):
        check(from_status, to_status, actor)


def test_every_status_has_actions() -> None:
    assert set(ACTIONS) == set(S)
    assert "retry" not in allowed_actions(S.failed, retry_available=False)
    assert "retry" in allowed_actions(S.failed, retry_available=True)


def test_automatic_backends_can_fail_before_or_while_paused() -> None:
    # Kaggle launch failure (awaiting_run) and giving up on a paused run: workers only
    for src in (S.awaiting_run, S.paused):
        check(src, S.failed, Actor.worker)
        for actor in (Actor.user, Actor.api, Actor.notebook, Actor.monitor):
            assert not is_allowed(src, S.failed, actor)
