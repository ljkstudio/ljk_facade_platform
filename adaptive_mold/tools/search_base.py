#! python 3
# -*- coding: utf-8 -*-
"""로봇 베이스 위치를 훑어 찾는다. **한 파일이 두 몫을 한다.**

    밖에서 (CPython 3):   python adaptive_mold/tools/search_base.py [옵션]
    Rhino 안에서:         run-file 로 태워지면 실제 계산을 한다

`import Rhino` 가 되는지로 두 모드를 가른다. 두 파일로 나누면 옵션 이름이
양쪽에서 갈라지므로 한 파일에 둔다.

──────────────────────────────────────────────────────────
조각으로 나눠 던진다 — 한 번에 다 돌리면 Rhino 가 얼어붙는다
──────────────────────────────────────────────────────────

`_-RunPythonScript` 는 **Rhino UI 스레드에서 동기 실행**된다. 후보 60개를 한
호출에 넣었더니 (실측) **Rhino 가 20분 동안 `Responding=False`** 였고, 사용자
눈에는 프로그램이 죽은 것으로 보였다. 게다가 밖에서 기다리던 소켓이 903초에
타임아웃해 **결과를 못 받았다** (계산은 Rhino 안에서 계속 돌고 있었다).

그래서 `--chunk` 개씩 나눠 던진다:

    조각마다 소켓이 열리고 닫힌다      → 타임아웃 예산이 조각 하나 몫이면 된다
    조각 사이에 UI 스레드가 풀린다      → Rhino 가 숨을 쉰다 (뷰포트·취소 가능)
    결과를 JSONL 에 누적한다           → 중간에 끊겨도 거기까지는 남는다

옵션 (밖에서):
    --polar 1600,2400,200   **권장.** 몰드 중심 기준 고리: 반경 시작,끝,간격
    --angles 0,330,30       고리의 각도 범위 (deg). --polar 와 같이 쓴다
    --step 200        (사각 격자) 간격 mm
    --span 1200       (사각 격자) 현재 위치에서 ±범위 mm
    --at X Y          사각 격자의 중심 (없으면 robot_base_pt 위치)
    --chunk 3         한 번에 던질 후보 수 (기본 3). 이만큼 Rhino 가 얼어붙는다
    --no-hit          팔 간섭 검사 생략 (후보당 0.7초 절약)
    --keep-dir        방향을 지금 선 방향으로 고정 (기본: 타겟 중심을 향함)
    --spin A,B,C      최적점에서 방향을 이 각도(deg)만큼 돌려 확인
    --z Z1,Z2         최적점에서 이 높이들도 확인 (받침대 효과)
    --apply           최적점으로 robot_base_pt(와 방향선)를 실제로 옮긴다
    --resume          기존 결과를 지우지 않고 남은 후보만 이어서 계산

로그: adaptive_mold/grasshopper/_search_base_log.txt
결과: adaptive_mold/grasshopper/_search_base_results.jsonl
"""

import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
GH_DIR = os.path.normpath(os.path.join(REPO, "adaptive_mold", "grasshopper"))
CFG = os.path.join(tempfile.gettempdir(), "am_search_cfg.json")
LOG = os.path.join(GH_DIR, "_search_base_log.txt")
JSONL = os.path.join(GH_DIR, "_search_base_results.jsonl")

try:
    import Rhino                      # noqa: F401
    INSIDE = True
except ImportError:
    INSIDE = False


DEFAULTS = {"step": 200.0, "span": 1200.0, "at": None, "hit": True,
            "keep_dir": False, "spin": [], "z": [], "apply": False,
            "polar": None, "angles": [0.0, 330.0, 30.0], "chunk": 3,
            "mode": "scan", "from": 0, "to": 0}

# 후보 하나에 걸리는 시간 (초) — **실측이고 편차가 크다.** 좋은 자리는 1.7초,
# 사각 격자 25개 평균 7.5초, 고리 60개(반경 1600~2400) 평균 15초였다.
# 최악은 반경이 큰 자리로 50초를 넘었다 — IK 가 수렴하지 못해 반복을 다 쓴다.
# 조각 타임아웃은 이 최악값으로 잡는다.
SEC_WORST_CANDIDATE = 60.0
SEC_HIT = 0.7


