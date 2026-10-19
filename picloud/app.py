#!/usr/bin/env python3
"""picloud - a tiny, dependency-free web file cloud.

Serves a single-page UI over the files in CLOUD_ROOT so you can upload from
one device and download from another on the same network.
"""
import json
import mimetypes
import os
import shutil
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.abspath(os.environ.get("CLOUD_ROOT", "/home/soumil/cloud"))
PORT = int(os.environ.get("CLOUD_PORT", "80"))
BIND = os.environ.get("CLOUD_BIND", "0.0.0.0")
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(ROOT, exist_ok=True)


def safe_path(rel):
    rel = (rel or "").replace("\\", "/").strip().lstrip("/")
    p = os.path.abspath(os.path.join(ROOT, rel))
    if p != ROOT and not p.startswith(ROOT + os.sep):
        raise ValueError("path escapes root")
    return p


def list_dir(rel):
    d = safe_path(rel)
    if not os.path.isdir(d):
        raise ValueError("not a directory")
    entries = []
    with os.scandir(d) as it:
        for e in it:
            try:
                st = e.stat()
            except OSError:
                continue
            entries.append({
                "name": e.name,
                "dir": e.is_dir(),
                "size": 0 if e.is_dir() else st.st_size,
                "mtime": int(st.st_mtime),
            })
    entries.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    return entries


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0f172a">
<title>picloud</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<header class="topbar">
  <div class="brand"><span class="dot"></span> picloud</div>
  <div class="actions">
    <button id="pickFiles" class="btn">Upload files</button>
    <button id="pickFolder" class="btn ghost">Upload folder</button>
    <button id="newFolder" class="btn ghost">New folder</button>
  </div>
</header>
<input type="file" id="fileInput" multiple hidden>
<input type="file" id="folderInput" webkitdirectory hidden>
<main>
  <nav id="crumbs" class="crumbs"></nav>
  <div id="drop" class="drop">
    <div class="drop-big">Drop files here</div>
    <div class="drop-sm">or click to choose files</div>
  </div>
  <div id="list" class="list"></div>
