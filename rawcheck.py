#!/usr/bin/env python3

"""
RAWCHECK

Copyright 2023 by Frank Eberle (https://www.frank-eberle.de)

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions
  and the following disclaimer in the documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED
WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
"""

import os
import threading
import argparse
import subprocess
import sys
import logging
from typing import List


class AppError(Exception):
    pass


class Queue(object):
    def __init__(self) -> None:
        self._data = []
        self._sem = threading.Semaphore()
        self._completed = False
        self._cond = threading.Condition()

    def push(self, entry: any) -> None:
        with self._sem:
            self._data.append(entry)
        with self._cond:
            self._cond.notify_all()

    def pop(self) -> any:
        result = None
        while True:
            with self._sem:
                if len(self._data) > 0:
                    result = self._data.pop(0)
                    break
            if not self._completed:
                with self._cond:
                    self._cond.wait()
            else:
                break
        return result
    
    def completed(self) -> None:
        self._completed = True
        with self._cond:
            self._cond.notify_all()
    
    def clear(self) -> None:
        self._data = []


class WorkerThread(threading.Thread):
    
    _dcraw_emu_path = "/usr/bin/dcraw_emu"

    def __init__(self, name: str, queue: Queue, dcraw_path: str) -> None:
        super().__init__(name=name)
        self._queue = queue
        self._failed = None
        self._dcraw_path = dcraw_path
        self._logger = logging.getLogger()
        if not os.path.isfile(self._dcraw_path):
            raise AppError(f"Executable '{self._dcraw_path}' not found")
        if not os.access(self._dcraw_path, os.X_OK):
            raise AppError(f"File '{self._dcraw_path}' ist not executable")

    def _command(self, path:str):
            args = [
                self._dcraw_path,
                "-Z",
                "-",
                path
            ]
            self._logger.debug(f"Processing file: {path}")
            res = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            stderr = res.stderr.decode("utf-8").strip()
            if (res.returncode != 0) or (stderr != ""):
                if stderr.startswith(path):
                    stderr = stderr[len(path) + 2:]
                self._logger.debug(f"Failed: {stderr}")
                self._failed[path] = stderr

    def run(self):
        self._failed = {}
        while True:
            path = self._queue.pop()
            if path == None:
                break
            self._command(path)

    @property
    def failed(self) -> List:
        return self._failed


class RawCheck(object):
    def __init__(self):
        self._raw_ext = ["crw", "cr2", "cr3", "rw2", "dng", "raf"]
        self._dcraw_path = "/usr/bin/dcraw_emu"

    def __call__(self, cmd_args:List) -> bool:
        result = False
        argparser = argparse.ArgumentParser()
        argparser.add_argument("--dir", required=True)
        argparser.add_argument("--debug", action="store_true", default=False)
        argparser.add_argument("--workers", required=False, type=int, default=1)
        argparser.add_argument("--show-extensions", required=False, action="store_true", default=False)
        argparser.add_argument("--dcraw-binary", required=False, default=self._dcraw_path)
        args = argparser.parse_args(cmd_args)
        # Prepare logger
        root_logger = logging.getLogger()
        log_handler = logging.StreamHandler()
        root_logger.addHandler(log_handler)
        if args.debug:
            root_logger.setLevel(logging.DEBUG)
            log_handler.setLevel(logging.DEBUG)
        else:
            root_logger.setLevel(logging.INFO)
            log_handler.setLevel(logging.INFO)
        #
        extensions = {}
        queue = Queue()
        completed = False
        try:
            # Check "--dir" argument
            if not os.path.isdir(args.dir):
                raise AppError(f"Specified path '{args.dir}' does not exist or is not a directory")
            # start workers
            for i in range(0, args.workers):
                worker = WorkerThread(name=f"Thread-{i+1}", queue=queue, dcraw_path=args.dcraw_binary)
                worker.start()
            # Scan for files
            for base, _, files in os.walk(args.dir):
                for f in files:
                    path = os.path.join(base, f)
                    _, ext = os.path.splitext(f)
                    ext = ext[1:].lower()
                    if not ext in extensions:
                        extensions[ext] = 1
                    else:
                        extensions[ext] += 1
                    if ext in self._raw_ext:
                        queue.push(path)
            queue.completed()
            failed = {}
            for t in threading.enumerate():
                if t != threading.main_thread():
                    t.join()
                    for p, e in t.failed.items():
                        failed[p] = e
            if args.show_extensions:
                for ext, count in extensions.items():
                    print("File Extensions:")
                    print(f"  {ext}: {count}")
                    print("")
            if len(failed) > 0:
                print("Failed:")
                for path, reason in failed.items():
                    print(f"  {path}: {reason}")
                print("")
            else:
                result = True
        except KeyboardInterrupt:
            queue.clear()
            queue.completed()
        except AppError as e:
            print(f"Error: {e}\n")


if __name__ == "__main__":
    rawcheck = RawCheck()
    if rawcheck(sys.argv[1:]):
        sys.exit(0)
    sys.exit(1)
