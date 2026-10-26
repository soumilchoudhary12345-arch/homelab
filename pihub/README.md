# PiHub

The homelab's coordinator on the Raspberry Pi (`piscreen`, 192.168.1.13, port **8899**).

| Piece | Where it runs | What it does |
|---|---|---|
| `app.py` + `index.html`/`app.js`/`style.css` | Pi, `pihub.service` | File inventory, 4-day sync rounds, file fetch relay, agent monitor, dashboard |
| `deploy/pihub-sync.timer` | Pi | Daily 02:00 check; queues a sync for every PC once 4 days have passed |
| `client/pihub_client.py` | each PC | Polls PiHub; runs syncs, sends requested files, saves fetched files |
| `client/pihub_mcp.py` | each PC | MCP tools for agents: `list_devices`, `search_files`, `request_file`, `task_status`, `sync_now` |
| `client/report_event.py` | each PC | Agent hook → `/agents` monitor (tool name + short summary only) |
| `setup/pair_syncthing.py` | each PC, once | Pairs Syncthing with the Pi and creates the folders |

Storage: `/srv/nas` (`devices/<pc>/…` synced copies, `music/`, `inbox/` in-transit files, `pihub.db`).
Token: `PIHUB_TOKEN` in `/etc/pihub.env` (root:som 640). Every `/api/*` call needs `X-Token`.

## Deploy to the Pi

```sh
rsync -a --exclude __pycache__ --exclude 'test_*.py' pihub/ som@piscreen.local:/home/som/pihub/
ssh som@piscreen.local 'sudo systemctl restart pihub'
```

PiHub serves the client files and join scripts below, so `client/`, `setup/` and `join/` must be on the Pi too.

## Add a PC (one command)

On any PC on the same Wi-Fi as the Pi. It installs Python and Syncthing if missing, sets up
pihub-client (runs at login, plus the 4-day fallback), pairs Syncthing with the Pi through
`/api/pair` (no ssh), adds the Claude Code hooks and PiHub tools, and a **Pi Agents** app.

* **Linux:** `curl -fsSL http://192.168.1.13:8899/join/linux.sh -o join-pi.sh && bash join-pi.sh`
* **Windows (PowerShell):** `irm http://192.168.1.13:8899/join/windows.ps1 | iex`

The Pi names each PC after its user (`soumil`, then `soumil-2`, `soumil-3`), remembered by
machine ID, so running the script again keeps the name. To choose a name instead:
`bash join-pi.sh my-laptop`, or on Windows `$env:PIHUB_DEVICE = "my-pc"` first.

The scripts are served with the token filled in, and `/join/*` needs no token, so anyone on the
LAN can fetch the token. That's accepted here because the Pi's firewall only allows the home LAN.

## Safety rules

* Each PC only shares folders in its `allowed_roots`; `.ssh`, `.gnupg`, `.env`, `API Keys.md` and private keys are always refused.
* The Pi keeps copies (Receive Only + Staggered versioning); deleting on a PC never destroys the Pi's copy.
* The Pi's firewall (ufw) only accepts connections from 192.168.1.0/24 and IPv6 link-local.

## Tests

`python3 -m unittest pihub/test_app.py`