</main>
<div id="toast" class="toast"></div>
<script>
var cwd = "";
function $(s){ return document.querySelector(s); }
function esc(s){ return String(s).replace(/[&<>"']/g, function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]; }); }
function toast(msg){
  var t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(t._t); t._t = setTimeout(function(){ t.classList.remove("show"); }, 2600);
}
function fmtSize(n){
  if(!n) return "0 B";
  var u=["B","KB","MB","GB","TB"], i=0, f=n;
  while(f>=1024 && i<u.length-1){ f/=1024; i++; }
  return (i? f.toFixed(1): f)+" "+u[i];
}
function fmtDate(s){
  try{ return new Date(s*1000).toLocaleString(); }catch(e){ return ""; }
}
function load(path){
  cwd = path || "";
  fetch("/api/list?path="+encodeURIComponent(cwd)).then(function(r){ return r.json(); })
  .then(function(d){
    if(d.error){ toast(d.error); return; }
    renderCrumbs(cwd); renderList(d.entries);
  });
}
function renderCrumbs(path){
  var parts = path ? path.split("/") : [], acc = "";
  var h = '<a data-path="" href="#">home</a>';
  for(var i=0;i<parts.length;i++){
    acc = acc ? acc+"/"+parts[i] : parts[i];
    h += ' <span class="sep">/</span> <a data-path="'+esc(acc)+'" href="#">'+esc(parts[i])+'</a>';
  }
  var c = $("#crumbs"); c.innerHTML = h;
  c.querySelectorAll("a").forEach(function(a){
    a.onclick = function(e){ e.preventDefault(); load(a.dataset.path); };
  });
}
function renderList(entries){
  var el = $("#list");
  if(!entries.length){ el.innerHTML = '<div class="empty">This folder is empty.</div>'; return; }
  var h = "";
  entries.forEach(function(e){
    var p = cwd ? cwd+"/"+e.name : e.name;
    var icon = e.dir ? "\uD83D\uDCC1" : "\uD83D\uDCC4";
    var nameCell = e.dir
      ? '<a class="name" data-dir="'+esc(p)+'" href="#">'+icon+' <span>'+esc(e.name)+'</span></a>'
      : '<a class="name" href="/download?path='+encodeURIComponent(p)+'">'+icon+' <span>'+esc(e.name)+'</span></a>';
    h += '<div class="row">'+nameCell
      + '<div class="meta">'+(e.dir? "folder" : fmtSize(e.size))+' &middot; '+fmtDate(e.mtime)+'</div>'
      + '<button class="del" data-del="'+esc(p)+'" title="Delete">&#10005;</button></div>';
  });
  el.innerHTML = h;
  el.querySelectorAll("[data-dir]").forEach(function(a){
    a.onclick = function(ev){ ev.preventDefault(); load(a.dataset.dir); };
  });
  el.querySelectorAll("[data-del]").forEach(function(b){
    b.onclick = function(){
      var p = b.dataset.del;
      if(!confirm("Delete \""+p+"\" ?")) return;
      fetch("/delete?path="+encodeURIComponent(p), {method:"POST"})
        .then(function(r){ return r.json(); })
        .then(function(d){ if(d.error) toast(d.error); load(cwd); });
    };
  });
}
function uploadFiles(files){
  var arr = Array.prototype.slice.call(files);
  if(!arr.length) return;
  var done = 0;
  function next(i){
    if(i >= arr.length){ toast("Uploaded "+done+" file(s)"); load(cwd); return; }
    var f = arr[i];
    var rel = (cwd ? cwd+"/" : "") + (f.webkitRelativePath || f.name);
    fetch("/upload?path="+encodeURIComponent(rel), {method:"POST", body:f})
      .then(function(){ done++; toast("Uploading "+(i+1)+"/"+arr.length); next(i+1); })
      .catch(function(){ toast("Failed: "+f.name); next(i+1); });
  }
  next(0);
}
$("#pickFiles").onclick = function(){ $("#fileInput").click(); };
$("#pickFolder").onclick = function(){ $("#folderInput").click(); };
$("#fileInput").onchange = function(e){ uploadFiles(e.target.files); e.target.value=""; };
$("#folderInput").onchange = function(e){ uploadFiles(e.target.files); e.target.value=""; };
$("#newFolder").onclick = function(){
  var n = prompt("New folder name:");
  if(!n) return;
  var p = cwd ? cwd+"/"+n : n;
  fetch("/mkdir?path="+encodeURIComponent(p), {method:"POST"})
    .then(function(r){ return r.json(); })
    .then(function(d){ if(d.error) toast(d.error); load(cwd); });
};
var drop = $("#drop");
drop.onclick = function(){ $("#fileInput").click(); };
["dragenter","dragover"].forEach(function(ev){
  drop.addEventListener(ev, function(e){ e.preventDefault(); drop.classList.add("over"); });
});
["dragleave","drop"].forEach(function(ev){
  drop.addEventListener(ev, function(e){ e.preventDefault(); drop.classList.remove("over"); });
});
drop.addEventListener("drop", function(e){ uploadFiles(e.dataTransfer.files); });
load("");
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "picloud/1.0"

    def _send(self, code, ctype, body, extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _json(self, code, obj):
        self._send(code, "application/json; charset=utf-8", json.dumps(obj))

    def _err(self, code, msg):
        self._json(code, {"error": msg})

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE)
        elif u.path == "/style.css":
            try:
                with open(os.path.join(HERE, "style.css"), "rb") as f:
                    self._send(200, "text/css; charset=utf-8", f.read())
            except OSError:
                self._send(200, "text/css; charset=utf-8", b"")
        elif u.path == "/api/list":
            try:
                rel = q.get("path", [""])[0]
                self._json(200, {"path": rel, "entries": list_dir(rel)})
            except Exception as e:
                self._err(400, str(e))
        elif u.path == "/download":
            self._download(q.get("path", [""])[0])
        else:
            self._err(404, "not found")

    def _download(self, rel):
        try:
            fp = safe_path(rel)
            if not os.path.isfile(fp):
                self._err(404, "not found")
                return
            size = os.path.getsize(fp)
            name = os.path.basename(fp).replace('"', "").replace("\\", "")
            ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % name)
            self.end_headers()
            with open(fp, "rb") as f:
                shutil.copyfileobj(f, self.wfile, 1 << 16)
        except BrokenPipeError:
            pass
        except Exception as e:
            self._err(400, str(e))

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            if u.path == "/upload":
                self._upload(q.get("path", [""])[0], length)
            elif u.path == "/mkdir":
                os.makedirs(safe_path(q.get("path", [""])[0]), exist_ok=True)
                self._json(200, {"ok": True})
            elif u.path == "/delete":
                fp = safe_path(q.get("path", [""])[0])
                if fp == ROOT:
                    self._err(400, "cannot delete root")
                    return
                if os.path.isdir(fp):
                    shutil.rmtree(fp)
                elif os.path.exists(fp):
                    os.remove(fp)
                self._json(200, {"ok": True})
            else:
                self._err(404, "not found")
        except Exception as e:
            self._err(400, str(e))

    def _upload(self, rel, length):
        fp = safe_path(rel)
        parent = os.path.dirname(fp)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = fp + ".part"
        remaining = length
        with open(tmp, "wb") as f:
            while remaining > 0:
                chunk = self.rfile.read(min(1 << 16, remaining))
                if not chunk:
                    break
                f.write(chunk)
                remaining -= len(chunk)
        os.replace(tmp, fp)
        self._json(200, {"ok": True, "path": rel, "bytes": length})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer((BIND, PORT), Handler)
    print("picloud serving %s on %s:%d" % (ROOT, BIND, PORT), flush=True)
    srv.serve_forever()
