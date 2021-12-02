import os
import sys
import subprocess
import json
import tempfile
import struct


def parse_rb_stat(file_name) -> bool:
    if not os.path.exists(file_name):
        return False
    with open(file_name, "rb") as f:
        data = f.read()
    data = list(map(lambda x: x[0], struct.iter_unpack("<I", data)))
    return any(x > 0 for x in data[1:])


if __name__ == "__main__":

    if len(sys.argv) != 2:
        print("Usage: repro [config.json]")
        exit(1)

    config_path = sys.argv[1]
    with open(config_path) as f:
        config = json.load(f)

    curdir = os.path.abspath(os.path.dirname(__file__))
    reproducer_path = os.path.join(curdir, "reproducer.py")

    timeout = config.get("timeout", None)
    gdb_cwd = config.get("cwd", None)

    temp_folder = tempfile.TemporaryDirectory(prefix="repro-")
    config2_path = os.path.join(temp_folder.name, "config.json")
    log_path = os.path.join(temp_folder.name, "rb_stat")

    environ = os.environ.copy()
    environ["REPRO_CONFIG"] = os.path.abspath(config_path)
    environ["PYTHONPATH"] = curdir + ":" + os.getenv("PYTHON_PATH", "")
    environ["RACEBENCH_STAT"] = log_path

    try:
        proc = subprocess.Popen(["gdb", "-q", "-nx", "-x", reproducer_path],
                                env=environ, cwd=gdb_cwd,
                                stdin=subprocess.DEVNULL)
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(1)
        except subprocess.TimeoutExpired:
            proc.kill()

    success = parse_rb_stat(log_path)
    temp_folder.cleanup()

    if success:
        exit()
    else:
        exit(-1)
