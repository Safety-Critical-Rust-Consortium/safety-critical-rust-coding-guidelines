import json
import subprocess
import sys
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

REPO_ROOT = Path(__file__).parents[3]


class WrongShapeFLSHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps({"documents": []}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        pass


@contextmanager
def wrong_shape_fls_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), WrongShapeFLSHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/paragraph-ids.json"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.integration
@pytest.mark.parametrize("enforce", [False, True], ids=["nonblocking", "enforcing"])
def test_real_sphinx_wrong_shape_policy(tmp_path: Path, enforce: bool) -> None:
    with wrong_shape_fls_server() as fls_url:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "sphinx",
                "-b",
                "html",
                "-d",
                str(tmp_path / "doctrees"),
                "-j",
                "1",
                "-E",
                "-W",
                "--keep-going",
                "--define",
                f"fls_paragraph_ids_url={fls_url}",
                "--define",
                f"enable_spec_lock_consistency={int(enforce)}",
                str(REPO_ROOT / "src"),
                str(tmp_path / "html"),
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )

    output = result.stdout + result.stderr
    if enforce:
        assert result.returncode != 0
        assert f"Failed to retrieve or parse the FLS specification from {fls_url}" in output
        assert "FLS NOTICE" not in output
    else:
        assert result.returncode == 0, output
        assert "Build complete" in output
        assert (
            "FLS NOTICE: Live FLS unavailable or unusable; freshness was not checked. "
            "References were validated against the committed src/spec.lock."
        ) in output
