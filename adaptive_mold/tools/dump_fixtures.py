#! python 3
# -*- coding: utf-8 -*-
"""골든 픽스처 생성기 — Python 파이프라인의 출력을 JSON으로 고정한다.

C# 포팅본(plugin/AdaptiveMold.Core)이 같은 입력에서 같은 숫자를 내는지
대조할 정답지를 만든다. 기존 tests/는 핀 높이의 실제 숫자를 검증하지
않으므로 포팅 정답지로 쓸 수 없다 — 그래서 이 스크립트가 필요하다.

**Rhino 안에서 실행해야 한다** (RhinoCommon 필요).

    Rhino 8 → ScriptEditor(Python 3) → 이 파일 열고 Run
    또는 GhPython 컴포넌트에서:
        exec(open(r"<repo>/adaptive_mold/tools/dump_fixtures.py").read())

출력: plugin/fixtures/<case>.json

곡면은 JSON에 직렬화하지 않는다. 대신 **생성 파라미터**를 기록하여
C# 쪽이 같은 RhinoCommon 호출로 동일한 지오메트리를 재구성하게 한다.
테스트 곡면이 전부 단순 프리미티브(PlaneSurface, Sphere)라 가능하다.

각 케이스를 **두 번 실행해 결과가 같은지 확인한 뒤에만** 기록한다.
비결정적 출력은 정답지가 될 수 없다.
"""

import os
import sys
import io
import json
import math

import Rhino
import Rhino.Geometry as rg


# ──────────────────────────────────────
# 경로 설정
# ──────────────────────────────────────

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # ScriptEditor에서 __file__이 없을 때: 여기에 repo 경로를 직접 넣는다.
    HERE = r"C:\Users\leeja\Documents\dev\26_AdaptiveMold_development\adaptive_mold\tools"

SRC_DIR = os.path.normpath(os.path.join(HERE, "..", "src"))
REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT_DIR = os.path.join(REPO_ROOT, "plugin", "fixtures")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


def _purge_src_modules():
    """src/에서 로드된 모듈을 sys.modules에서 제거한다.

    Rhino의 Python 인터프리터는 **Rhino 프로세스가 살아 있는 동안** 모듈
    캐시를 유지한다. src/를 고쳐도 이미 import된 옛 모듈이 계속 쓰이므로,
    ScriptEditor를 닫았다 열어도 반영되지 않는다. Rhino를 재시작하거나
    이렇게 캐시를 비워야 한다.

    이름으로 지우면 stdlib의 동명 모듈(utils 등)까지 건드릴 수 있으므로
    __file__ 경로가 SRC_DIR 아래인 것만 지운다.
    """
    src_norm = os.path.normcase(os.path.normpath(SRC_DIR))
    removed = []
    for name in list(sys.modules.keys()):
        mod = sys.modules.get(name)
        path = getattr(mod, "__file__", None)
        if not path:
            continue
        if os.path.normcase(os.path.normpath(path)).startswith(src_norm):
            del sys.modules[name]
            removed.append(name)
    return removed


_PURGED = _purge_src_modules()

from adaptive_mold_v1 import run_adaptive_mold  # noqa: E402


# ──────────────────────────────────────
# 테스트 지오메트리 — tests/test_integration.py와 동일한 생성식
#
# 여기서 값이 달라지면 픽스처가 기존 테스트와 다른 것을 재는 셈이 된다.
# 수정할 일이 생기면 test_integration.py와 함께 고칠 것.
# ──────────────────────────────────────

def _make_flat_surface(z_height=200.0, size=2000.0):
    plane = rg.Plane(rg.Point3d(0, 0, z_height), rg.Vector3d.ZAxis)
    interval = rg.Interval(-size / 2, size / 2)
    return rg.PlaneSurface(plane, interval, interval)


def _make_tilted_surface(tilt_degrees=10.0, z_base=200.0, size=2000.0):
    angle = math.radians(tilt_degrees)
    normal = rg.Vector3d(math.sin(angle), 0, math.cos(angle))
    origin = rg.Point3d(size / 2, size / 2, z_base)
    plane = rg.Plane(origin, normal)
    interval = rg.Interval(-size / 2, size / 2)
    return rg.PlaneSurface(plane, interval, interval)


def _make_hemisphere(radius=400.0, center_z=0.0):
    center = rg.Point3d(500, 500, center_z)
    sphere = rg.Sphere(center, radius)
    return sphere.ToBrep()


