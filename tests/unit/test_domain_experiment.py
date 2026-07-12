import pytest

from researchforge.domain.experiment import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    ExperimentStatus,
    InvalidTransitionError,
    advance,
)


class TestStateTransitions:
    def test_every_status_has_a_transition_entry(self) -> None:
        assert set(ALLOWED_TRANSITIONS) == set(ExperimentStatus)

    def test_terminal_statuses_allow_nothing_except_validated_to_ready(self) -> None:
        for status in TERMINAL_STATUSES:
            if status is ExperimentStatus.VALIDATED:
                assert ALLOWED_TRANSITIONS[status] == {ExperimentStatus.IMPLEMENTATION_READY}
            else:
                assert ALLOWED_TRANSITIONS[status] == frozenset()

    @pytest.mark.parametrize(
        ("current", "new"),
        [
            (ExperimentStatus.PLANNED, ExperimentStatus.APPROVED),
            (ExperimentStatus.APPROVED, ExperimentStatus.PREPARING),
            (ExperimentStatus.PREPARING, ExperimentStatus.RUNNING),
            (ExperimentStatus.PREPARING, ExperimentStatus.REJECTED),  # path re-check
            (ExperimentStatus.RUNNING, ExperimentStatus.PROMISING),
            (ExperimentStatus.RUNNING, ExperimentStatus.REJECTED),
            (ExperimentStatus.RUNNING, ExperimentStatus.FAILED_EXECUTION),
            (ExperimentStatus.PROMISING, ExperimentStatus.VALIDATING),
            (ExperimentStatus.PROMISING, ExperimentStatus.PREPARING),  # resume re-attempt
            (ExperimentStatus.VALIDATING, ExperimentStatus.VALIDATED),
            (ExperimentStatus.VALIDATING, ExperimentStatus.PROMISING),
            (ExperimentStatus.VALIDATING, ExperimentStatus.REJECTED),
            (ExperimentStatus.VALIDATED, ExperimentStatus.IMPLEMENTATION_READY),
        ],
    )
    def test_legal_transitions(self, current: ExperimentStatus, new: ExperimentStatus) -> None:
        assert advance(current, new) is new

    @pytest.mark.parametrize(
        ("current", "new"),
        [
            (ExperimentStatus.PLANNED, ExperimentStatus.RUNNING),  # skips approval
            (ExperimentStatus.PLANNED, ExperimentStatus.VALIDATED),
            (ExperimentStatus.APPROVED, ExperimentStatus.PROMISING),
            (ExperimentStatus.RUNNING, ExperimentStatus.VALIDATED),  # one-off can't validate
            (ExperimentStatus.REJECTED, ExperimentStatus.RUNNING),
            (ExperimentStatus.FAILED_EXECUTION, ExperimentStatus.PROMISING),
            (ExperimentStatus.CANCELLED, ExperimentStatus.APPROVED),
            (ExperimentStatus.VALIDATED, ExperimentStatus.PROMISING),
        ],
    )
    def test_illegal_transitions_raise(
        self, current: ExperimentStatus, new: ExperimentStatus
    ) -> None:
        with pytest.raises(InvalidTransitionError):
            advance(current, new)

    def test_validated_requires_validating_first(self) -> None:
        # Structural "never call a one-off validated": no path to VALIDATED
        # except through VALIDATING.
        sources = [
            status
            for status, targets in ALLOWED_TRANSITIONS.items()
            if ExperimentStatus.VALIDATED in targets
        ]
        assert sources == [ExperimentStatus.VALIDATING]
