from analysis.evaluation.strumming_state_classifier import (
    ClassifiedStrummingWindow,
    EvidenceStrength,
    StrummingEvidenceWindow,
    StrummingState,
    consolidate_strumming_windows,
    export_confirmed_music_only_regions,
)


def _classified(index, state, *, weak=0, strong=0, candidate=False):
    return ClassifiedStrummingWindow(
        start=index * 8.0,
        end=(index + 1) * 8.0,
        state=StrummingState(state),
        weak_group_count=weak,
        strongly_weak_group_count=strong,
        music_only_candidate=candidate,
    )


def _evidence(index, *, structure="NORMAL"):
    return StrummingEvidenceWindow(
        start=index * 8.0,
        end=(index + 1) * 8.0,
        model_uncertainty=EvidenceStrength.NORMAL,
        structural_instability=EvidenceStrength(structure),
        section_consistency=EvidenceStrength.NORMAL,
        estimator_disagreement=EvidenceStrength.NORMAL,
    )


def _states(windows):
    return [window.state for window in windows]


def test_suppresses_isolated_music_only_without_supportive_neighbors():
    classified = [
        _classified(0, "PLAY_CHORD"),
        _classified(1, "MUSIC_ONLY", weak=3, strong=1, candidate=True),
        _classified(2, "PLAY_CHORD"),
    ]

    result = consolidate_strumming_windows(
        classified,
        [_evidence(0), _evidence(1, structure="WEAK"), _evidence(2)],
    )

    assert _states(result) == [
        StrummingState.PLAY_CHORD,
        StrummingState.UNCERTAIN,
        StrummingState.PLAY_CHORD,
    ]


def test_expands_into_supported_uncertain_neighbor():
    classified = [
        _classified(0, "UNCERTAIN", weak=3),
        _classified(1, "MUSIC_ONLY", weak=3, strong=1, candidate=True),
        _classified(2, "UNCERTAIN", weak=1),
    ]
    evidence = [
        _evidence(0, structure="WEAK"),
        _evidence(1, structure="WEAK"),
        _evidence(2),
    ]

    result = consolidate_strumming_windows(classified, evidence)

    assert _states(result) == [
        StrummingState.MUSIC_ONLY,
        StrummingState.MUSIC_ONLY,
        StrummingState.UNCERTAIN,
    ]


def test_does_not_expand_across_play_chord_window():
    classified = [
        _classified(0, "PLAY_CHORD", weak=3),
        _classified(1, "MUSIC_ONLY", weak=3, strong=1, candidate=True),
        _classified(2, "UNCERTAIN", weak=3),
    ]
    evidence = [
        _evidence(0, structure="WEAK"),
        _evidence(1, structure="WEAK"),
        _evidence(2, structure="WEAK"),
    ]

    result = consolidate_strumming_windows(classified, evidence)

    assert _states(result) == [
        StrummingState.PLAY_CHORD,
        StrummingState.MUSIC_ONLY,
        StrummingState.MUSIC_ONLY,
    ]


def test_applies_configured_minimum_music_only_duration():
    classified = [
        _classified(0, "MUSIC_ONLY", weak=3, candidate=True),
        _classified(1, "MUSIC_ONLY", weak=3, candidate=True),
    ]
    evidence = [_evidence(0, structure="WEAK"), _evidence(1, structure="WEAK")]

    result = consolidate_strumming_windows(
        classified,
        evidence,
        minimum_music_only_beats=24,
    )

    assert _states(result) == [
        StrummingState.UNCERTAIN,
        StrummingState.UNCERTAIN,
    ]


def test_inserts_uncertain_buffer_before_stable_recovery():
    classified = [
        _classified(0, "MUSIC_ONLY", weak=3, candidate=True),
        _classified(1, "MUSIC_ONLY", weak=3, candidate=True),
        _classified(2, "PLAY_CHORD"),
        _classified(3, "PLAY_CHORD"),
    ]
    evidence = [_evidence(index, structure="WEAK") for index in range(2)]
    evidence.extend([_evidence(2), _evidence(3)])

    result = consolidate_strumming_windows(classified, evidence)

    assert _states(result) == [
        StrummingState.MUSIC_ONLY,
        StrummingState.MUSIC_ONLY,
        StrummingState.UNCERTAIN,
        StrummingState.PLAY_CHORD,
    ]


def test_valid_unique_intro_cannot_manufacture_music_only():
    classified = [
        _classified(0, "UNCERTAIN", weak=2, strong=1),
        _classified(1, "UNCERTAIN", weak=1),
        _classified(2, "PLAY_CHORD"),
    ]
    evidence = [
        _evidence(0, structure="WEAK"),
        _evidence(1, structure="WEAK"),
        _evidence(2),
    ]

    result = consolidate_strumming_windows(classified, evidence)

    assert _states(result) == [
        StrummingState.UNCERTAIN,
        StrummingState.UNCERTAIN,
        StrummingState.PLAY_CHORD,
    ]


def test_exports_only_contiguous_confirmed_music_only_windows():
    classified = [
        _classified(0, "PLAY_CHORD"),
        _classified(1, "UNCERTAIN"),
        _classified(2, "MUSIC_ONLY", weak=3, candidate=True),
        _classified(3, "MUSIC_ONLY", weak=3, candidate=True),
        _classified(4, "UNCERTAIN"),
    ]
    evidence = [
        _evidence(0),
        _evidence(1),
        _evidence(2, structure="WEAK"),
        _evidence(3, structure="WEAK"),
        _evidence(4),
    ]

    result = export_confirmed_music_only_regions(classified, evidence)

    assert [region.model_dump(mode="json") for region in result] == [
        {"start": 16.0, "end": 32.0, "mode": "music_only"}
    ]


def test_export_suppresses_unconsolidated_one_window_candidate():
    result = export_confirmed_music_only_regions(
        [_classified(0, "MUSIC_ONLY", weak=3, candidate=True)],
        [_evidence(0, structure="WEAK")],
    )

    assert result == []