def _make_rotated_plane():
    origin = rg.Point3d(500, 300, 100)
    x_axis = rg.Vector3d(1, 1, 0)
    x_axis.Unitize()
    y_axis = rg.Vector3d.CrossProduct(rg.Vector3d.ZAxis, x_axis)
    y_axis.Unitize()
    return rg.Plane(origin, x_axis, y_axis)


def build_surface(spec):
    """surface spec(dict)으로 지오메트리를 만든다. C# 쪽도 같은 분기를 구현한다."""
    kind = spec["kind"]
    if kind == "flat":
        return _make_flat_surface(spec["z_height"], spec["size"])
    if kind == "tilted":
        return _make_tilted_surface(spec["tilt_degrees"], spec["z_base"], spec["size"])
    if kind == "hemisphere":
        return _make_hemisphere(spec["radius"], spec["center_z"])
    raise ValueError("unknown surface kind: {}".format(kind))


def build_plane(spec):
    """base_plane spec(dict) → Plane. None이면 WorldXY."""
    if spec is None:
        return None
    if spec.get("kind") == "rotated":
        return _make_rotated_plane()
    raise ValueError("unknown plane kind: {}".format(spec.get("kind")))


def _r3(v):
    return [round(float(v.X), 6), round(float(v.Y), 6), round(float(v.Z), 6)]


def geometry_fingerprint(geo):
    """C#이 같은 스펙으로 같은 지오메트리를 만들었는지 볼 지문.

    픽스처의 input.surface는 직렬화된 지오메트리가 아니라 **생성 스펙**이라,
    C# 쪽이 build_surface를 재구현해야 한다. 거기서 어긋나면 Core가 옳아도
    대조가 깨지고, 우연히 상쇄되면 틀린 채로 통과한다.
    그래서 출력 대조보다 **입력 동일성 증명이 먼저**다.

    값 자체에 의미는 없다. 양쪽이 같기만 하면 된다. 6자리로 반올림하는
    이유: 최하위 비트 차이로 지문이 어긋나면 정작 보려던 것(스펙 해석이
    다른가)을 못 본다.
    """
    brep = geo if isinstance(geo, rg.Brep) else geo.ToBrep()

    bb = brep.GetBoundingBox(True)
    amp = rg.AreaMassProperties.Compute(brep)
    ns = brep.Faces[0].UnderlyingSurface().ToNurbsSurface()

    return {
        "bbox_min": _r3(bb.Min),
        "bbox_max": _r3(bb.Max),
        "area": round(float(amp.Area), 6) if amp else None,
        "face_count": int(brep.Faces.Count),
        "degree_u": int(ns.Degree(0)),
        "degree_v": int(ns.Degree(1)),
        "cv_u": int(ns.Points.CountU),
        "cv_v": int(ns.Points.CountV),
    }


def plane_fingerprint(plane):
    """base_plane은 지오메트리가 아니므로 따로 잰다. None이면 None."""
    if plane is None:
        return None
    return {
        "origin": _r3(plane.Origin),
        "x_axis": _r3(plane.XAxis),
        "y_axis": _r3(plane.YAxis),
        "z_axis": _r3(plane.ZAxis),
    }


# ──────────────────────────────────────
# 케이스 정의 — tests/test_integration.py의 T1~T8과 동일한 입력
#
# Phase E(housing/rod/top)는 이번 슬라이스 범위 밖이므로 모델을 넘기지
# 않는다. get_housing_height(None) == 0.0 이라 pin_tops도 A~D만으로
# 재현된다. T6의 모델 변형 케이스는 Phase E 포팅 때 별도로 만든다.
# ──────────────────────────────────────

DEFAULT_PARAMS = {
    "width": 1000.0,
    "length": 1000.0,
    "spacing": 200.0,
    "max_height": 400.0,
    "min_height": 0.0,
}