# ══════════════════════════════════════════════════════════
# Rhino 안 — 실제 계산
# ══════════════════════════════════════════════════════════

def _log(lines, msg=""):
    print(msg)
    lines.append(str(msg))
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(str(msg) + u"\n")


def _setup(cfg, log):
    """입력·후보·간섭검사 준비를 한 곳에서. 조각마다 다시 부른다.

    다시 부르는 비용은 메시 로딩뿐이고(1초 미만), 그 대신 조각들이 서로
    독립이라 중간에 끊겨도 이어붙일 수 있다.
    """
    import Grasshopper as ghk
    import Rhino.Geometry as rg

    src = os.path.join(REPO, "adaptive_mold", "src")
    sys.path.insert(0, src)

    # **Rhino 의 모듈 캐시는 프로세스 수명을 따른다.** src/ 를 고쳐도 옛 모듈이
    # 쓰인다 — 실측: 새로 추가한 인자를 "그런 인자 없다"고 거부했다.
    # 이름이 아니라 `__file__` 경로로 지운다 (이름으로 지우면 stdlib 동명
    # 모듈까지 날아간다).
    _n = os.path.normcase(src)
    for _m in list(sys.modules.keys()):
        _p = getattr(sys.modules.get(_m), "__file__", None)
        if _p and os.path.normcase(os.path.normpath(_p)).startswith(_n):
            del sys.modules[_m]

    import robot as rb
    import collision as col
    import base_search as bs

    def find(nick):
        for d in [x for x in ghk.Instances.DocumentServer]:
            for o in d.Objects:
                if o.NickName == nick:
                    return o
        return None

    def outs(comp, name):
        out = []
        if comp is None:
            return out
        for p in comp.Params.Output:
            if p.NickName == name:
                for it in p.VolatileData.AllData(True):
                    out.append(getattr(it, "Value", it))
        return out

    rp = find("AMv1 RollerPath")
    insp = find("AMv1 Inspect")
    env = {"bs": bs, "rb": rb, "col": col, "rg": rg, "ghk": ghk,
           "targets": outs(rp, "targets"),
           "kinds": [str(v) for v in outs(rp, "move_kind")],
           "pin_pts": outs(insp, "pin_tops"),
           "srfs": outs(insp, "sheet_ht")}
    if not env["targets"]:
        log("타겟이 없다 — AMv1 RollerPath 를 먼저 돌릴 것")
        return None

    doc = Rhino.RhinoDoc.ActiveDoc
    st = Rhino.DocObjects.ObjectEnumeratorSettings()
    st.HiddenObjects = True
    env["doc"] = doc
    env["pt_obj"] = None
    env["dir_obj"] = None
    for o in doc.Objects.GetObjectList(st):
        if o.Geometry is None:
            continue
        if o.Attributes.Name == "robot_base_pt":
            env["pt_obj"] = o
        elif o.Attributes.Name == "robot_base_dir":
            env["dir_obj"] = o

    if cfg["at"]:
        cx, cy = float(cfg["at"][0]), float(cfg["at"][1])
        cz = env["pt_obj"].Geometry.Location.Z if env["pt_obj"] else -500.0
    elif env["pt_obj"] is not None:
        p = env["pt_obj"].Geometry.Location
        cx, cy, cz = p.X, p.Y, p.Z
    else:
        log("robot_base_pt 도 --at 도 없다 — 중심을 정할 수 없다")
        return None
    env["cz"] = cz

    env["direction"] = None
    if cfg["keep_dir"]:
        if env["dir_obj"] is None:
            log("--keep-dir 인데 robot_base_dir 가 없다")
            return None
        env["direction"] = rb._direction_of(env["dir_obj"].Geometry)

    # 간섭 검사 준비
    env["hit"] = None
    env["skipped"] = None
    if cfg["hit"]:
        field = None
        if env["srfs"]:
            field = col.Heightfield.from_surface(env["srfs"][0], nx=40, ny=40)
        if field is None:
            env["skipped"] = "팔 간섭 검사 (몰드면을 못 얻었다)"
        else:
            import robot_body as rbb
            parts = rbb.load_parts(os.path.join(GH_DIR, "irb6700_parts.3dm"))
            if not parts:
                env["skipped"] = "팔 간섭 검사 (로봇 메시가 없다)"
            else:
                env["hit"] = (col.sample_points(parts), field,
                              col.DEFAULT_MARGIN)
    else:
        env["skipped"] = "팔 간섭 검사 (--no-hit)"

    # 후보 목록 — cfg 만 보고 **결정적으로** 만든다. 조각들이 같은 목록을
    # 봐야 인덱스로 자를 수 있다.
    if cfg["polar"]:
        r0, r1, dr = cfg["polar"]
        a0, a1, da = cfg["angles"]
        center = rg.BoundingBox([t.Origin for t in env["targets"]]).Center
        raw, xs, ys = bs.polar_points(center, r0, r1, dr, a0, a1, da)
        env["cells"] = list(raw)
        env["axes"] = ("각도", "반경")
        env["center"] = center
    else:
        pts, xs, ys = bs.grid_points(cx - cfg["span"], cx + cfg["span"],
                                     cy - cfg["span"], cy + cfg["span"],
                                     step=cfg["step"])
        env["cells"] = [(x, y, x, y) for (x, y) in pts]
        env["axes"] = ("x", "y")
        env["center"] = None
    env["xs"] = xs
    env["ys"] = ys
    return env


