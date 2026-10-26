#!/usr/bin/env python3
"""Coding-agent hook -> PiHub agent monitor.

Reads the hook's JSON from stdin, keeps only the event name, tool name and a
short summary (never file contents or prompts), and posts it to PiHub with a
1-second timeout. Always exits 0 and prints nothing, so it can't slow down or
block the agent.

  report_event.py --agent claude-code     (Claude Code hook command)
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def summarize(tool, ti):
    if not isinstance(ti, dict):
        return None
    for key in ("command", "file_path", "path", "pattern", "url", "query", "description", "skill"):
        v = ti.get(key)
        if isinstance(v, str) and v:
            v = " ".join(v.split())
            if key == "file_path" or key == "path":
                v = os.path.basename(v.rstrip("/")) or v
            return v[:120]
    return None


def main():
    try:
        agent = sys.argv[sys.argv.index("--agent") + 1] if "--agent" in sys.argv else "agent"
        data = json.loads(sys.stdin.read() or "{}")
        from pihub_client import load_config
        cfg = load_config()
        event = data.get("hook_event_name") or data.get("event")
        tool = data.get("tool_name")
        summary = summarize(tool, data.get("tool_input"))
        if event == "Notification":
            summary = (data.get("message") or "Needs your attention")[:120]
        body = {"device": cfg["device"], "agent": agent, "session": (data.get("session_id") or "")[:80],
                "event": event, "tool": tool, "summary": summary,
                "cwd": os.path.basename((data.get("cwd") or "").rstrip("/"))}
        req = urllib.request.Request(cfg["hub_url"] + "/api/agent-events", data=json.dumps(body).encode(),
                                     method="POST", headers={"X-Token": cfg["token"], "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=1).read()
    except Exception:
        pass  # monitoring must never get in the agent's way


if __name__ == "__main__":
    main()
    sys.exit(0)
