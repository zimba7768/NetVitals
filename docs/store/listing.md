# Microsoft Store listing — NetPulse

Copy for the Partner Center submission. Two builds exist and the difference is
stated plainly here rather than discovered after install: a user who finds the
Applications page empty and no explanation concludes the app is broken.

## Name

NetPulse — Network Usage Monitor

## Short description (≤ 200 characters)

See exactly how much you upload and download — per hour, day, week, month and
year — with VPN traffic kept separate. Local, private, no account, no telemetry.

## Description

NetPulse shows where your bandwidth goes.

**Totals for every period you'd want.** This hour, today, this week, this month,
this year, all time — as hoverable charts and as plain tables.

**VPN traffic kept separate.** When a tunnel is up, NetPulse measures it apart
from your direct traffic instead of adding the two together, which is what
produces the doubled figures other monitors show while a VPN is connected. A
dedicated VPN tab carries the same views for tunnelled traffic alone.

**A file log.** Every file that lands in your watched folders, with its size,
when it arrived, and the address it came from.

**Live throughput.** A two-minute rolling graph, plus a tray icon whose arrows
brighten with activity.

**Local and private.** One database file on your own machine. No account, no
cloud, no telemetry. The only outbound request NetPulse ever makes is the
optional public-IP lookup, and that has an off switch.

### About per-application volumes

This Store build does not show how much each individual program used. That
feature needs a Windows kernel trace, which requires administrator rights, and
Windows does not permit Store apps to run with them. Nothing NetPulse can change
— the restriction is the platform's.

Everything else above works exactly the same in both builds.

If you want the per-application breakdown, the desktop version is the same
program without that restriction. It is free, its source is public, and it is
released under the MIT licence:

https://github.com/zimba7768/Netpulse

### Open source

NetPulse is MIT-licensed and developed in the open. Issues and contributions
welcome at the address above.

## Website / Support contact

https://github.com/zimba7768/Netpulse

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
- Privacy policy: required whenever a product collects anything. NetPulse
  collects nothing and sends nothing except the optional IP lookup — say that
  in one line rather than leaving the field empty.
- The listing links to the desktop build. The Store's restrictions on sending
  users elsewhere concern *purchase* mechanisms; both builds here are free, and
  Website/Support URL are sanctioned fields for the project address.
