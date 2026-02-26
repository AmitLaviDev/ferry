"""Tests for ferry_action.gha — GHA workflow command helpers."""

from __future__ import annotations

import pytest

from ferry_action.gha import (
    begin_group,
    end_group,
    error,
    mask_value,
    set_output,
    warning,
    write_summary,
)


class TestSetOutput:
    """Tests for set_output()."""

    def test_writes_to_github_output_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Writes name=value to the GITHUB_OUTPUT file."""
        output_file = tmp_path / "github_output"
        output_file.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        set_output("matrix", '{"include":[]}')

        content = output_file.read_text()
        assert content == 'matrix={"include":[]}\n'

    def test_appends_multiple_outputs(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Multiple calls append to the file."""
        output_file = tmp_path / "github_output"
        output_file.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        set_output("first", "value1")
        set_output("second", "value2")

        lines = output_file.read_text().strip().split("\n")
        assert lines == ["first=value1", "second=value2"]

    def test_fallback_without_github_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Falls back to deprecated set-output command when GITHUB_OUTPUT not set."""
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

        set_output("key", "val")

        captured = capsys.readouterr()
        assert "::set-output name=key::val" in captured.out


class TestBeginGroup:
    """Tests for begin_group()."""

    def test_prints_group_command(self, capsys: pytest.CaptureFixture) -> None:
        """Prints ::group::title."""
        begin_group("Building order-processor")

        captured = capsys.readouterr()
        assert captured.out.strip() == "::group::Building order-processor"


class TestEndGroup:
    """Tests for end_group()."""

    def test_prints_endgroup_command(self, capsys: pytest.CaptureFixture) -> None:
        """Prints ::endgroup::."""
        end_group()

        captured = capsys.readouterr()
        assert captured.out.strip() == "::endgroup::"


class TestMaskValue:
    """Tests for mask_value()."""

    def test_prints_mask_command(self, capsys: pytest.CaptureFixture) -> None:
        """Prints ::add-mask::value."""
        mask_value("super-secret-123")

        captured = capsys.readouterr()
        assert captured.out.strip() == "::add-mask::super-secret-123"


class TestError:
    """Tests for error()."""

    def test_prints_error_command(self, capsys: pytest.CaptureFixture) -> None:
        """Prints ::error::message."""
        error("Something went wrong")

        captured = capsys.readouterr()
        assert captured.out.strip() == "::error::Something went wrong"


class TestWarning:
    """Tests for warning()."""

    def test_prints_warning_command(self, capsys: pytest.CaptureFixture) -> None:
        """Prints ::warning::message."""
        warning("Heads up")

        captured = capsys.readouterr()
        assert captured.out.strip() == "::warning::Heads up"


class TestWriteSummary:
    """Tests for write_summary()."""

    def test_writes_to_step_summary_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Appends markdown to the GITHUB_STEP_SUMMARY file."""
        summary_file = tmp_path / "step_summary"
        summary_file.touch()
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        write_summary("## Deploy Complete\n")

        content = summary_file.read_text()
        assert content == "## Deploy Complete\n"

    def test_appends_multiple_summaries(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pytest.TempPathFactory,
    ) -> None:
        """Multiple calls append to the file."""
        summary_file = tmp_path / "step_summary"
        summary_file.touch()
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        write_summary("## First\n")
        write_summary("## Second\n")

        content = summary_file.read_text()
        assert "## First\n## Second\n" == content

    def test_fallback_without_step_summary(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Falls back to stdout when GITHUB_STEP_SUMMARY not set."""
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

        write_summary("## Done\n")

        captured = capsys.readouterr()
        assert "## Done" in captured.out