CASES = [
    {
        "case": "T1_flat_parallel",
        "note": "flat target parallel to base_plane - all heights equal, no clamping",
        "surface": {"kind": "flat", "z_height": 200.0, "size": 3000.0},
        "base_plane": None,
        "params": {},
    },
    {
        "case": "T2_tilted",
        "note": "10deg tilted plane - heights must become uniform after Phase B alignment",
        "surface": {"kind": "tilted", "tilt_degrees": 10.0, "z_base": 200.0, "size": 2000.0},
        "base_plane": None,
        "params": {},
    },
    {
        "case": "T3_hemisphere",
        "note": "hemisphere - center highest, edges in extension zone. most fallback branching",
        "surface": {"kind": "hemisphere", "radius": 400.0, "center_z": 0.0},
        "base_plane": None,
        "params": {},
    },
    {
        "case": "T4_small_surface",
        "note": "surface smaller than mold - extension_flags expected",
        "surface": {"kind": "flat", "z_height": 200.0, "size": 600.0},
        "base_plane": None,
        "params": {"width": 1000.0, "length": 1000.0},
    },
    {
        "case": "T5_deep_clamp",
        "note": "max_height=200 with deep surface - clamping expected",
        "surface": {"kind": "flat", "z_height": 500.0, "size": 3000.0},
        "base_plane": None,
        "params": {"max_height": 200.0},
    },
    {
        "case": "T6_flat_150",
        "note": "flat plane at z=150. original T6 tested rod scale (Phase E); here A-D only",
        "surface": {"kind": "flat", "z_height": 150.0, "size": 3000.0},
        "base_plane": None,
        "params": {},
    },
    {
        "case": "T7_rotated_base_plane",
        "note": "rotated/translated base_plane - first grid_pt must equal plane origin",
        "surface": {"kind": "flat", "z_height": 300.0, "size": 3000.0},
        "base_plane": {"kind": "rotated"},
        "params": {},
    },
    {
        "case": "T8_large_grid",
        "note": "11x11=121 actuators - doubles as the 3s performance bound",
        "surface": {"kind": "flat", "z_height": 200.0, "size": 4000.0},
        "base_plane": None,
        "params": {"width": 2000.0, "length": 2000.0, "spacing": 200.0},
    },
]


# ──────────────────────────────────────
# 실행
# ──────────────────────────────────────

