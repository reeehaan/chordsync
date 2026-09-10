from pathlib import Path

import pytest

from analysis.evaluation.compare_estimators import main


def write_lab(path: Path, labels: tuple[str, str]) -> None:
    path.write_text(
        f"0.0 1.0 {labels[0]}\n1.0 2.0 {labels[1]}\n",
        encoding="utf-8",
    )


def test_cli_uses_supplied_synthetic_reference(
    tmp_path: Path,
    capsys,
) -> None:
    reference_path = tmp_path / "reference.lab"
    chordino_path = tmp_path / "chordino.lab"
    btc_path = tmp_path / "btc.lab"

    write_lab(reference_path, ("C", "G"))
    write_lab(chordino_path, ("C", "G"))
    write_lab(btc_path, ("C", "G"))

    main([
        "--reference",
        str(reference_path),
        "--chordino-prediction",
        str(chordino_path),
        "--btc-prediction",
        str(btc_path),
    ])

    output = capsys.readouterr().out
    assert "Chordino" in output
    assert "BTC" in output
    assert output.count("1.0000") == 4


def test_cli_reports_a_missing_reference_file(tmp_path: Path) -> None:
    missing_reference = tmp_path / "missing-reference.lab"

    with pytest.raises(
        FileNotFoundError,
        match="Reference lab file not found",
    ):
        main([
            "--reference",
            str(missing_reference),
        ])
