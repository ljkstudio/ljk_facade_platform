#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""rhinomcp 브리지(127.0.0.1:1999)에 직접 말하는 최소 클라이언트.

MCP 서버 계층을 건너뛴다. 브리지는 JSON을 그대로 받으므로 기능 차이는 없다.
연결 하나로 여러 명령을 처리해 소켓 누적(CLOSE_WAIT)을 줄인다.
"""

import socket
import json
import sys

HOST, PORT = "127.0.0.1", 1999

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


class Rhino(object):
    def __init__(self, timeout=120):
        self.sock = socket.create_connection((HOST, PORT), timeout=timeout)
        self.sock.settimeout(timeout)

    def call(self, cmd_type, **params):
        self.sock.sendall(json.dumps({"type": cmd_type, "params": params}).encode())
        buf = b""
        while True:
            b = self.sock.recv(1 << 20)
            if not b:
                break
            buf += b
            try:
                return json.loads(buf.decode())
            except Exception:
                continue
        raise RuntimeError("응답 없음")

    def py(self, code):
        """Rhino 안에서 파이썬 실행."""
        return self.call("execute_rhinoscript_python_code", code=code)

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        self.sock.close()


def main():
    r = Rhino()
    try:
        info = r.call("get_document_info")
        md = info.get("result", {}).get("meta_data", {})
        print("문서:", md.get("name"), "| 단위:", md.get("units"))
        print("객체 수:", info.get("result", {}).get("object_count"))
        print()
        out = r.py("import Rhino\nprint('Rhino', Rhino.RhinoApp.Version)")
        print("파이썬 실행 결과:", json.dumps(out, ensure_ascii=False)[:400])
    finally:
        r.close()


if __name__ == "__main__":
    main()
