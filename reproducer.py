from typing import List
import gdb
import os
import json

from gdb_utils import *


class ThreadPos:
    def __init__(self, tid: int, addr: int):
        self.tid = tid
        self.addr = addr


def parse_trace(trace_path) -> List[ThreadPos]:
    ans = []
    with open(trace_path) as f:
        for line in f.readlines():
            line = line.strip()
            if len(line) == 0:
                continue
            try:
                tid, addr = line.split(":")
                tid = int(tid)
                addr = int(addr, 16)
            except ValueError:
                gdb.write("trace format error: %s\n" % line, gdb.STDERR)
                continue
            ans.append(ThreadPos(tid, addr))
    return ans


class Reproducer:

    def __init__(self, cmd: List[str], trace_path: str, step_timeout: float):
        self.exe = cmd[0]
        self.args = cmd[1:]
        self.trace = parse_trace(trace_path)
        self.fail = False
        self.step_timeout = step_timeout

    def start(self):
        gdb_execute("file %s" % self.exe)
        args = ' '.join(map(gdb_path, self.args))
        args += " >/dev/null 2>&1"
        gdb_execute("set args " + args)
        gdb_execute("set startup-with-shell on")
        gdb_execute("set non-stop off")
        gdb_execute("starti")

        self._setup_gdb_options()
        self._setup_handlers()

        self.base_addr = gdb_load_address(self.exe)
        if self.base_addr is None:
            gdb.write("fail to load base address\n", gdb.STDERR)
            self.fail = True
        # print("base", hex(self.base_addr))

    def _setup_gdb_options(self):
        gdb_execute("set follow-fork-mode parent")
        gdb_execute("set detach-on-fork off")
        gdb_execute("set follow-exec-mode new")
        gdb_execute("set scheduler-locking on")
        gdb_execute("set schedule-multiple on")
        gdb_execute("set print finish off")
        gdb_execute("set pagination off")

    def _setup_handlers(self):
        # let program crash on signal
        # signals = ["SIGSEGV", "SIGILL", "SIGABRT"]
        # for sig in signals:
        #    gdb_execute("handle %s nostop pass" % sig)

        # stop on new threads
        gdb_execute("catch syscall clone")

    def inside_clone(self) -> bool:
        try:
            frame = gdb.newest_frame()
        except gdb.error:
            return False
        if frame is None or not frame.is_valid():
            return False
        return frame.name() == "clone"

    def run(self):
        if self.fail:
            return
        for item in self.trace:
            print("run", item.tid, hex(item.addr))
            tid = item.tid
            if not gdb_switch_thread(tid):
                gdb.write("cannot switch to thread %d\n" % tid, gdb.STDERR)
                self.fail = True
                return
            addr = item.addr + self.base_addr
            break_addr = "*0x%x" % addr
            bp = gdb.Breakpoint(break_addr, internal=True, temporary=True)
            bp.silent = True
            # bp.thread = True # cannot use this, why?
            try:
                gdb_execute_timeout("continue", self.step_timeout)
            except TimeoutError:
                if item.addr != 0:
                    self.fail = True
                    return
            except gdb.error:
                print("gdb error")
                return
            if self.inside_clone():
                gdb_execute("stepi")
            if bp.is_valid():
                bp.delete()


def from_config(config_path):
    with open(config_path) as f:
        config = json.load(f)
    cmd = config["cmd"]
    trace_path = config["trace"]
    step_timeout = config.get("step_timeout", 0.5)
    repro = Reproducer(cmd, trace_path, step_timeout)
    return repro


def main():
    config_path = os.environ["REPRO_CONFIG"]
    repro = from_config(config_path)
    repro.start()
    repro.run()


main()
gdb_quit()
