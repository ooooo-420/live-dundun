# 直播蹲蹲 · Live Dundun

A Douyin live-shopping room lists one or two hundred products. The host explains them one by one, and if you want number 37 you have to keep watching until it comes up. This tool watches for you: set the numbers you want on your phone, and WeChat tells you the moment the host gets there.

This is the first project I designed from scratch. I set the requirements and tested every piece on real streams; Claude Code wrote the code.

[Portfolio](https://ooooo-420.github.io/blackhole-memory-relay/)

## How it works

```
iPhone (WeChat mini program)  ──commands──▶  WeChat Cloud DB  ◀──sync──  PC (Python + Edge)
        set targets, on/off                   rooms, carts,                reads the Douyin
        see what's being explained            commands, heartbeat          live page every 4 s
                                                    │
                                              watchdog (timer)
                                                    │
        ◀────────────── WeChat template message ────┴────────────────────  "No. 37 is up"
```

1. **PC** opens the live room in a dedicated Edge profile (Playwright), reads the product list and the "explaining now" card from the page's React data, and tracks products by ID, not by number.
2. **Mini program** adds rooms (paste a share link), picks target numbers, and switches monitoring on or off. It never talks to Douyin; it only writes commands to the cloud database, and the PC picks them up every 15 s.
3. **Notification** goes out as a WeChat template message, with retries, plus an optional Bark push for the lock screen.
4. **Watchdog** is a cloud function on a 5-minute timer. If the PC stops sending heartbeats, it messages you, because a dead PC cannot tell you it is dead.

## Things I learned on real streams

- **Product numbers are positions, not IDs.** In some rooms the product being explained is pinned to No. 1 and everything else shifts (type A); in others the numbers stay put (type B). The tool detects which type a room is and tracks the product ID you chose, so "No. 37" still means the jeans you picked after the list reorders.
- **The cart only loads 20 at a time.** Scrolling to the bottom loads the rest; a room with 104 products was read completely with no duplicate numbers.
- **"Skipped" is not always skipped.** A host jumping from No. 1 to No. 8 is not skipping No. 4; the missed-product alert only fires when the host is clearly going in order.
- **Captchas are solved by a person.** When Douyin shows a slider, the program pauses, tells you on WeChat, and waits. It does not try to solve or hide from it.
- **The same command ran 370 times.** A cloud update on a `null` field failed silently, so the command was never marked done. The fix was `_.set`, reporting errors back, and deduplicating on the PC.

## Files

| Path | Purpose |
|---|---|
| `run.py`, `start.bat`, `stop.bat` | Start and stop the monitor |
| `login.py` | Log in to Douyin once in the dedicated Edge profile |
| `app/douyin.py` | Reads the live page: cart, explaining card, captcha, login wall |
| `app/monitor.py` | One worker per room, A/B type detection, target tracking, Edge relaunch |
| `app/rules.py` | When to notify: on arrival, N products ahead, missed |
| `app/notify.py` | WeChat template message and Bark, with retries |
| `app/cloud.py` | Sync with the cloud function; resolves `v.douyin.com` share links |
| `app/web.py` | Local settings page on `127.0.0.1:8765` |
| `miniprogram/` | WeChat mini program (pages: rooms, room, members) |
| `miniprogram/cloudfunctions/api` | The only path to the database; members and invite codes |
| `miniprogram/cloudfunctions/watchdog` | Offline alert on a timer |
| `tests/` | Rules, sync and notification tests (no network, no browser) |
| `design/avatar` | The mini program icon, drawn in HTML and rendered with headless Edge |

## Running it yourself

You need Python 3.12+, Microsoft Edge, a WeChat sandbox account (接口测试号) for template messages, and a WeChat mini program with cloud development enabled.

1. `python -m venv .venv` and install `requests`, `playwright`, `aiohttp`.
2. Copy `config.example.json` to `config.local.json` and fill it in, or run `set_miniprogram.bat` and `set_openid.bat`. In `miniprogram/`, copy `project.config.example.json` to `project.config.json` and `utils/config.example.js` to `utils/config.js`, and put your own AppID and cloud environment ID in them.
3. Deploy `cloudfunctions/api` and `cloudfunctions/watchdog` from WeChat DevTools, and upload the watchdog's timer trigger.
4. `python login.py` once, then `start.bat`.

It has only run on Windows, in my own environment, against Douyin's web page as of November 2026. Page structure changes will break the reader.
