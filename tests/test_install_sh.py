"""install.sh in a clean Linux container: it sets Inky up with Python and prints the address and pairing code.
Skips unless Docker is running with the python:3.12-slim image (the browser download is skipped to keep it quick)."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def docker_ready():
    if not shutil.which("docker"):
        return False
    r = subprocess.run(["docker", "image", "inspect", "python:3.12-slim"], capture_output=True)
    return r.returncode == 0


@unittest.skipUnless(docker_ready(), "needs Docker with python:3.12-slim")
class InstallShTest(unittest.TestCase):
    def test_python_install_prints_url_and_code_and_the_engine_answers(self):
        script = ("mkdir -p /tmp/src && cp -r /repo/inky /repo/install.sh /tmp/src/ && "
                  "INKY_SRC=/tmp/src INKY_HOME=/tmp/data INKY_SKIP_BROWSER=1 sh /tmp/src/install.sh --python --json --no-service > /tmp/out.json && "
                  "cat /tmp/out.json && /tmp/src/.venv/bin/python -c \"import httpx; print(httpx.get('http://127.0.0.1:8800/api/ping').json()['ok'])\"")
        r = subprocess.run(["docker", "run", "--rm", "-v", f"{ROOT}:/repo:ro", "python:3.12-slim", "sh", "-c", script],
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        lines = r.stdout.strip().splitlines()
        out = json.loads(lines[-2])
        self.assertTrue(out["url"].startswith("http://") and out["url"].endswith(":8800"), out)
        self.assertRegex(out["code"], r"^[A-Z0-9]{6}$")
        self.assertEqual(lines[-1], "True")  # the engine it started answers on the network port

    def test_refuses_bad_port(self):
        r = subprocess.run(["sh", str(ROOT / "install.sh"), "--port", "80;rm", "--json"], capture_output=True, text=True, timeout=30,
                           env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "INKY_SRC": str(ROOT)})
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["error"], "the port must be a number")


if __name__ == "__main__":
    unittest.main()
