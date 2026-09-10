# -*- coding: utf-8 -*-
"""守护进程（pythonw 运行，无窗口）：主程序异常退出时自动重启并恢复会话；
主程序正常关窗（写入退出标记）时守护进程一并退出。"""
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(BASE, "video_desc_tool.py")
FLAG = os.path.join(BASE, "video_desc_normal_exit.flag")


def main():
    n = 0
    while True:
        try:
            os.remove(FLAG)
        except OSError:
            pass
        try:
            p = subprocess.Popen([sys.executable, MAIN])
            p.wait()
        except Exception:
            time.sleep(2)
            n += 1
            if n >= 5:
                return
            continue
        if os.path.exists(FLAG):
            return
        n += 1
        if n >= 5:
            return
        time.sleep(2)


if __name__ == "__main__":
    main()
