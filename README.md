# Live TV 📺

A fast, searchable **browser player for live TV** — watch 16,900+ free IPTV
channels from around the world. Search by name, filter by country or category,
and it opens straight to the channels that actually play.

## Quick start

```bash
python3 server.py
```

Then open **<http://localhost:8777/>**.

No build step — the channel catalog (`data.json`) is prebuilt and included.
Python 3 only; `pip3 install PySocks` if you want SOCKS5 region proxies.

## Features

- **16,900+ channels** with logos, quality tags, and country flags.
- **Search-first** UI, plus **country** and **category** filters (News, Movies,
  Sports, Kids, Music…).
- **Playable-only by default** — availability is probed live; toggle between
  `All` · `Working first` (dead streams dimmed) · `Playable only`.
- **Built-in HLS proxy** — adds CORS, rewrites `.m3u8` manifests, and sends each
  stream's own `User-Agent`/`Referer`, so far more streams play in the browser.
- **Region proxies** — map a per-country HTTP/SOCKS5 proxy in ⚙ to view
  geo-locked channels from that country.
- **Immersive player** — fills the screen, true fullscreen (`F`), and **← / →**
  to zap between channels.

| Key | Action |
|-----|--------|
| `←` / `→` | Previous / next channel |
| `F` | Fullscreen |
| `Esc` | Close player |

## Files

| File | Purpose |
|------|---------|
| `index.html` | The single-page player (HTML/CSS/JS, hls.js) |
| `server.py` | Static server + HLS proxy + availability probe |
| `iptv_core.py` | Request handler: proxy, `/config`, `/check` |
| `data.json` | Prebuilt channel catalog (16,879 streams) |

## Notes & credits

- Geo-locked channels need a proxy **located in that country** (the proxy runs on
  your machine, so it shares your IP).
- "Playable only" reflects reachability at check time; a stream can pass the probe
  yet still stall on playback.
- Channel data and streams come from the **[iptv-org](https://github.com/iptv-org/iptv)**
  project — all streams are publicly available and provided by their respective
  owners. This player only consumes iptv-org's public playlists/API.
