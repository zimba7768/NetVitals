"""Build the Microsoft Store package layout: manifest, assets, staged files.

    python tools/make_msix.py [--staging DIR]

Produces everything makeappx needs. The manifest is generated rather than
checked in so the package version can never drift from APP_VERSION — the same
drift that already has to be watched between APP_VERSION and the git tag.

The package is deliberately left unsigned. The Store signs what it accepts,
and signing it yourself risks a publisher mismatch that fails validation;
locally, ``Add-AppxPackage -AllowUnsigned`` installs it for testing.

Two more things in here are deliberate and easy to get wrong:

* **runFullTrust, and not allowElevation.** A packaged desktop app runs at
  medium integrity with no route to elevation, which is why the Store build
  has no per-application tracking. Asking to elevate would not grant it and
  would likely fail certification.
* **A four-part version ending in 0.** The Store rejects packages whose
  revision field is non-zero, reserving it for its own use.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: Assigned by the Store when the name was reserved. Not secrets — every one
#: of these is inside any package that ships.
IDENTITY_NAME = "SeeBell.NetVitals"
PUBLISHER = "CN=10BC7C43-ED41-49B8-BF50-BDAE2A4857D8"
PUBLISHER_DISPLAY_NAME = "SeeBell"
STORE_ID = "9NKCJC2PBFC8"

#: 17763 is Windows 10 1809, the oldest release with the packaging features
#: used here. There is no reason to exclude anyone older than necessary.
MIN_WINDOWS = "10.0.17763.0"
MAX_TESTED_WINDOWS = "10.0.22621.0"

DESCRIPTION = ("See how much you upload and download, per hour, day, week, "
               "month and year, with VPN traffic kept separate.")

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:uap5="http://schemas.microsoft.com/appx/manifest/uap/windows10/5"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap uap5 rescap">

  <Identity
    Name="{identity_name}"
    Publisher="{publisher}"
    Version="{version}"
    ProcessorArchitecture="x64" />

  <Properties>
    <DisplayName>{display_name}</DisplayName>
    <PublisherDisplayName>{publisher_display_name}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>

  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop"
                        MinVersion="{min_windows}"
                        MaxVersionTested="{max_tested}" />
  </Dependencies>

  <Resources>
    <Resource Language="en-us" />
  </Resources>

  <Applications>
    <Application Id="{app_id}"
                 Executable="{executable}"
                 EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="{display_name}"
        Description="{description}"
        BackgroundColor="transparent"
        Square150x150Logo="Assets\\Square150x150Logo.png"
        Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile
          Wide310x150Logo="Assets\\Wide310x150Logo.png"
          Square71x71Logo="Assets\\Square71x71Logo.png"
          Square310x310Logo="Assets\\Square310x310Logo.png" />
        <uap:SplashScreen Image="Assets\\SplashScreen.png" />
      </uap:VisualElements>
      <Extensions>
        <!-- Windows owns the start-with-Windows switch for packaged apps and
             shows it in Task Manager. Enabled="false" so installing does not
             silently opt the user in. -->
        <uap5:Extension
          Category="windows.startupTask"
          Executable="{executable}"
          EntryPoint="Windows.FullTrustApplication">
          <uap5:StartupTask
            TaskId="{app_id}Startup"
            Enabled="false"
            DisplayName="{display_name}" />
        </uap5:Extension>
      </Extensions>
    </Application>
  </Applications>

  <Capabilities>
    <!-- Full trust, not elevation: this is what lets a normal desktop
         application run at all. It does not grant administrator rights, and
         nothing here asks for them. -->
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""


def app_version() -> str:
    text = (ROOT / "netvitals" / "config.py").read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("Could not read APP_VERSION from netvitals/config.py")
    return match.group(1)


def package_version(version: str | None = None) -> str:
    """APP_VERSION as the four-part form the Store requires.

    The fourth part must be zero: the Store reserves the revision field and
    rejects a package that sets it.
    """
    parts = (version or app_version()).split(".")
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3] + ["0"])


def build_manifest(version: str | None = None) -> str:
    from netvitals.config import APP_NAME
    return MANIFEST.format(
        identity_name=IDENTITY_NAME,
        publisher=PUBLISHER,
        publisher_display_name=PUBLISHER_DISPLAY_NAME,
        version=package_version(version),
        display_name=APP_NAME,
        app_id=APP_NAME,
        executable=f"{APP_NAME}.exe",
        description=DESCRIPTION,
        min_windows=MIN_WINDOWS,
        max_tested=MAX_TESTED_WINDOWS,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging", default=str(ROOT / "build" / "msix"))
    parser.add_argument("--dist", default=str(ROOT / "dist" / "NetVitals"),
                        help="PyInstaller onedir output to package")
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()

    staging = Path(args.staging)
    manifest = build_manifest()

    if args.manifest_only:
        target = ROOT / "packaging" / "AppxManifest.xml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(manifest, encoding="utf-8")
        print(f"Wrote {target}")
        return 0

    dist = Path(args.dist)
    if not dist.is_dir():
        print(f"No build at {dist}.")
        print("Run build-exe.bat --onedir first (PyInstaller must produce a")
        print("folder, not a single file: the package needs the real layout,")
        print("and a one-file build would unpack itself on every launch).")
        return 1

    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(dist, staging)

    from tools.make_package_assets import write_assets
    count = write_assets(staging / "Assets")
    (staging / "AppxManifest.xml").write_text(manifest, encoding="utf-8")

    print(f"Staged {staging}")
    print(f"  {count} asset images")
    print(f"  AppxManifest.xml  (version {package_version()})")
    print()
    print("Now pack it:")
    print(f'  makeappx pack /d "{staging}" /p NetVitals.msix /o')
    print()
    print("And install it to try it out:")
    print("  Add-AppxPackage .\\NetVitals.msix -AllowUnsigned")
    print()
    print("No signing is needed, and signing would be a mistake: the Store")
    print("signs submissions with its own certificate, and a package signed")
    print("with your own can fail validation on a publisher mismatch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
