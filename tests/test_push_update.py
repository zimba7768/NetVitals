"""The commit-and-push helper.

Every assertion here corresponds to something that actually went wrong while
pushing this project by hand. They are regression tests for a workflow rather
than for the application, which is unusual but warranted: both mistakes reached
the public repository.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def load_tool():
    path = os.path.join(ROOT, "tools", "push_update.py")
    spec = importlib.util.spec_from_file_location("push_update", path)
    module = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, ["push_update.py"]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = argv
    return module


tool = load_tool()


class MessageFileTests(unittest.TestCase):
    """The scratch file must never be inside the working tree.

    Writing it into the repository meant `git add -A` staged it before the
    `del` could run. That happened twice, and both times it reached GitHub.
    """

    def setUp(self) -> None:
        self.path = tool.write_message("Subject\n\nBody\n")
        self.addCleanup(lambda: os.path.exists(self.path)
                        and os.unlink(self.path))

    def test_it_is_written_outside_the_repository(self) -> None:
        self.assertNotIn(Path(ROOT).resolve(), Path(self.path).resolve().parents)

    def test_it_has_no_byte_order_mark(self) -> None:
        # A BOM here became an invisible character at the start of the commit
        # subject, visible forever in the GitHub history.
        raw = Path(self.path).read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(raw.startswith(b"Subject"))

    def test_it_uses_unix_line_endings(self) -> None:
        self.assertNotIn(b"\r\n", Path(self.path).read_bytes())


class MessageShapeTests(unittest.TestCase):
    def test_the_subject_comes_first_and_alone(self) -> None:
        message = tool.build_message("Fix the thing")
        self.assertTrue(message.startswith("Fix the thing\n\n"))

    def test_trailers_form_one_contiguous_block_at_the_end(self) -> None:
        # Separate -m arguments put a blank line between trailers, which stops
        # git parsing them as a trailer block.
        message = tool.build_message("Subject", "Some body text.")
        tail = message.rstrip("\n").split("\n\n")[-1]
        for line in tail.splitlines():
            self.assertRegex(line, r"^[A-Za-z-]+: ")

    def test_the_body_sits_between_subject_and_trailers(self) -> None:
        message = tool.build_message("Subject", "Explanation.")
        self.assertLess(message.index("Explanation."),
                        message.index("Co-Authored-By"))
        self.assertLess(message.index("Subject"), message.index("Explanation."))

    def test_a_missing_body_leaves_no_blank_gap(self) -> None:
        message = tool.build_message("Subject", "")
        self.assertNotIn("\n\n\n", message)

    def test_surrounding_whitespace_is_trimmed(self) -> None:
        self.assertTrue(tool.build_message("  Subject  ").startswith("Subject\n"))


class VersionTests(unittest.TestCase):
    def test_the_version_is_read_from_the_app_itself(self) -> None:
        # The tag has to match what Settings reports, so it is read from the
        # same place rather than typed twice.
        from netpulse.config import APP_VERSION
        self.assertEqual(tool.app_version(), APP_VERSION)

    def test_it_looks_like_a_version(self) -> None:
        self.assertRegex(tool.app_version(), r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
