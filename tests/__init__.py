"""Every test's temporary folder (browser profiles, scratch homes) goes in one folder that's removed when the run ends,
so test runs never pile up on the disk. INKY_JOURNEY_KEEP keeps them, to look at what happened."""
import atexit
import os
import shutil
import tempfile

if not os.environ.get("INKY_JOURNEY_KEEP"):
    tempfile.tempdir = tempfile.mkdtemp(prefix="inky-tests-")
    atexit.register(shutil.rmtree, tempfile.tempdir, True)
