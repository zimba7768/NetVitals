# Privacy policy

**NetVitals collects nothing, stores everything locally, and has no account.**

Last updated: 28 September 2026.

## What NetVitals records, and where it goes

NetVitals measures how much data your computer sends and receives, and logs
files that arrive in the folders you choose to watch. All of it is written to a
single SQLite database on your own machine:

```
%APPDATA%\NetVitals\netvitals.db
```

That file never leaves your computer. Nothing is uploaded, synchronised,
backed up, or transmitted anywhere. There is no account to create, no
telemetry, no analytics, no crash reporting, and no advertising.

Deleting that folder erases everything NetVitals knows about you. **Settings →
Reset all statistics** does the same from inside the application.

## The one outbound request

NetVitals makes exactly one kind of request to the internet: it asks an outside
service what public IP address your connection appears to come from, because
there is no reliable way for a program to discover that locally.

- It is sent to one of: ipify.org, checkip.amazonaws.com, icanhazip.com,
  ifconfig.me, ipinfo.io, or `1.1.1.1` (Cloudflare).
- It contains nothing but the request itself — no identifier, no usage data,
  nothing about you or your machine beyond the connection it arrives on.
- It happens at start-up, every fifteen minutes, and whenever your network
  adapters change (for example when a VPN connects).
- Those providers will see your IP address, as they would for any web request.
  Their own privacy policies apply to what they do with it.

**This can be switched off.** Uncheck *Show my public (WAN) IP on the
dashboard* in Settings and NetVitals makes no outbound requests at all.

## What NetVitals reads on your computer

To do its job it reads:

- **Network adapter byte counters** — the same figures Task Manager shows.
- **Folders you have chosen to watch** — by default Downloads, Desktop,
  Documents, Pictures, Videos and Music. It records file names, sizes and
  timestamps. It does not read file contents.
- **Browser download history** — the download tables kept by Chrome, Edge,
  Brave, Opera, Vivaldi and Firefox, to identify where a downloaded file came
  from. It reads only download records, not your browsing history. This can be
  switched off in Settings.
- **Running process names** — in the desktop version only, to attribute traffic
  to applications. The Microsoft Store version does not do this.

None of it is transmitted. It goes into the local database described above.

## Children

NetVitals is a utility with no social features, no content, and no data
collection. It is not directed at children, and collects nothing from anyone.

## Changes

This policy is versioned with the application in its public source repository,
so any change to it is visible in the commit history.

## Contact

Questions or concerns: open an issue at
<https://github.com/zimba7768/NetVitals/issues>.
