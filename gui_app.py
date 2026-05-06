"""
GUI-сервер SiteTester.
Запускает локальный веб-сервер и открывает браузер с интерфейсом.
"""
import asyncio
import json
import queue
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file

from sitetester.config import Config
from sitetester import runner as _runner

app = Flask(__name__, template_folder="gui_templates")

_log_q: queue.Queue = queue.Queue()
_state: dict = {
    "running": False,
    "done": False,
    "report_path": None,
    "error": None,
}


# ── Перехват вывода print() → очередь логов ──────────────────────────────────

class _LogCapture:
    def __init__(self):
        self._orig = sys.stdout
        self._buf  = ""

    def write(self, text: str):
        self._orig.write(text)
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                _log_q.put({"type": "log", "text": line})

    def flush(self):
        self._orig.flush()
        if self._buf.strip():
            _log_q.put({"type": "log", "text": self._buf})
            self._buf = ""


# ── Фоновый поток для запуска проверки ───────────────────────────────────────

def _run_check(config: Config) -> None:
    _state.update(running=True, done=False, error=None, report_path=None)
    orig = sys.stdout
    sys.stdout = _LogCapture()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_runner.run(config))
        loop.close()
        rp = config.output_dir / "report.html"
        _state["report_path"] = str(rp.resolve()) if rp.exists() else None
    except Exception as exc:
        _state["error"] = str(exc)
        _log_q.put({"type": "error", "text": f"Ошибка: {exc}"})
    finally:
        sys.stdout = orig
        _state["running"] = False
        _state["done"]    = True
        _log_q.put({"type": "done", "text": "✅ Проверка завершена"})


# ── Flask-маршруты ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("gui.html")


@app.route("/start", methods=["POST"])
def start():
    if _state["running"]:
        return jsonify({"error": "Проверка уже выполняется"}), 400

    d = request.get_json(force=True)
    if not d.get("original_url") or not d.get("mirror_url"):
        return jsonify({"error": "Укажите оба URL"}), 400

    config = Config(
        original_url      = d["original_url"].rstrip("/"),
        mirror_url        = d["mirror_url"].rstrip("/"),
        output_dir        = Path(d.get("output_dir") or "output"),
        mode              = d.get("mode", "both"),
        max_pages         = int(d.get("max_pages", 50)),
        exclude_selectors = [s.strip() for s in d.get("exclude", "").splitlines() if s.strip()],
        diff_threshold    = float(d.get("threshold", 8.0)),
        blur_radius       = int(d.get("blur", 4)),
        pixel_sensitivity = int(d.get("sensitivity", 25)),
        check_mobile      = bool(d.get("check_mobile", True)),
    )

    # Очищаем старые логи
    while not _log_q.empty():
        try:
            _log_q.get_nowait()
        except queue.Empty:
            break

    threading.Thread(target=_run_check, args=(config,), daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/logs")
def logs():
    """SSE-поток логов в реальном времени."""
    def generate():
        yield 'data: {"type":"connected"}\n\n'
        while True:
            try:
                msg = _log_q.get(timeout=25)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get("type") == "done":
                    break
            except queue.Empty:
                yield 'data: {"type":"ping"}\n\n'

    return Response(
        generate(),
        content_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/status")
def status():
    return jsonify(_state)


@app.route("/open_report")
def open_report():
    rp = _state.get("report_path")
    if rp and Path(rp).exists():
        webbrowser.open(Path(rp).as_uri())
        return jsonify({"ok": True})
    return jsonify({"error": "Отчёт не найден"}), 404


# ── Точка входа ───────────────────────────────────────────────────────────────

def main():
    port = 7654
    url  = f"http://localhost:{port}"
    print(f"\n🔍 SiteTester запущен: {url}\n")
    threading.Timer(1.4, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
