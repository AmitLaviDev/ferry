"""GitHub Actions workflow command helpers.

Thin wrappers around GHA workflow command syntax for logging,
masking, output setting, and step summaries.
"""

from __future__ import annotations

import os
import sys


def set_output(name: str, value: str) -> None:
    """Write a step output to $GITHUB_OUTPUT.

    Appends ``name=value`` to the GITHUB_OUTPUT file. For values that
    may contain newlines, uses the delimiter pattern. In practice,
    matrix JSON is single-line so the simple format works.

    Args:
        name: Output parameter name.
        value: Output parameter value.
    """
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"{name}={value}\n")
    else:
        # Fallback: print the deprecated set-output command for local testing
        print(f"::set-output name={name}::{value}")


def begin_group(title: str) -> None:
    """Start a collapsible log group in GHA.

    Args:
        title: Group title displayed in the log.
    """
    print(f"::group::{title}")
    sys.stdout.flush()


def end_group() -> None:
    """End the current collapsible log group."""
    print("::endgroup::")
    sys.stdout.flush()


def mask_value(value: str) -> None:
    """Mask a value so it is redacted in GHA logs.

    Args:
        value: The sensitive string to mask.
    """
    print(f"::add-mask::{value}")
    sys.stdout.flush()


def error(message: str) -> None:
    """Emit an error annotation in GHA.

    Args:
        message: Error message text.
    """
    print(f"::error::{message}")
    sys.stdout.flush()


def warning(message: str) -> None:
    """Emit a warning annotation in GHA.

    Args:
        message: Warning message text.
    """
    print(f"::warning::{message}")
    sys.stdout.flush()


def write_summary(markdown: str) -> None:
    """Append markdown content to the GHA job step summary.

    Args:
        markdown: Markdown string to append to the summary.
    """
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a") as f:
            f.write(markdown)
    else:
        # Fallback for local testing: print to stdout
        print(markdown)