def _to_unicode(obj):
    """dict/list 안의 bytes 문자열을 재귀적으로 unicode로 올린다.

    IronPython 2.7에서 소스의 한글 리터럴은 utf-8 bytes(str)이고,
    json 인코더가 그것을 ascii로 처리하려다 UnicodeEncodeError를 낸다.
    Python 3에서는 아무 일도 하지 않는다.
    """
    if isinstance(obj, dict):
        return dict((_to_unicode(k), _to_unicode(v)) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return [_to_unicode(v) for v in obj]
    if isinstance(obj, bytes) and bytes is str:
        return obj.decode("utf-8")
    return obj


def _as_text(s):
    """io.open(encoding=...)에 쓸 수 있는 텍스트로 맞춘다."""
    if isinstance(s, bytes):
        return s.decode("utf-8")
    return s


def run_case(case):
    """케이스 하나를 실행해 비교 가능한 dict를 돌려준다."""
    params = dict(DEFAULT_PARAMS)
    params.update(case["params"])

    surface = build_surface(case["surface"])
    base_plane = build_plane(case["base_plane"])

    # 지문은 파이프라인에 넘기기 전에 잰다. 원본을 만지지 않는 읽기 연산이지만
    # 순서를 고정해 두는 편이 나중에 의심할 거리를 줄인다.
    fingerprint = geometry_fingerprint(surface)
    plane_fp = plane_fingerprint(base_plane)

    r = run_adaptive_mold(
        surface,
        base_plane=base_plane,
        width=params["width"],
        length=params["length"],
        spacing=params["spacing"],
        max_height=params["max_height"],
        min_height=params["min_height"],
        compute=True,
    )

    return {
        "pin_heights": [float(h) for h in r.pin_heights],
        "clamp_flags": [bool(c) for c in r.clamp_flags],
        "extension_flags": [bool(e) for e in r.extension_flags],
        "branch_taken": list(r.branch_taken),
        "opt_branch": r.opt_branch,
        "ext_branch": r.ext_branch,
        "pin_tops": [[float(p.X), float(p.Y), float(p.Z)] for p in r.pin_tops],
        "grid_pts": [[float(p.X), float(p.Y), float(p.Z)] for p in r.grid_pts],
        "info": r.info,
        "fingerprint": fingerprint,
        "plane_fingerprint": plane_fp,
    }


def compare(a, b):
    """두 실행 결과가 완전히 같은지 확인한다. 다르면 첫 불일치를 돌려준다."""
    for key in ("pin_heights", "clamp_flags", "extension_flags", "branch_taken"):
        va, vb = a[key], b[key]
        if len(va) != len(vb):
            return "{}: 길이 다름 {} vs {}".format(key, len(va), len(vb))
        for i, (x, y) in enumerate(zip(va, vb)):
            if x != y:
                return "{}[{}]: {!r} vs {!r}".format(key, i, x, y)
    # Phase B·C 가지도 재현성 검사 대상이다 — 실행마다 흔들리면 정답지가 될 수 없다.
    for key in ("opt_branch", "ext_branch"):
        if a[key] != b[key]:
            return "{}: {!r} vs {!r}".format(key, a[key], b[key])
    return None


_LOG = []


def log(msg):
    """콘솔과 로그 파일 양쪽에 남긴다.

    Rhino를 /runscript로 띄워 자동 실행하면 명령줄 출력을 되읽을 수 없으므로
    파일에도 기록한다.
    """
    print(msg)
    _LOG.append(msg)


def main():
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)

    rhino_version = str(Rhino.RhinoApp.Version)
    log("Rhino {}".format(rhino_version))
    log("출력: {}".format(OUT_DIR))
    if _PURGED:
        log("모듈 캐시 비움: {}".format(", ".join(sorted(_PURGED))))
    import projection as _proj
    log("projection.py 로드: {}".format(_proj.__file__))
    log("")

    failures = []

    for case in CASES:
        name = case["case"]

        first = run_case(case)
        second = run_case(case)

        diff = compare(first, second)
        if diff is not None:
            log("[재현실패] {} — {}".format(name, diff))
            failures.append(name)
            continue

        branch_counts = {}
        for b in first["branch_taken"]:
            branch_counts[b] = branch_counts.get(b, 0) + 1

        fixture = {
            "case": name,
            "note": case["note"],
            "input": {
                "surface": case["surface"],
                "base_plane": case["base_plane"],
                "params": dict(DEFAULT_PARAMS, **case["params"]),
                # 지문은 입력의 성질이지 계산 결과가 아니므로 expected에 넣지 않는다.
                "fingerprint": first["fingerprint"],
                "plane_fingerprint": first["plane_fingerprint"],
            },
            "expected": {
                "pin_heights": first["pin_heights"],
                "clamp_flags": first["clamp_flags"],
                "extension_flags": first["extension_flags"],
                "branch_taken": first["branch_taken"],
                "opt_branch": first["opt_branch"],
                "ext_branch": first["ext_branch"],
                "pin_tops": first["pin_tops"],
                "grid_pts": first["grid_pts"],
            },
            "summary": {
                "pin_count": len(first["pin_heights"]),
                "clamped": sum(1 for c in first["clamp_flags"] if c),
                "in_extension": sum(1 for e in first["extension_flags"] if e),
                "branch_counts": branch_counts,
            },
            "meta": {
                "generated_by": "adaptive_mold/tools/dump_fixtures.py",
                "rhino_version": rhino_version,
                "source": "python (adaptive_mold/src)",
            },
        }

        path = os.path.join(OUT_DIR, name + ".json")
        # encoding 명시 필수: Windows 한국어 로캘에서 open()의 기본 인코딩이
        # cp949라 em dash 같은 문자를 못 쓴다.
        # 또한 IronPython 2.7의 json 인코더는 utf-8 bytes 문자열에서 죽으므로
        # 덤프 전에 전부 unicode로 올린다.
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(_as_text(json.dumps(_to_unicode(fixture), indent=2, sort_keys=False)))

        log("[OK] {:<24} pins={:<4} clamp={:<4} ext={:<4} branches={}".format(
            name,
            fixture["summary"]["pin_count"],
            fixture["summary"]["clamped"],
            fixture["summary"]["in_extension"],
            branch_counts,
        ))

    log("")
    if failures:
        log("재현 실패 {}건: {}".format(len(failures), ", ".join(failures)))
        log("비결정적 출력은 정답지가 될 수 없다. 원인을 찾기 전엔 진행하지 말 것.")
    else:
        log("전 케이스 재현 확인 — 픽스처 {}개 기록됨.".format(len(CASES)))

    with io.open(os.path.join(OUT_DIR, "_dump_log.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(_LOG))


try:
    main()
except Exception:
    import traceback
    tb = traceback.format_exc()
    print(tb)
    try:
        if not os.path.isdir(OUT_DIR):
            os.makedirs(OUT_DIR)
        with io.open(os.path.join(OUT_DIR, "_dump_log.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(_LOG) + "\n\n[예외]\n" + tb)
    except Exception:
        pass
    raise
