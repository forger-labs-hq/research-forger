import os
import time
from pathlib import Path

import pytest

from researchforge.execution.runner import SubprocessRunner, shell_argv


@pytest.fixture
def runner() -> SubprocessRunner:
    return SubprocessRunner()


def _logs(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "out.log", tmp_path / "err.log"


class TestSubprocessRunner:
    def test_captures_stdout_and_exit_code(self, runner: SubprocessRunner, tmp_path: Path) -> None:
        out, err = _logs(tmp_path)
        outcome = runner.run(
            shell_argv("echo hello && echo oops >&2"),
            cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin"},
            timeout_seconds=10,
            stdout_path=out,
            stderr_path=err,
        )

        assert outcome.ok
        assert outcome.exit_code == 0
        assert out.read_text() == "hello\n"
        assert err.read_text() == "oops\n"

    def test_nonzero_exit(self, runner: SubprocessRunner, tmp_path: Path) -> None:
        out, err = _logs(tmp_path)
        outcome = runner.run(
            shell_argv("exit 7"),
            cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin"},
            timeout_seconds=10,
            stdout_path=out,
            stderr_path=err,
        )

        assert not outcome.ok
        assert outcome.exit_code == 7
        assert not outcome.timed_out

    def test_env_is_exactly_what_was_passed(self, runner: SubprocessRunner, tmp_path: Path) -> None:
        out, err = _logs(tmp_path)
        runner.run(
            shell_argv("echo ${MY_FORWARDED:-missing} ${HOME:-nohome}"),
            cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin", "MY_FORWARDED": "yes"},
            timeout_seconds=10,
            stdout_path=out,
            stderr_path=err,
        )

        assert out.read_text() == "yes nohome\n"

    def test_timeout_kills_whole_process_group(
        self, runner: SubprocessRunner, tmp_path: Path
    ) -> None:
        out, err = _logs(tmp_path)
        pid_file = tmp_path / "grandchild.pid"
        # Parent spawns a grandchild that would outlive a naive kill.
        command = f"(sleep 300 & echo $! > {pid_file}; wait)"

        outcome = runner.run(
            shell_argv(command),
            cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin"},
            timeout_seconds=1,
            stdout_path=out,
            stderr_path=err,
        )

        assert outcome.timed_out
        assert outcome.exit_code is None
        assert outcome.duration_seconds < 30

        grandchild_pid = int(pid_file.read_text().strip())
        # The grandchild dies with the process group; allow a moment for reaping.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(grandchild_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            pytest.fail(f"grandchild {grandchild_pid} survived the group kill")
