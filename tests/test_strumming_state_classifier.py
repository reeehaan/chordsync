from analysis.evaluation.strumming_state_classifier import (
    EvidenceStrength,
    StrummingEvidenceWindow,
    StrummingState,
    classify_strumming_windows,
)


def _window(
    index,
    *,
    model="NORMAL",
    structure="NORMAL",
    section="NORMAL",
    disagreement="NORMAL",
):
    return StrummingEvidenceWindow(
        start=index * 8.0,
        end=(index + 1) * 8.0,
        model_uncertainty=EvidenceStrength(model),
        structural_instability=EvidenceStrength(structure),
        section_consistency=EvidenceStrength(section),
        estimator_disagreement=EvidenceStrength(disagreement),
    )


def test_single_weak_signal_cannot_trigger_music_only():
    result = classify_strumming_windows(
        [_window(0, disagreement="STRONGLY_WEAK")]
    )

    assert result[0].state == StrummingState.UNCERTAIN
    assert not result[0].music_only_candidate


def test_music_only_requires_multiple_groups_and_consecutive_windows():
    evidence = dict(
        model="WEAK",
        structure="WEAK",
        section="WEAK",
        disagreement="STRONGLY_WEAK",
    )

    result = classify_strumming_windows(
        [_window(0, **evidence), _window(1, **evidence)]
    )

    assert [window.state for window in result] == [
        StrummingState.UNCERTAIN,
        StrummingState.MUSIC_ONLY,
    ]


def test_recovery_requires_two_stable_windows_with_uncertain_buffer():
    weak = dict(
        model="WEAK",
        structure="WEAK",
        section="WEAK",
        disagreement="STRONGLY_WEAK",
    )
    result = classify_strumming_windows(
        [
            _window(0, **weak),
            _window(1, **weak),
            _window(2),
            _window(3),
        ]
    )

    assert [window.state for window in result] == [
        StrummingState.UNCERTAIN,
        StrummingState.MUSIC_ONLY,
        StrummingState.UNCERTAIN,
        StrummingState.PLAY_CHORD,
    ]


def test_partial_warning_uses_uncertain_fallback():
    result = classify_strumming_windows(
        [_window(0, model="WEAK", structure="WEAK")]
    )

    assert result[0].state == StrummingState.UNCERTAIN


def test_unique_but_otherwise_healthy_guard_case_remains_play_chord():
    result = classify_strumming_windows(
        [
            _window(0, section="STRONGLY_WEAK"),
            _window(1, section="STRONGLY_WEAK"),
        ]
    )

    assert [window.state for window in result] == [
        StrummingState.PLAY_CHORD,
        StrummingState.PLAY_CHORD,
    ]