_KEEP = ("ok", "reason", "fails", "err_max", "j_margin", "j_worst",
         "min_override", "clear", "hits", "flips", "overlap", "prefiltered",
         "hit_checked")


def _dump(r):
    o = r["origin"]
    d = {"x": o.X, "y": o.Y, "z": o.Z, "cell": list(r.get("cell") or (o.X, o.Y))}
    for k in _KEEP:
        if k in r:
            d[k] = r[k]
    return d


def _load(d, rg):
    r = {"origin": rg.Point3d(d["x"], d["y"], d["z"]),
         "cell": tuple(d["cell"])}
    for k in _KEEP:
        if k in d:
            r[k] = d[k]
    return r


def inside():
    import time

    cfg = dict(DEFAULTS)
    if os.path.exists(CFG):
        with io.open(CFG, encoding="utf-8") as f:
            cfg.update(json.loads(f.read()))

    lines = []

    def log(m=""):
        _log(lines, m)

    env = _setup(cfg, log)
    if env is None:
        return
    bs = env["bs"]
    rg = env["rg"]

    if cfg["mode"] == "scan":
        lo = int(cfg["from"])
        hi = min(int(cfg["to"]), len(env["cells"]))
        t0 = time.time()
        with io.open(JSONL, "a", encoding="utf-8") as out:
            for k in range(lo, hi):
                x, y, cu, cv = env["cells"][k]
                r = bs.evaluate(env["targets"], rg.Point3d(x, y, env["cz"]),
                                kinds=env["kinds"], mold_pts=env["pin_pts"],
                                hit=env["hit"], direction=env["direction"])
                r["cell"] = (cu, cv)
                out.write(json.dumps(_dump(r)) + u"\n")
                out.flush()
        log("  {}~{} / {}  {:.0f}초".format(
            lo + 1, hi, len(env["cells"]), time.time() - t0))
        return

    # ── mode == "report" ───────────────────────────────
    results = []
    if os.path.exists(JSONL):
        with io.open(JSONL, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    results.append(_load(json.loads(ln), rg))
    log("")
    log(bs.report(results, env["xs"], env["ys"], top=8,
                  skipped=env["skipped"], axes=env["axes"]))

    best = bs.rank(results)
    if not best:
        return
    b = best[0]
    rb = env["rb"]
    targets = env["targets"]

    if cfg["spin"]:
        log("")
        log("방향 흔들기 (최적점에서) — '중심을 향한다'는 가정 확인:")
        base_dir = rb.base_plane_from(point=b["origin"], line=None,
                                      targets=targets)[0].XAxis
        log("  {:>+5}deg (기준) {}".format(0, _one(b)))
        for a in cfg["spin"]:
            v = rg.Vector3d(base_dir)
            v.Rotate(float(a) * 3.141592653589793 / 180.0, rg.Vector3d.ZAxis)
            r = bs.evaluate(targets, b["origin"], kinds=env["kinds"],
                            mold_pts=env["pin_pts"], hit=env["hit"],
                            direction=v)
            log("  {:>+5.0f}deg  {}".format(a, _one(r)))

    if cfg["z"]:
        log("")
        log("높이 바꿔보기 (받침대를 쓰면 얼마나 나아지는가):")
        log("  z={:>7.0f} (기준) {}".format(env["cz"], _one(b)))
        for z in cfg["z"]:
            o = rg.Point3d(b["origin"].X, b["origin"].Y, float(z))
            r = bs.evaluate(targets, o, kinds=env["kinds"],
                            mold_pts=env["pin_pts"], hit=env["hit"],
                            direction=env["direction"])
            log("  z={:>7.0f}  {}".format(z, _one(r)))

    if cfg["apply"]:
        _apply(env, b, cfg, log)


def _apply(env, b, cfg, log):
    rg = env["rg"]
    rb = env["rb"]
    doc = env["doc"]
    pt_obj = env["pt_obj"]
    dir_obj = env["dir_obj"]
    if pt_obj is None:
        log("적용 실패 — robot_base_pt 가 없다")
        return

    log("")
    old = pt_obj.Geometry.Location
    log("적용: ({:.1f}, {:.1f}, {:.1f}) -> ({:.1f}, {:.1f}, {:.1f})".format(
        old.X, old.Y, old.Z, b["origin"].X, b["origin"].Y, b["origin"].Z))
    xf = rg.Transform.Translation(b["origin"].X - old.X,
                                  b["origin"].Y - old.Y,
                                  b["origin"].Z - old.Z)
    doc.Objects.Transform(pt_obj.Id, xf, True)

    # **방향선도 같이 맞춘다.** 점만 옮기면 살아 있는 파이프라인은
    # (resolve_base_plane 이 선 방향을 쓰므로) 옛 방향으로 계산해
    # 탐색한 자세와 다른 결과가 나온다.
    if dir_obj is not None and not cfg["keep_dir"]:
        v = rb.base_plane_from(point=b["origin"], line=None,
                               targets=env["targets"])[0].XAxis
        length = dir_obj.Geometry.GetLength()
        tip = rg.Point3d(b["origin"].X + v.X * length,
                         b["origin"].Y + v.Y * length, b["origin"].Z)
        doc.Objects.Replace(dir_obj.Id, rg.LineCurve(b["origin"], tip))
        log("  방향선도 ({:.2f}, {:.2f}) 로 맞췄다 — 안 맞추면 계산이 어긋난다".format(
            v.X, v.Y))
    elif dir_obj is not None:
        doc.Objects.Transform(dir_obj.Id, xf, True)
        log("  방향선을 같이 평행이동했다 (--keep-dir)")

    doc.Views.Redraw()
    for d in [x for x in env["ghk"].Instances.DocumentServer]:
        d.NewSolution(True)
    log("  GH 재계산 요청 — Play 의 info 로 대조할 것")


def _one(r):
    """후보 한 줄 요약."""
    if not r.get("ok"):
        return "기각: " + r["reason"]
    return "관절여유 {:>5.1f} ({})  간섭 {}  오버라이드 {:.1f}%".format(
        r["j_margin"], r["j_worst"],
        ("{:.0f}mm".format(r["clear"]) if r.get("clear") is not None
         else "미검사"),
        r["min_override"] * 100.0)


# ══════════════════════════════════════════════════════════
# 밖 — 옵션 파싱 + 조각 디스패치
# ══════════════════════════════════════════════════════════

def _parse(argv):
    cfg = dict(DEFAULTS)
    cfg["resume"] = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--step":
            cfg["step"] = float(argv[i + 1]); i += 2
        elif a == "--span":
            cfg["span"] = float(argv[i + 1]); i += 2
        elif a == "--at":
            cfg["at"] = [float(argv[i + 1]), float(argv[i + 2])]; i += 3
        elif a == "--no-hit":
            cfg["hit"] = False; i += 1
        elif a == "--keep-dir":
            cfg["keep_dir"] = True; i += 1
        elif a == "--spin":
            cfg["spin"] = [float(v) for v in argv[i + 1].split(",")]; i += 2
        elif a == "--z":
            cfg["z"] = [float(v) for v in argv[i + 1].split(",")]; i += 2
        elif a == "--apply":
            cfg["apply"] = True; i += 1
        elif a == "--polar":
            cfg["polar"] = [float(v) for v in argv[i + 1].split(",")]; i += 2
        elif a == "--angles":
            cfg["angles"] = [float(v) for v in argv[i + 1].split(",")]; i += 2
        elif a == "--chunk":
            cfg["chunk"] = int(argv[i + 1]); i += 2
        elif a == "--resume":
            cfg["resume"] = True; i += 1
        else:
            return None, "모르는 옵션: {}".format(a)
        continue
    return cfg, None


def _count(cfg):
    if cfg["polar"]:
        r0, r1, dr = cfg["polar"]
        a0, a1, da = cfg["angles"]
        nr = int(round(abs(r1 - r0) / dr)) + 1
        na = int(round(abs(a1 - a0) / da)) + 1
        return nr * na, "고리 {}반경 x {}각도".format(nr, na)
    n = int(round(2.0 * cfg["span"] / cfg["step"])) + 1
    return n * n, "격자 {}x{}".format(n, n)


def outside(argv):
    import socket

    sys.path.insert(0, HERE)
    from rhino_cli import Rhino as BridgeConn

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    cfg, err = _parse(argv)
    if err:
        print(err)
        print(__doc__)
        return 2

    total, shape = _count(cfg)
    per = SEC_WORST_CANDIDATE + (SEC_HIT if cfg["hit"] else 0.0)
    chunk = max(1, int(cfg["chunk"]))
    print("{} = {}개, {}개씩 {}조각".format(
        shape, total, chunk, (total + chunk - 1) // chunk))
    print("조각 타임아웃 {:.0f}초 (최악 후보 {:.0f}초 기준)".format(
        chunk * per + 60.0, per))
    if cfg["apply"]:
        print("** --apply: 최적점으로 robot_base_pt 를 실제로 옮긴다")

    done = 0
    if cfg["resume"] and os.path.exists(JSONL):
        with io.open(JSONL, encoding="utf-8") as f:
            done = sum(1 for ln in f if ln.strip())
        print("이어서: 이미 {}개 있음".format(done))
    else:
        for p in (JSONL, LOG):
            if os.path.exists(p):
                os.remove(p)        # 없으면 "안 돌았다"로 판정되게

    me = os.path.abspath(__file__)
    code = (u'import Rhino\n'
            u'Rhino.RhinoApp.RunScript(\'_-RunPythonScript "%s"\', True)\n'
            % me.replace("\\", "\\\\"))

    def dispatch(mode, lo=0, hi=0, timeout=300):
        c = dict(cfg)
        c["mode"] = mode
        c["from"] = lo
        c["to"] = hi
        with io.open(CFG, "w", encoding="utf-8") as f:
            f.write(json.dumps(c))
        conn = BridgeConn(timeout=timeout)
        try:
            conn.py(code)
        finally:
            conn.close()

    try:
        k = done
        while k < total:
            hi = min(k + chunk, total)
            dispatch("scan", k, hi, timeout=int(chunk * per + 60.0))
            with io.open(JSONL, encoding="utf-8") as f:
                have = sum(1 for ln in f if ln.strip())
            print("  {}/{} 완료".format(have, total))
            if have <= k:
                print("진행이 없다 — 중단한다 (로그를 볼 것: {})".format(LOG))
                return 1
            k = have
        dispatch("report", timeout=600)
    except socket.timeout:
        print("조각이 타임아웃했다. Rhino 안에서는 계속 돌고 있을 수 있다 —")
        print("잠시 뒤 --resume 으로 이어서 돌릴 것.")
        return 1
    except socket.error as exc:
        print("브리지에 연결할 수 없다: {}".format(exc))
        print("Rhino 8 을 띄우고 명령창에 mcpstart 를 입력할 것.")
        return 2

    if not os.path.exists(LOG):
        print("로그가 생기지 않았다 — 실행되지 않았다.")
        return 1
    with io.open(LOG, encoding="utf-8") as f:
        print(f.read())
    return 0


if INSIDE:
    # **traceback 을 로그에 남긴다.** 안 남기면 로그가 중간에 끊긴 것만 보이고
    # 원인이 사라진다 — Rhino 콘솔은 밖에서 보이지 않는다.
    try:
        inside()
    except Exception:
        import traceback
        with io.open(LOG, "a", encoding="utf-8") as _f:
            _f.write(u"\n\n*** 예외 ***\n" + traceback.format_exc())
        raise
elif __name__ == "__main__":
    sys.exit(outside(sys.argv[1:]))
