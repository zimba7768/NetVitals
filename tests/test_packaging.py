"""The Microsoft Store package manifest.

A manifest mistake is expensive in a way a code mistake is not: it passes
locally, then fails certification days later after the submission has sat in a
queue. These assertions encode the rules that are easy to get wrong and slow to
find out about.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import unittest
from xml.etree import ElementTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def load(name: str):
    path = os.path.join(ROOT, "tools", f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, [f"{name}.py"]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = argv
    return module


msix = load("make_msix")
assets = load("make_package_assets")

NS = {
    "m": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
    "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
    "uap5": "http://schemas.microsoft.com/appx/manifest/uap/windows10/5",
    "rescap": ("http://schemas.microsoft.com/appx/manifest/foundation/"
               "windows10/restrictedcapabilities"),
}


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.xml = msix.build_manifest()
        self.tree = ElementTree.fromstring(self.xml)

    def test_it_is_well_formed(self) -> None:
        self.assertTrue(self.tree.tag.endswith("Package"))

    def test_the_identity_matches_what_the_store_assigned(self) -> None:
        identity = self.tree.find("m:Identity", NS)
        self.assertEqual(identity.get("Name"), "SeeBell.NetVitals")
        self.assertEqual(identity.get("Publisher"),
                         "CN=10BC7C43-ED41-49B8-BF50-BDAE2A4857D8")

    def test_the_version_has_four_parts_ending_in_zero(self) -> None:
        # The Store reserves the revision field and rejects a package that
        # sets it. Nothing local catches this.
        version = self.tree.find("m:Identity", NS).get("Version")
        self.assertRegex(version, r"^\d+\.\d+\.\d+\.0$")

    def test_the_version_tracks_the_application(self) -> None:
        from netvitals.config import APP_VERSION
        self.assertTrue(
            self.tree.find("m:Identity", NS).get("Version").startswith(APP_VERSION),
            "the package version has drifted from APP_VERSION")

    def test_it_asks_for_full_trust_and_nothing_more(self) -> None:
        names = [c.get("Name") for c in self.tree.iter()
                 if c.tag.endswith("Capability")]
        self.assertIn("runFullTrust", names)

    def test_it_never_asks_to_elevate(self) -> None:
        # allowElevation would not grant per-application tracking anyway, and
        # an app that requests elevation is unlikely to pass certification.
        self.assertNotIn("allowElevation", self.xml)
        self.assertNotIn("requireAdministrator", self.xml)

    def test_the_entry_point_is_a_full_trust_desktop_app(self) -> None:
        application = self.tree.find(".//m:Application", NS)
        self.assertEqual(application.get("EntryPoint"),
                         "Windows.FullTrustApplication")
        self.assertEqual(application.get("Executable"), "NetVitals.exe")

    def test_startup_is_declared_but_off_by_default(self) -> None:
        # Windows owns this switch for packaged apps; installing must not
        # silently opt the user into starting with Windows.
        task = self.tree.find(".//uap5:StartupTask", NS)
        self.assertIsNotNone(task, "no startup task declared")
        self.assertEqual(task.get("Enabled"), "false")

    def test_every_referenced_image_is_one_we_generate(self) -> None:
        produced = {name for name, _, _, _ in assets.ASSETS}
        referenced = set(re.findall(r"Assets\\([A-Za-z0-9_.-]+\.png)", self.xml))
        self.assertTrue(referenced, "no images referenced")
        self.assertTrue(referenced <= produced,
                        f"manifest references images we never write: "
                        f"{sorted(referenced - produced)}")

    def test_a_windows_version_old_enough_to_be_useful(self) -> None:
        family = self.tree.find(".//m:TargetDeviceFamily", NS)
        self.assertEqual(family.get("Name"), "Windows.Desktop")
        major, minor, build, _ = family.get("MinVersion").split(".")
        self.assertLessEqual(int(build), 19041,
                             "excludes Windows 10 releases for no reason")


class VersionFormattingTests(unittest.TestCase):
    def test_a_three_part_version_gains_a_zero(self) -> None:
        self.assertEqual(msix.package_version("1.3.1"), "1.3.1.0")

    def test_a_short_version_is_padded(self) -> None:
        self.assertEqual(msix.package_version("2"), "2.0.0.0")

    def test_an_existing_revision_is_replaced_not_kept(self) -> None:
        self.assertEqual(msix.package_version("1.2.3.7"), "1.2.3.0")


class AssetTests(unittest.TestCase):
    def test_the_required_store_images_are_all_produced(self) -> None:
        names = {name for name, _, _, _ in assets.ASSETS}
        for required in ("StoreLogo.png", "Square44x44Logo.png",
                         "Square150x150Logo.png"):
            self.assertIn(required, names)

    def test_tiles_leave_room_around_the_icon(self) -> None:
        # Windows draws tiles on a coloured plate; art that fills the square
        # edge to edge looks wrong beside everything else on Start.
        for name, _, _, fill in assets.ASSETS:
            if name.startswith(("Square71", "Square150", "Square310", "Wide")):
                self.assertLess(fill, 0.8, name)

    def test_the_small_icon_fills_its_canvas(self) -> None:
        # The 44px one is an icon, not a tile: padding it wastes pixels where
        # there are fewest to spare.
        sizes = {name: fill for name, _, _, fill in assets.ASSETS}
        self.assertEqual(sizes["Square44x44Logo.png"], 1.0)

    def test_images_are_actually_written_at_the_stated_size(self) -> None:
        import shutil
        import tempfile
        from PySide6.QtGui import QPixmap
        folder = tempfile.mkdtemp(prefix="netvitals-assets-")
        self.addCleanup(shutil.rmtree, folder, True)
        from pathlib import Path
        written = assets.write_assets(Path(folder))
        self.assertEqual(written, len(assets.ASSETS))
        for name, width, height, _ in assets.ASSETS:
            image = QPixmap(os.path.join(folder, name))
            self.assertEqual((image.width(), image.height()), (width, height), name)


if __name__ == "__main__":
    unittest.main()
