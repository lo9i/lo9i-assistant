"""The daemon's output file: past its limit at start, it's kept as output.log.1 and the daemon writes to a new
one. The daemons here are real processes whose stderr is the file, as launchd and the terminal app start it."""

import subprocess
import sys
from pathlib import Path

_START = (
    "import sys; from pathlib import Path; from assistant.daemon import output; "
    "print('before', file=sys.stderr, flush=True); rotated = output.rotate(Path(sys.argv[1]), limit=int(sys.argv[2])); "
    "print('after', rotated, file=sys.stderr)"
)


def _start(log: Path, stderr: Path, limit: int) -> None:
    with stderr.open("ab") as out:
        subprocess.run([sys.executable, "-c", _START, str(log), str(limit)], stderr=out, check=True)


def test_a_full_output_file_is_kept_as_the_one_before_and_the_daemon_writes_to_a_new_one(tmp_path):
    log = tmp_path / "output.log"
    log.write_text("x" * 100 + "\n")
    _start(log, log, limit=50)
    assert (tmp_path / "output.log.1").read_text() == "x" * 100 + "\nbefore\n"
    assert log.read_text() == "after True\n"


def test_one_under_its_limit_stays_as_it_is(tmp_path):
    log = tmp_path / "output.log"
    log.write_text("short\n")
    _start(log, log, limit=1000)
    assert log.read_text() == "short\nbefore\nafter False\n"
    assert not (tmp_path / "output.log.1").exists()


def test_output_going_elsewhere_isnt_touched(tmp_path):
    log, elsewhere = tmp_path / "output.log", tmp_path / "terminal.txt"
    log.write_text("x" * 100)
    _start(log, elsewhere, limit=50)
    assert log.read_text() == "x" * 100 and not (tmp_path / "output.log.1").exists()
    assert elsewhere.read_text() == "before\nafter False\n"
