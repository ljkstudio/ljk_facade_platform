#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""rhinomcp 브리지(127.0.0.1:1999)에 직접 말하는 최소 클라이언트.

MCP 서버 계층을 건너뛴다. 브리지는 JSON을 그대로 받으므로 기능 차이는 없다.
연결 하나로 여러 명령을 처리해 소켓 누적(CLOSE_WAIT)을 줄인다.
"""

import socket
import io
import json
import os
import sys
import tempfile
import uuid

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

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


Bridge = Rhino          # 이름만 다른 별칭 — 호출부에서 의미가 드러나도록


_WRAPPER = u'''
import io, os, sys, traceback
import Rhino
import Rhino.Geometry as rg
lines = []
try:
    import Grasshopper as gh
except Exception:
    gh = None
try:
{body}
except Exception:
    lines.append(traceback.format_exc())
_f = io.open(r"{out}", "w", encoding="utf-8")
try:
    _f.write(u"\\n".join([unicode(x) for x in lines]))
finally:
    _f.close()          # close 필수 — .NET GC라 빠뜨리면 0바이트 파일이 남는다
'''


def remote(bridge, body):
    """브리지에서 코드를 실행하고 `lines`에 담긴 결과를 문자열로 돌려준다.

    결과를 stdout으로 받지 않는 이유: 브리지는 IronPython 2.7이고 stdout이
    ascii라 한글 print가 죽는다. 응답 JSON에 비ASCII를 넣어도 인코더가 죽는다.
    그래서 원격 코드가 파일에 쓰고 이쪽이 읽는다.

    body 안에서 쓸 수 있는 것: lines, Rhino, rg, gh(없으면 None).
    들여쓰기는 여기서 맞춰 넣으므로 body는 왼쪽 정렬로 쓰면 된다.
    """
    out = os.path.join(tempfile.gettempdir(),
                       "am_bridge_%s.txt" % uuid.uuid4().hex[:8])
    indented = u"\n".join(u"    " + ln for ln in body.splitlines())
    bridge.py(_WRAPPER.format(body=indented, out=out.replace("\\", "\\\\")))
    if not os.path.exists(out):
        raise RuntimeError("결과 파일이 생기지 않았다: %s" % out)
    with io.open(out, encoding="utf-8") as f:
        text = f.read()
    os.remove(out)
    return text


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
