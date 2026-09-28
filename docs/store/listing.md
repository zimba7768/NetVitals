# Microsoft Store listing — NetVitals

Copy for the Partner Center submission. Two builds exist and the difference is
stated plainly here rather than discovered after install: a user who finds the
Applications page empty and no explanation concludes the app is broken.

## Name

NetVitals — Network Usage Monitor

## Short description (≤ 200 characters)

See exactly how much you upload and download — per hour, day, week, month and
year — with VPN traffic kept separate. Local, private, no account, no telemetry.

## Description

NetVitals shows where your bandwidth goes.

**Totals for every period you'd want.** This hour, today, this week, this month,
this year, all time — as hoverable charts and as plain tables.

**VPN traffic kept separate.** When a tunnel is up, NetVitals measures it apart
from your direct traffic instead of adding the two together, which is what
produces the doubled figures other monitors show while a VPN is connected. A
dedicated VPN tab carries the same views for tunnelled traffic alone.

**A file log.** Every file that lands in your watched folders, with its size,
when it arrived, and the address it came from.

**Live throughput.** A two-minute rolling graph, plus a tray icon whose arrows
brighten with activity.

**Adapters and connections.** Which adapter is carrying what, and which
application is talking to which host — grouped so a browser's thirty sockets to
one host read as one line, and labelled with whether each conversation went
through the tunnel.

**Local and private.** One database file on your own machine. No account, no
cloud, no telemetry. The only outbound request NetVitals ever makes is the
optional public-IP lookup, and that has an off switch.

### About per-application volumes

This Store build does not show how much each individual program used. That
feature needs a Windows kernel trace, which requires administrator rights, and
Windows does not permit Store apps to run with them. Nothing NetVitals can change
— the restriction is the platform's.

Everything else above works exactly the same in both builds.

If you want the per-application breakdown, the desktop version is the same
program without that restriction. It is free, its source is public, and it is
released under the MIT licence:

https://github.com/zimba7768/NetVitals

### Open source

NetVitals is MIT-licensed and developed in the open. Issues and contributions
welcome at the address above.

## Website / Support contact

https://github.com/zimba7768/NetVitals

## Search terms

network monitor, bandwidth, data usage, VPN, upload download, traffic, metered

## Notes for the submission itself

- Category: **Utilities & tools**.
- Declare **runFullTrust**. Do **not** declare `allowElevation`: an app that
  asks to elevate is unlikely to pass certification, and this build has no use
  for it.
- Declare a **windows.startupTask** extension for the start-with-Windows
  option. Windows shows the switch in Task Manager › Startup apps; the app's
  own checkbox is disabled in packaged builds and says so.
- Privacy policy URL: **https://github.com/zimba7768/NetVitals/blob/main/PRIVACY.md**
  The Store requires one. PRIVACY.md is versioned with the application, so any
  change to it is visible in the commit history.
- Screenshots: `docs/store/01-dashboard.png` and the four beside it, rendered
  at 1920x1080 by `tools/make_store_images.py`. They show the **packaged**
  build with demo data — never the desktop build's per-application table,
  which would advertise a feature the package does not have, and never real
  usage. Captions are printed by that script.
- App tile icon: `docs/store/store-tile-300.png` (300x300, strongly
  recommended; the Store prefers it over the package icon).
- The listing links to the desktop build. The Store's restrictions on sending
  users elsewhere concern *purchase* mechanisms; both builds here are free, and
  Website/Support URL are sanctioned fields for the project address.
