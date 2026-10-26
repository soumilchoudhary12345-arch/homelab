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
rsync -a --exclude client --exclude '__pycache__' pihub/ som@piscreen.local:/home/som/pihub/
ssh som@piscreen.local 'sudo cp ~/pihub/deploy/pihub*.service ~/pihub/deploy/pihub-sync.timer /etc/systemd/system/ \
  && sudo systemctl daemon-reload && sudo systemctl enable --now pihub pihub-sync.timer && sudo systemctl restart pihub'
```

## Set up a Linux PC (Arch)

```sh
# 1. Syncthing
sudo pacman -S syncthing
systemctl --user enable --now syncthing

# 2. pihub-client files + config (~/.config/pihub/client.json: device, hub_url, token, allowed_roots)
mkdir -p ~/.local/share/pihub
cp pihub/client/{pihub_client,pihub_mcp,report_event}.py ~/.local/share/pihub/

# 3. run it now and at every login, plus the 4-day fallback timer
cp pihub/client/linux/pihub-* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pihub-client.service pihub-sync-fallback.timer

# 4. pair Syncthing with the Pi (asks for the Pi password only if your ssh key isn't set up)
python3 pihub/setup/pair_syncthing.py

# 5. give your agents the tools
claude mcp add pihub -s user -- python3 ~/.local/share/pihub/pihub_mcp.py
```

Agent monitor hooks for Claude Code go in `~/.claude/settings.json` (see the top-level homelab notes).

## Set up a Windows PC

1. Install Python 3 (tick "Add python.exe to PATH") and Syncthing.
2. In PowerShell, from `pihub\client\windows`:
   `powershell -ExecutionPolicy Bypass -File install.ps1 -Device win-pc -Token <PIHUB_TOKEN>`
3. `py ..\..\setup\pair_syncthing.py`

## Safety rules

* Each PC only shares folders in its `allowed_roots`; `.ssh`, `.gnupg`, `.env`, `API Keys.md` and private keys are always refused.
* The Pi keeps copies (Receive Only + Staggered versioning); deleting on a PC never destroys the Pi's copy.
* The Pi's firewall (ufw) only accepts connections from 192.168.1.0/24 and IPv6 link-local.

## Tests

`python3 -m unittest pihub/test_app.py`
