"""Inspect and stop owned workers without platform-specific liveness signals."""

import os
import signal

import psutil


def is_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


def stop_tree(process):
    """Stop a verified worker and its descendants, guarding against PID reuse."""
    if process.pid == os.getpid():
        raise ValueError("Cannot stop the calling process")
    try:
        if not process.is_running():
            return
        if os.name != "nt" and os.getpgid(process.pid) == process.pid:
            os.killpg(process.pid, signal.SIGKILL)
            return
        # Freeze the producer before collecting children so it cannot start more work.
        process.suspend()
        try:
            children = process.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            process.kill()
        finally:
            try:
                if process.is_running():
                    process.resume()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs([*children, process], timeout=10)
        if alive:
            raise TimeoutError("Owned worker processes did not stop")
    except (psutil.NoSuchProcess, ProcessLookupError):
        pass


def stop_worker(process):
    if process is None:
        return
    try:
        if os.name != "nt":
            # The worker owns a session; descendants can outlive its group leader.
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            stop_tree(psutil.Process(process.pid))
    except (psutil.NoSuchProcess, ProcessLookupError):
        pass
    process.wait(timeout=10)


def stop_recorded_worker(pid, request_path):
    try:
        process = psutil.Process(pid)
        argv = process.cmdline()
        if len(argv) >= 4 and argv[1:4] == ["-m", "unfold.worker", str(request_path)]:
            stop_tree(process)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
