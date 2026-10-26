"use strict";

var $ = function (id) { return document.getElementById(id); };
var rowsEl = $("rows");
var cwd = "";                 // current folder, relative to the cloud root
var entries = [];
var sort = { key: "name", dir: 1 };
var filter = "";
var editing = null;           // { kind: "new" | "rename" | "delete", name }
var loadSeq = 0;

// ---------- helpers ----------
function esc(s) {
  return String(s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}
function join(dir, name) { return dir ? dir + "/" + name : name; }
function fmtSize(n) {
  if (n < 1024) return n + " B";
  var u = ["KB", "MB", "GB", "TB"], i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < u.length - 1);
  return (n < 10 ? n.toFixed(1) : Math.round(n)) + " " + u[i];
}
var rtf = window.Intl && Intl.RelativeTimeFormat ? new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }) : null;
function fmtAgo(sec) {
  var diff = sec - Date.now() / 1000, abs = Math.abs(diff);
  var steps = [[60, "second"], [3600, "minute"], [86400, "hour"], [604800, "day"], [2629800, "week"], [31557600, "month"], [Infinity, "year"]];
  var div = [1, 60, 3600, 86400, 604800, 2629800, 31557600];
  for (var i = 0; i < steps.length; i++) {
    if (abs < steps[i][0]) {
      if (i === 0) return "just now";
      return rtf ? rtf.format(Math.round(diff / div[i]), steps[i][1]) : new Date(sec * 1000).toLocaleDateString();
    }
  }
}
function fullDate(sec) { return new Date(sec * 1000).toLocaleString(); }

var KINDS = {
  image: /\.(jpe?g|png|gif|webp|avif|heic|svg|bmp)$/i,
  audio: /\.(mp3|m4a|flac|wav|ogg|opus|aac)$/i,
  video: /\.(mp4|mkv|webm|mov|avi)$/i,
  archive: /\.(zip|tar|gz|tgz|xz|7z|rar|bz2|zst)$/i,
  code: /\.(py|js|ts|jsx|tsx|c|h|cpp|java|rs|go|rb|sh|html|css|json|sql|asm)$/i,
  doc: /\.(pdf|txt|md|docx?|odt|rtf|xlsx?|csv|pptx?)$/i
};
function kind(e) {
  if (e.dir) return "folder";
  for (var k in KINDS) if (KINDS[k].test(e.name)) return k;
  return "file";
}
// Files the browser can show itself open in a new tab; others download.
var VIEWABLE = /\.(jpe?g|png|gif|webp|avif|svg|bmp|pdf|txt|md|mp3|m4a|wav|ogg|opus|flac|mp4|webm|mov|json|csv|py|js|css|html|sh|c|h)$/i;

var toastTimer;
function toast(msg, isError) {
  var t = $("toast");
  t.textContent = msg;
  t.classList.toggle("error", !!isError);
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function () { t.classList.remove("show"); }, isError ? 5000 : 2600);
}

function api(url, opts) {
  return fetch(url, opts).then(function (r) {
    return r.json().catch(function () { return {}; }).then(function (d) {
      if (!r.ok) throw new Error(d.error || ("The Pi answered " + r.status + "."));
      return d;
    });
  }, function () { throw new Error("Can't reach the Pi. Check that you're on the home Wi-Fi."); });
}

// ---------- navigation (folder lives in the URL hash so Back works) ----------
function pathFromHash() {
  var h = location.hash.replace(/^#\/?/, "");
  try { return decodeURIComponent(h).replace(/\/+$/, ""); } catch (e) { return ""; }
}
function go(path) {
  var h = "#/" + path.split("/").map(encodeURIComponent).join("/");
  if (!path) h = "#/";
  if (location.hash === h) load(); else location.hash = h;
}
window.addEventListener("hashchange", load);

function load() {
  cwd = pathFromHash();
  editing = null;
  filter = ""; $("filter").value = "";
  renderCrumbs();
  renderSkeleton();
  var seq = ++loadSeq;
  api("/api/list?path=" + encodeURIComponent(cwd)).then(function (d) {
    if (seq !== loadSeq) return;
    entries = d.entries;
    render();
  }).catch(function (err) {
    if (seq !== loadSeq) return;
    entries = [];
    rowsEl.innerHTML = '<div class="empty"><svg class="icon" aria-hidden="true"><use href="#i-folder"/></svg>' +
      "<h2>Couldn’t open this folder</h2><p>" + esc(err.message) + "</p>" +
      '<button class="btn" type="button" data-act="home">Go to Home</button></div>';
    $("summary").textContent = "";
  });
  loadUsage();
}

function loadUsage() {
  api("/api/usage").then(function (u) {
    var pct = u.total ? u.used / u.total : 0;
    $("usage").hidden = false;
    $("usage").classList.toggle("full", pct > 0.9);
    $("usageFill").style.width = (pct * 100).toFixed(1) + "%";
    $("usageText").textContent = fmtSize(u.free) + " free of " + fmtSize(u.total);
  }).catch(function () { $("usage").hidden = true; });
}

// ---------- rendering ----------
function renderCrumbs() {
  var parts = cwd ? cwd.split("/") : [];
  var h = "", acc = "";
  var chev = '<svg class="icon" aria-hidden="true"><use href="#i-chev"/></svg>';
  if (!parts.length) h = '<span class="here" aria-current="page">Home</span>';
  else h = '<a href="#/" data-go="">Home</a>';
  parts.forEach(function (p, i) {
    acc = join(acc, p);
    h += chev + (i === parts.length - 1
      ? '<span class="here" aria-current="page" title="' + esc(p) + '">' + esc(p) + "</span>"
      : '<a href="#" data-go="' + esc(acc) + '" title="' + esc(p) + '">' + esc(p) + "</a>");
  });
  $("crumbs").innerHTML = h;
  $("dropTarget").textContent = parts.length ? parts[parts.length - 1] : "Home";
  document.title = (parts.length ? parts[parts.length - 1] + " · " : "") + "picloud";
}

function renderSkeleton() {
  var h = "";
  for (var i = 0; i < 6; i++) h += '<div class="skel" aria-hidden="true"><b></b><b style="width:' + (35 + (i * 23) % 45) + '%"></b><b></b><b></b><b></b></div>';
  rowsEl.innerHTML = h;
}

function sorted() {
  var q = filter.trim().toLowerCase();
  var list = entries.filter(function (e) { return !q || e.name.toLowerCase().indexOf(q) !== -1; });
  return list.sort(function (a, b) {
    if (a.dir !== b.dir) return a.dir ? -1 : 1;  // folders always first
    var x = a[sort.key], y = b[sort.key];
    var c = sort.key === "name" ? x.localeCompare(y, undefined, { numeric: true, sensitivity: "base" }) : x - y;
    return c * sort.dir;
  });
}

function nameCell(e) {
  var path = join(cwd, e.name);
  var k = kind(e);
  var sub = e.dir ? fmtAgo(e.mtime) : fmtSize(e.size) + " · " + fmtAgo(e.mtime);
  var inner = '<svg class="icon" aria-hidden="true"><use href="#i-' + k + '"/></svg>' +
    '<span class="name-text"><span>' + esc(e.name) + '</span><small class="sub">' + esc(sub) + "</small></span>";
  if (e.dir) return '<a class="name is-dir" href="#" data-go="' + esc(path) + '">' + inner + "</a>";
  var viewable = VIEWABLE.test(e.name);
  var href = "/download?path=" + encodeURIComponent(path) + (viewable ? "&inline=1" : "");
  return '<a class="name" href="' + href + '"' + (viewable ? ' target="_blank" rel="noopener"' : "") +
    ' title="' + (viewable ? "Open " : "Download ") + esc(e.name) + '">' + inner + "</a>";
}

function rowHTML(e) {
  var path = join(cwd, e.name);
  if (editing && editing.name === e.name && editing.kind === "rename") {
    return '<div class="tr editing" role="row"><div class="edit">' +
      '<svg class="icon" aria-hidden="true"><use href="#i-' + kind(e) + '"/></svg>' +
      '<input id="editInput" value="' + esc(e.name) + '" aria-label="New name for ' + esc(e.name) + '"></div>' +
      '<div class="row-actions"><button class="btn small" type="button" data-act="cancel">Cancel</button>' +
      '<button class="btn small primary" type="button" data-act="save">Rename</button></div></div>';
  }
  if (editing && editing.name === e.name && editing.kind === "delete") {
    return '<div class="tr confirming" role="row"><div class="confirm-text">Delete <b>' + esc(e.name) + "</b>" +
      (e.dir ? " and everything inside it" : "") + "?</div>" +
      '<div class="row-actions"><button class="btn small" type="button" data-act="cancel">Cancel</button>' +
      '<button class="btn small danger" type="button" data-act="confirm-delete">Delete</button></div></div>';
  }
  return '<div class="tr" role="row">' +
    '<div role="cell">' + nameCell(e) + "</div>" +
    '<div class="cell-size" role="cell">' + (e.dir ? "—" : fmtSize(e.size)) + "</div>" +
    '<div class="cell-date" role="cell" title="' + esc(fullDate(e.mtime)) + '">' + fmtAgo(e.mtime) + "</div>" +
    '<div class="c-act" role="cell">' +
      (e.dir ? "" : '<a class="icon-btn" href="/download?path=' + encodeURIComponent(path) + '" aria-label="Download ' + esc(e.name) + '"><svg class="icon" aria-hidden="true"><use href="#i-download"/></svg></a>') +
      '<button class="icon-btn ren" type="button" data-act="rename" data-name="' + esc(e.name) + '" aria-label="Rename ' + esc(e.name) + '"><svg class="icon" aria-hidden="true"><use href="#i-pencil"/></svg></button>' +
      '<button class="icon-btn del" type="button" data-act="delete" data-name="' + esc(e.name) + '" aria-label="Delete ' + esc(e.name) + '"><svg class="icon" aria-hidden="true"><use href="#i-trash"/></svg></button>' +
    "</div></div>";
}

function render() {
  var list = sorted();
  var h = "";
  if (editing && editing.kind === "new") {
    h += '<div class="tr editing" role="row"><div class="edit">' +
      '<svg class="icon" aria-hidden="true"><use href="#i-folder"/></svg>' +
      '<input id="editInput" placeholder="Folder name" aria-label="New folder name"></div>' +
      '<div class="row-actions"><button class="btn small" type="button" data-act="cancel">Cancel</button>' +
      '<button class="btn small primary" type="button" data-act="create">Create</button></div></div>';
  }
  if (!entries.length && !h) {
    h = '<div class="empty"><svg class="icon" aria-hidden="true"><use href="#i-upload"/></svg>' +
      "<h2>This folder is empty</h2><p>Drop files anywhere on this page, or use Upload files. Anything you add here is reachable from every device on your Wi-Fi.</p></div>";
  } else if (!list.length && !h) {
    h = '<div class="empty"><h2>No matches</h2><p>Nothing in this folder matches “' + esc(filter.trim()) + "”.</p></div>";
  } else {
    h += list.map(rowHTML).join("");
  }
  rowsEl.innerHTML = h;

  var dirs = entries.filter(function (e) { return e.dir; }).length;
  var files = entries.length - dirs;
  var bytes = entries.reduce(function (s, e) { return s + e.size; }, 0);
  $("summary").textContent = entries.length
    ? [dirs ? dirs + (dirs === 1 ? " folder" : " folders") : "", files ? files + (files === 1 ? " file" : " files") + " · " + fmtSize(bytes) : ""].filter(Boolean).join(", ")
    : "";

  document.querySelectorAll(".th").forEach(function (th) {
    var b = th.querySelector("button");
    if (b && b.dataset.sort === sort.key) th.setAttribute("aria-sort", sort.dir > 0 ? "ascending" : "descending");
    else th.removeAttribute("aria-sort");
  });

  var input = $("editInput");
  if (input) {
    input.focus();
    if (editing.kind === "rename") {
      var dot = input.value.lastIndexOf(".");
      input.setSelectionRange(0, dot > 0 ? dot : input.value.length);
    }
  }
}

// ---------- actions ----------
function post(url) { return api(url, { method: "POST" }); }

function createFolder() {
  var name = $("editInput").value.trim();
  if (!name) return $("editInput").focus();
  post("/mkdir?path=" + encodeURIComponent(join(cwd, name)))
    .then(function () { toast("Created " + name); editing = null; refresh(); })
    .catch(function (err) { toast(err.message, true); });
}

function renameEntry() {
  var from = editing.name, to = $("editInput").value.trim();
  if (!to || to === from) { editing = null; return render(); }
  post("/rename?path=" + encodeURIComponent(join(cwd, from)) + "&to=" + encodeURIComponent(to))
    .then(function () { toast("Renamed to " + to); editing = null; refresh(); })
    .catch(function (err) { toast(err.message, true); });
}

function deleteEntry() {
  var name = editing.name;
  post("/delete?path=" + encodeURIComponent(join(cwd, name)))
    .then(function () { toast("Deleted " + name); editing = null; refresh(); })
    .catch(function (err) { toast(err.message, true); });
}

function refresh() {
  api("/api/list?path=" + encodeURIComponent(cwd)).then(function (d) { entries = d.entries; render(); loadUsage(); })
    .catch(function (err) { toast(err.message, true); });
}

// ---------- uploads (XHR so we get progress) ----------
var uploading = 0, trayTimer;
function uploadFiles(fileList) {
  var files = Array.prototype.slice.call(fileList);
  if (!files.length) return;
  var target = cwd;
  var tray = $("tray"), list = $("trayList");
  clearTimeout(trayTimer);
  tray.hidden = false;
  var items = files.map(function (f) {
    var li = document.createElement("li");
    li.innerHTML = '<div class="tray-row"><span></span><span>Waiting</span></div><div class="prog"><span></span></div>';
    li.querySelector("span").textContent = f.webkitRelativePath || f.name;
    list.appendChild(li);
    return li;
  });
  uploading += files.length;
  updateTrayTitle();

  var i = 0;
  (function next() {
    if (i >= files.length) {
      if (target === cwd) refresh();
      return;
    }
    var f = files[i], li = items[i++];
    var status = li.querySelector(".tray-row span:last-child"), bar = li.querySelector(".prog span");
    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/upload?path=" + encodeURIComponent(join(target, f.webkitRelativePath || f.name)));
    xhr.upload.onprogress = function (e) {
      if (!e.lengthComputable) return;
      var p = e.loaded / e.total;
      bar.style.width = (p * 100).toFixed(1) + "%";
      status.textContent = Math.floor(p * 100) + "%";
    };
    xhr.onload = function () {
      if (xhr.status >= 200 && xhr.status < 300) {
        li.classList.add("done"); bar.style.width = "100%"; status.textContent = fmtSize(f.size);
      } else {
        var msg = "Failed";
        try { msg = JSON.parse(xhr.responseText).error || msg; } catch (e) {}
        li.classList.add("failed"); status.textContent = "Failed"; li.title = msg;
        toast(f.name + ": " + msg, true);
      }
      finish();
    };
    xhr.onerror = function () {
      li.classList.add("failed"); status.textContent = "Failed";
      toast("Lost the connection while uploading " + f.name + ".", true);
      finish();
    };
    status.textContent = "0%";
    xhr.send(f);
    function finish() { uploading--; updateTrayTitle(); next(); }
  })();
}

function updateTrayTitle() {
  var failed = $("trayList").querySelectorAll(".failed").length;
  if (uploading > 0) $("trayTitle").textContent = "Uploading " + uploading + (uploading === 1 ? " file" : " files");
  else {
    $("trayTitle").textContent = failed ? failed + " upload" + (failed === 1 ? "" : "s") + " failed" : "Uploads finished";
    if (!failed) trayTimer = setTimeout(hideTray, 4000);
  }
}
function hideTray() { if (uploading) return; $("tray").hidden = true; $("trayList").innerHTML = ""; }

// ---------- events ----------
document.addEventListener("click", function (e) {
  var g = e.target.closest("[data-go]");
  if (g) { e.preventDefault(); go(g.dataset.go); return; }
  var b = e.target.closest("[data-act]");
  if (!b) return;
  var act = b.dataset.act;
  if (act === "rename" || act === "delete") { editing = { kind: act, name: b.dataset.name }; render(); }
  else if (act === "cancel") { editing = null; render(); }
  else if (act === "create") createFolder();
  else if (act === "save") renameEntry();
  else if (act === "confirm-delete") deleteEntry();
  else if (act === "home") go("");
});

rowsEl.addEventListener("keydown", function (e) {
  if (e.target.id !== "editInput") return;
  if (e.key === "Enter") { e.preventDefault(); editing.kind === "new" ? createFolder() : renameEntry(); }
  if (e.key === "Escape") { editing = null; render(); }
});

document.querySelector(".thead").addEventListener("click", function (e) {
  var b = e.target.closest("[data-sort]");
  if (!b) return;
  if (sort.key === b.dataset.sort) sort.dir = -sort.dir;
  else sort = { key: b.dataset.sort, dir: b.dataset.sort === "name" ? 1 : -1 };
  render();
});

$("filter").addEventListener("input", function (e) { filter = e.target.value; render(); });
$("newFolder").addEventListener("click", function () { editing = { kind: "new" }; window.scrollTo(0, 0); render(); });
$("pickFiles").addEventListener("click", function () { $("fileInput").click(); });
$("pickFolder").addEventListener("click", function () { $("folderInput").click(); });
$("fileInput").addEventListener("change", function (e) { uploadFiles(e.target.files); e.target.value = ""; });
$("folderInput").addEventListener("change", function (e) { uploadFiles(e.target.files); e.target.value = ""; });
$("trayClose").addEventListener("click", hideTray);

// Whole-window drag and drop. A counter handles dragenter/leave firing on children.
var dragDepth = 0;
function hasFiles(e) { return e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, "Files") !== -1; }
window.addEventListener("dragenter", function (e) { if (!hasFiles(e)) return; e.preventDefault(); dragDepth++; $("dropzone").hidden = false; });
window.addEventListener("dragover", function (e) { if (hasFiles(e)) e.preventDefault(); });
window.addEventListener("dragleave", function () { if (--dragDepth <= 0) { dragDepth = 0; $("dropzone").hidden = true; } });
window.addEventListener("drop", function (e) {
  if (!hasFiles(e)) return;
  e.preventDefault(); dragDepth = 0; $("dropzone").hidden = true;
  uploadFiles(e.dataTransfer.files);
});

document.addEventListener("keydown", function (e) {
  var typing = e.target.tagName === "INPUT";
  if (e.key === "Escape" && typing && e.target.id === "filter") { e.target.value = ""; filter = ""; render(); e.target.blur(); return; }
  if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === "/") { e.preventDefault(); $("filter").focus(); }
  else if (e.key === "Backspace" && cwd) { e.preventDefault(); go(cwd.split("/").slice(0, -1).join("/")); }
});

load();
