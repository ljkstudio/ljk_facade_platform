# 복곡면 블랭크 전개 v1 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 복곡면 패널 한 장을 성형 전 블랭크(재단 도형)로 펴는 Grasshopper 컴포넌트 `UFv1 Flatten` / `UFv1 Material` 을 만든다.

**Architecture:** ARAP(as-rigid-as-possible) 평탄화를 local-global 반복으로 푼다. 코어는 Rhino 없이 도는 순수 파이썬이고, Rhino 의존은 `rhino_io.py` 한 파일에만 둔다. 선형해는 켤레기울기(CG)이며 numpy 는 있으면 쓰는 가속기이지 의존성이 아니다.

**Tech Stack:** Python 3.9+ (Rhino 8 py39 호환), pytest 9, numpy(선택), RhinoCommon(어댑터에서만), Grasshopper Python 3 스크립트 컴포넌트

**Spec:** `docs/superpowers/specs/2026-08-14-unfold-blank-development-design.md`

## Global Constraints

- **저장소·브랜치**: `26_AdaptiveMold_development`, 브랜치 `feature/unfold-v1`
- **단위는 항상 mm.** 다른 단위를 쓰면 변수명에 명시한다.
- **`unfold/src/` 의 `rhino_io.py` 를 제외한 모든 모듈은 Rhino 를 import 하지 않는다.** 이걸 어기면 pytest 가 안 돈다.
- **Python 3.9 문법 상한.** Rhino 8 py39 에서 돌아야 한다. `match`, `X | Y` 타입 문법, `list[int]` 어노테이션(런타임 평가되는 자리) 금지. 타입힌트는 주석 스타일(`# type: (...) -> ...`) 을 쓴다 — `adaptive_mold/gh_components/path_setup.py` 와 같은 방식.
- **numpy 를 import 하되 없으면 동작해야 한다.** `try: import numpy except ImportError: numpy = None`
- **부호 규약 (spec §3.1)** — 야코비안 특이값 `σ = (평면 길이)/(3D 길이)`
  - `σ < 1` : 평탄화에서 줄어듦 → **성형에서 늘어남**, 변형률 `1/σ − 1`. 정상.
  - `σ > 1` : 평탄화에서 늘어남 → **성형에서 압축됨**. 주름 위험.
  - 변수명은 `sigma` 를 쓴다. `lambda` 는 파이썬 예약어이고 spec 초안에서 한 번 부호가 뒤집혔다.
- **미판정을 통과로 치지 않는다.** 검사하지 않은 항목은 `warn` 에 "미판정"으로 남긴다. 통과한 항목도 적는다.
- **매직 넘버 금지.** 임계값은 모듈 상단 상수로 두고 이름을 준다.
- **테스트 실행**: `python -m pytest unfold/tests -q` (저장소 루트에서)
- **커밋 메시지**: Conventional Commits. 스코프는 `unfold`. 예: `feat(unfold): topology 위상 검사`

---

## File Structure

| 파일 | 책임 | Rhino |
|---|---|---|
| `unfold/src/topology.py` | 반엣지 인접, 경계 루프 추출, 다양체·연결성·방향 검사 | 없음 |
| `unfold/src/element.py` | 삼각형 국소 등거리 좌표계, 면적, cotangent 가중 | 없음 |
| `unfold/src/material.py` | `MaterialProps` + 검증 + 등급(형상/판정/기록) 기록 | 없음 |
| `unfold/src/solver.py` | 희소행렬 + CG. numpy 백엔드 감지 | 없음 |
| `unfold/src/initial.py` | 최적평면 투영 → 뒤집힘 검사 → Tutte 폴백 | 없음 |
| `unfold/src/energy.py` | 2×2 부호 SVD, ARAP local 단계, 요소 에너지, 주름 가중 | 없음 |
| `unfold/src/flatten.py` | local-global 조립, 게이지 고정, `FlattenResult` | 없음 |
| `unfold/src/metrics.py` | 요소별 σ, 성형 변형률, 주름·찢어짐 판정 | 없음 |
| `unfold/src/blank.py` | 경계 추출 → 단순화 → 바깥 오프셋 → 자기교차 검사 | 없음 |
| `unfold/src/report.py` | 사람이 읽는 요약 + `warn` 목록 | 없음 |
| `unfold/src/pipeline.py` | 공개 진입점 `run()` — 위 전부를 엮는다 | 없음 |
| `unfold/src/rhino_io.py` | Brep→메쉬, 결과→Curve/Mesh | **있음** |
| `unfold/gh_scripts/UFv1_Material.py` | GH 어댑터 | 있음 |
| `unfold/gh_scripts/UFv1_Flatten.py` | GH 어댑터 | 있음 |
| `unfold/tools/build_uf_components.py` | 컴포넌트 파라미터 정렬·코드 push | 있음 |

의존 방향은 한 방향이다:

```
topology ─┬─> element ─┬─> energy ──┐
          │            │            ├─> flatten ─> metrics ─> blank ─> report ─> pipeline
          └─> initial <─┴─> solver ──┘
material ────────────────────────────────────────────────────────────┘
```

---

## Task 1: 패키지 뼈대 + `topology.py`

**Files:**
- Create: `unfold/src/__init__.py`, `unfold/src/topology.py`, `unfold/tests/conftest.py`, `unfold/tests/test_topology.py`
- Modify: `pyproject.toml:18-20`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `topology.build(n_verts, faces) -> Topology`
  - `Topology` 속성: `.n_verts:int`, `.faces:list`, `.boundary_loops:list[list[int]]`, `.problems:list[str]`, `.ok:bool`
  - `faces` 는 `(i, j, k)` 정수 3튜플의 리스트. 반시계 방향이 앞면.

- [ ] **Step 1: 폴더와 conftest 를 만든다**

`unfold/src/__init__.py` — 빈 파일.

`unfold/tests/conftest.py`:

```python
# -*- coding: utf-8 -*-
"""unfold/src 를 import 경로에 넣는다.

`unfold` 를 설치 가능한 패키지로 만들지 않는 이유: `adaptive_mold/src` 와 같은
방식(평평한 모듈)을 쓰면 Rhino 안에서도 sys.path 하나만 추가하면 되기 때문이다.
"""

import os
import sys

_SRC = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
```

`pyproject.toml` 18-20 줄을 다음으로 바꾼다:

```toml
[tool.pytest.ini_options]
testpaths = ["tests", "unfold/tests"]
pythonpath = ["."]
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`unfold/tests/test_topology.py`:

```python
# -*- coding: utf-8 -*-
"""topology.py 테스트 — 위상 검사가 나쁜 메쉬를 실제로 걸러내는가.

**핵심은 "통과시키지 않는 것"이다.** 나쁜 메쉬를 통과시키면 솔버가 발산하는
대신 그럴듯한 틀린 답을 낸다. 그래서 각 결함마다 걸리는지를 따로 확인한다.
"""

import topology as tp


TRI = [(0, 1, 2)]
SQUARE = [(0, 1, 2), (0, 2, 3)]
# 바깥 사각 0-3, 안쪽 사각 4-7 을 잇는 고리 (구멍 1개)
ANNULUS = [(0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
           (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
# 바깥으로 방향이 맞춰진 사면체 (닫힌 메쉬)
TETRA = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]


def joined(t):
    return " / ".join(t.problems)


def test_single_triangle_is_a_disk():
    t = tp.build(3, TRI)
    assert t.ok, joined(t)
    assert len(t.boundary_loops) == 1
    assert sorted(t.boundary_loops[0]) == [0, 1, 2]


def test_square_boundary_loop_is_four_vertices_in_order():
    t = tp.build(4, SQUARE)
    assert t.ok, joined(t)
    assert len(t.boundary_loops) == 1
    loop = t.boundary_loops[0]
    assert len(loop) == 4
    # 순환열이므로 시작점은 자유롭지만 이웃 관계는 고정이다
    ring = loop + loop
    assert any(ring[i:i + 4] == [0, 1, 2, 3] for i in range(4))


def test_index_out_of_range_is_rejected():
    t = tp.build(3, [(0, 1, 9)])
    assert not t.ok
    assert "범위 밖" in joined(t)


def test_degenerate_face_is_rejected():
    t = tp.build(3, [(0, 1, 1)])
    assert not t.ok
    assert "중복" in joined(t)


def test_non_manifold_edge_is_rejected():
    # 엣지 {0,1} 을 면 셋이 공유한다
    t = tp.build(5, [(0, 1, 2), (1, 0, 3), (0, 1, 4)])
    assert not t.ok
    assert "비다양체" in joined(t)


def test_inconsistent_orientation_is_rejected():
    # 두 면이 같은 방향으로 엣지 (0,2) 를 쓴다 → 앞뒤가 어긋났다
    t = tp.build(4, [(0, 1, 2), (0, 2, 3), (0, 2, 1)])
    assert not t.ok
    assert "방향" in joined(t) or "비다양체" in joined(t)


def test_disconnected_shells_are_rejected():
    t = tp.build(6, [(0, 1, 2), (3, 4, 5)])
    assert not t.ok
    assert "덩어리" in joined(t)


def test_closed_mesh_has_no_boundary_and_is_rejected():
    t = tp.build(4, TETRA)
    assert not t.ok
    assert "경계가 없" in joined(t)
    assert t.boundary_loops == []


def test_hole_makes_two_loops_and_is_rejected():
    t = tp.build(8, ANNULUS)
    assert len(t.boundary_loops) == 2
    assert not t.ok
    assert "구멍" in joined(t)


def test_problems_are_readable_korean_sentences():
    """진단이 사람에게 도달해야 한다 — 코드만 뱉으면 아무도 안 고친다."""
    t = tp.build(3, [(0, 1, 9)])
    assert t.problems
    for msg in t.problems:
        assert len(msg) > 8
        assert "면" in msg or "엣지" in msg or "정점" in msg
```

- [ ] **Step 3: 테스트가 실패하는지 확인한다**

Run: `python -m pytest unfold/tests/test_topology.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'topology'`

- [ ] **Step 4: `topology.py` 를 구현한다**

```python
# -*- coding: utf-8 -*-
"""삼각망의 위상을 검사하고 경계 루프를 뽑는다.

**여기서 걸러내지 못한 결함은 솔버에서 오류가 아니라 그럴듯한 틀린 답이 된다.**
그래서 통과 기준을 좁게 잡는다 — 전개할 수 있는 것은 구멍 없는 원판 하나뿐이다.

  · 삼각형이 아니거나 정점이 중복    → 거부
  · 인덱스가 범위 밖                  → 거부
  · 엣지를 면 셋 이상이 공유(비다양체) → 거부
  · 같은 유향 엣지가 둘 이상(방향 어긋남) → 거부
  · 면 덩어리가 둘 이상               → 거부
  · 경계 루프가 0개(닫힘) 또는 2개 이상(구멍) → 거부
"""

from collections import defaultdict


class Topology(object):
    """검사 결과. `ok` 가 False 면 `problems` 에 이유가 한국어로 들어 있다."""

    def __init__(self, n_verts, faces, boundary_loops, problems):
        # type: (int, list, list, list) -> None
        self.n_verts = n_verts
        self.faces = faces
        self.boundary_loops = boundary_loops
        self.problems = problems

    @property
    def ok(self):
        # type: () -> bool
        return not self.problems


def _check_faces(n_verts, faces):
    # type: (int, list) -> list
    """면 자체의 결함. 여기서 걸리면 뒤 검사는 의미가 없다."""
    problems = []
    for fi, f in enumerate(faces):
        if len(f) != 3:
            problems.append("면 %d: 정점이 %d개다 — 삼각형이 아니다" % (fi, len(f)))
            continue
        if len(set(f)) != 3:
            problems.append("면 %d: 정점이 중복이다 %r" % (fi, tuple(f)))
        for v in f:
            if v < 0 or v >= n_verts:
                problems.append(
                    "면 %d: 정점 인덱스 %d 가 범위 밖이다 (0..%d)" % (fi, v, n_verts - 1))
    return problems


def _directed(faces):
    # type: (list) -> list
    out = []
    for fi, (a, b, c) in enumerate(faces):
        out.append(((a, b), fi))
        out.append(((b, c), fi))
        out.append(((c, a), fi))
    return out


def _components(faces, undirected):
    # type: (list, dict) -> int
    """면을 공유 엣지로 이어 붙여 덩어리 수를 센다 (union-find)."""
    parent = list(range(len(faces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for _e, fis in undirected.items():
        for other in fis[1:]:
            ra, rb = find(fis[0]), find(other)
            if ra != rb:
                parent[ra] = rb
    return len(set(find(i) for i in range(len(faces))))


def _loops(boundary_next):
    # type: (dict) -> list
    """경계 유향 엣지를 이어 순환열로 만든다."""
    loops = []
    unused = dict(boundary_next)
    while unused:
        start = next(iter(unused))
        loop = [start]
        cur = unused.pop(start)
        while cur != start:
            loop.append(cur)
            nxt = unused.pop(cur, None)
            if nxt is None:      # 끊긴 경계 — 위에서 이미 거부됐어야 한다
                break
            cur = nxt
        loops.append(loop)
    return loops


def build(n_verts, faces):
    # type: (int, list) -> Topology
    """위상을 검사하고 경계 루프를 뽑는다."""
    faces = [tuple(f) for f in faces]
    problems = _check_faces(n_verts, faces)
    if problems:
        return Topology(n_verts, faces, [], problems)

    dir_count = defaultdict(int)
    for e, _fi in _directed(faces):
        dir_count[e] += 1
    for e, n in sorted(dir_count.items()):
        if n > 1:
            problems.append(
                "엣지 %d→%d 를 면 %d개가 같은 방향으로 쓴다 — 면 방향이 어긋났다" % (e[0], e[1], n))

    undirected = defaultdict(list)
    for e, fi in _directed(faces):
        undirected[(min(e), max(e))].append(fi)
    for e, fis in sorted(undirected.items()):
        if len(fis) > 2:
            problems.append("엣지 %d-%d 를 면 %d개가 공유한다 — 비다양체다" % (e[0], e[1], len(fis)))

    n_comp = _components(faces, undirected)
    if n_comp > 1:
        problems.append("면 덩어리가 %d개다 — 한 장씩 나눠서 넣어야 한다" % n_comp)

    boundary_next = {}
    for (a, b), _n in dir_count.items():
        if (b, a) not in dir_count:
            boundary_next[a] = b
    loops = _loops(boundary_next)

    if not loops:
        problems.append("경계가 없다 — 닫힌 메쉬는 한 장으로 펼 수 없다")
    elif len(loops) > 1:
        problems.append("경계 루프가 %d개다 — 구멍이 있다. 구멍은 v1 범위 밖이다" % len(loops))

    return Topology(n_verts, faces, loops, problems)
```

- [ ] **Step 5: 테스트가 통과하는지 확인한다**

Run: `python -m pytest unfold/tests/test_topology.py -q`
Expected: PASS (11 passed)

- [ ] **Step 6: 커밋**

```bash
git add unfold/src/__init__.py unfold/src/topology.py unfold/tests/conftest.py unfold/tests/test_topology.py pyproject.toml
git commit -m "feat(unfold): 위상 검사 — 전개할 수 없는 메쉬를 앞에서 끊는다"
```

---

## Task 2: `element.py` — 국소 등거리 좌표계와 cotangent

**Files:**
- Create: `unfold/src/element.py`, `unfold/tests/test_element.py`

**Interfaces:**
- Consumes: 없음 (좌표는 `(x, y, z)` 실수 3튜플의 리스트)
- Produces:
  - `element.local_frame(p0, p1, p2) -> ((0.0,0.0), (a,0.0), (b,c))` — 3D 삼각형을 길이를 보존한 채 평면에 놓은 좌표
  - `element.area(p0, p1, p2) -> float`
  - `element.cotangents(p0, p1, p2) -> (cot0, cot1, cot2)` — 정점 i 에서의 각의 cotangent
  - `element.prepare(verts, faces) -> list[ElementData]`
  - `ElementData` 속성: `.local:tuple`, `.area:float`, `.cot:tuple`, `.inv:tuple` (2×2 역행렬을 `(m00,m01,m10,m11)` 로)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`unfold/tests/test_element.py`:

```python
# -*- coding: utf-8 -*-
"""element.py 테스트 — 국소 좌표계가 길이를 보존하는가, cotangent 가 맞는가."""

import math

import element as el


def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


RIGHT = ((0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (0.0, 4.0, 0.0))   # 3-4-5 직각삼각형
EQUI = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.5, math.sqrt(3) / 2, 0.0))


def test_local_frame_preserves_all_three_edge_lengths():
    """이게 무너지면 '등거리'가 거짓이 되고 변형률 전체가 틀린다."""
    p = ((1.0, 2.0, 3.0), (4.0, 0.0, 5.0), (-2.0, 1.0, 7.0))
    loc = el.local_frame(*p)
    for i in range(3):
        j = (i + 1) % 3
        assert abs(dist(p[i], p[j]) - dist(loc[i], loc[j])) < 1e-9


def test_local_frame_puts_first_edge_on_x_axis():
    loc = el.local_frame(*RIGHT)
    assert loc[0] == (0.0, 0.0)
    assert abs(loc[1][0] - 3.0) < 1e-12 and abs(loc[1][1]) < 1e-12
    assert loc[2][1] > 0.0          # 세 번째 점은 항상 y > 0 (앞면 방향)


def test_area_matches_hand_computation():
    assert abs(el.area(*RIGHT) - 6.0) < 1e-12


def test_cotangent_of_equilateral_is_one_over_sqrt3():
    for c in el.cotangents(*EQUI):
        assert abs(c - 1.0 / math.sqrt(3)) < 1e-9


def test_cotangent_of_right_angle_is_zero():
    cots = el.cotangents(*RIGHT)
    assert abs(cots[0]) < 1e-12       # 정점 0 이 직각이다
    assert cots[1] > 0 and cots[2] > 0


def test_cotangent_is_invariant_under_rigid_motion():
    """좌표계를 바꿔도 각은 그대로여야 한다."""
    p = ((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.7, 1.3, 0.0))
    moved = tuple((x + 10.0, z - 4.0, y + 1.0) for (x, y, z) in p)   # 회전 + 평행이동
    a = el.cotangents(*p)
    b = el.cotangents(*moved)
    # 축을 바꾸면 정점 순서가 아니라 성분 대응만 바뀐다 — 집합으로 비교한다
    assert all(abs(x - y) < 1e-9 for x, y in zip(sorted(a), sorted(b)))


def test_prepare_returns_one_entry_per_face_with_usable_inverse():
    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
    faces = [(0, 1, 2), (0, 2, 3)]
    data = el.prepare(verts, faces)
    assert len(data) == 2
    for d in data:
        assert d.area > 0
        m00, m01, m10, m11 = d.inv
        assert abs(m00 * m11 - m01 * m10) > 0    # 특이하지 않다


def test_zero_area_triangle_raises():
    """퇴화 삼각형은 조용히 통과시키면 안 된다 — 역행렬이 폭발한다."""
    try:
        el.prepare([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)], [(0, 1, 2)])
    except el.DegenerateTriangle as ex:
        assert "0" in str(ex) or "퇴화" in str(ex)
    else:
        raise AssertionError("퇴화 삼각형이 통과했다")
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest unfold/tests/test_element.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'element'`

- [ ] **Step 3: `element.py` 를 구현한다**

```python
# -*- coding: utf-8 -*-
"""삼각형 하나의 기하 — 국소 등거리 좌표계, 면적, cotangent 가중.

**국소 좌표계가 이 프로젝트의 기준자다.** 3D 삼각형을 길이를 하나도 바꾸지 않고
평면에 눕힌 것이고, 전개 결과를 여기에 견주어 변형률을 잰다. 길이 보존이
깨지면 그 뒤의 모든 수치가 조용히 틀린다.

    p0 → (0, 0)
    p1 → (|p1-p0|, 0)
    p2 → (투영 길이, 남은 높이)     ← 항상 y > 0
"""

import math

MIN_AREA = 1e-12       # mm^2. 이보다 작으면 퇴화로 본다


class DegenerateTriangle(Exception):
    """면적이 0 에 가까운 삼각형. 역행렬이 폭발하므로 앞에서 끊는다."""


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(a):
    return math.sqrt(_dot(a, a))


def local_frame(p0, p1, p2):
    # type: (tuple, tuple, tuple) -> tuple
    """3D 삼각형을 길이를 보존한 채 평면에 놓는다."""
    e1 = _sub(p1, p0)
    e2 = _sub(p2, p0)
    a = _norm(e1)
    if a <= 0.0:
        raise DegenerateTriangle("첫 변의 길이가 0 이다 — 퇴화 삼각형")
    ux = (e1[0] / a, e1[1] / a, e1[2] / a)
    b = _dot(e2, ux)
    h2 = _dot(e2, e2) - b * b
    c = math.sqrt(h2) if h2 > 0.0 else 0.0
    return ((0.0, 0.0), (a, 0.0), (b, c))


def area(p0, p1, p2):
    # type: (tuple, tuple, tuple) -> float
    return 0.5 * _norm(_cross(_sub(p1, p0), _sub(p2, p0)))


def cotangents(p0, p1, p2):
    # type: (tuple, tuple, tuple) -> tuple
    """정점 i 에서의 각의 cotangent. cot θ = (u·v) / |u×v|, |u×v| = 2·면적."""
    two_a = 2.0 * area(p0, p1, p2)
    if two_a <= 0.0:
        raise DegenerateTriangle("면적이 0 이다 — 퇴화 삼각형")
    p = (p0, p1, p2)
    out = []
    for i in range(3):
        u = _sub(p[(i + 1) % 3], p[i])
        v = _sub(p[(i + 2) % 3], p[i])
        out.append(_dot(u, v) / two_a)
    return tuple(out)


class ElementData(object):
    """요소 하나의 사전계산 결과. 반복 중에 바뀌지 않는다."""

    __slots__ = ("local", "area", "cot", "inv")

    def __init__(self, local, area_, cot, inv):
        self.local = local
        self.area = area_
        self.cot = cot
        self.inv = inv


def prepare(verts, faces):
    # type: (list, list) -> list
    """모든 면의 국소 좌표·면적·cotangent·역행렬을 한 번에 계산한다."""
    out = []
    for fi, (i, j, k) in enumerate(faces):
        p0, p1, p2 = verts[i], verts[j], verts[k]
        a = area(p0, p1, p2)
        if a < MIN_AREA:
            raise DegenerateTriangle("면 %d: 면적이 %g 로 0 에 가깝다 — 퇴화 삼각형" % (fi, a))
        loc = local_frame(p0, p1, p2)
        # 국소 엣지행렬 D = [[x1-x0, x2-x0], [y1-y0, y2-y0]] = [[a, b], [0, c]]
        m00 = loc[1][0] - loc[0][0]
        m01 = loc[2][0] - loc[0][0]
        m10 = loc[1][1] - loc[0][1]
        m11 = loc[2][1] - loc[0][1]
        det = m00 * m11 - m01 * m10
        inv = (m11 / det, -m01 / det, -m10 / det, m00 / det)
        out.append(ElementData(loc, a, cotangents(p0, p1, p2), inv))
    return out
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest unfold/tests/test_element.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: 커밋**

```bash
git add unfold/src/element.py unfold/tests/test_element.py
git commit -m "feat(unfold): 삼각형 국소 등거리 좌표계 + cotangent 가중"
```

---

## Task 3: `material.py` — 물성과 등급

**Files:**
- Create: `unfold/src/material.py`, `unfold/tests/test_material.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `material.MaterialProps(name="", thickness=None, elong_max=None, wrinkle_penalty=1.0, source="")`
  - 속성 `.problems:list[str]`, `.notes:list[str]`, `.ok:bool`
  - `material.DEFAULT` — 기본 물성 인스턴스 (`wrinkle_penalty=1.0`, 나머지 없음)
  - `MaterialProps.describe() -> str` — 등급별로 무엇이 작동했는지 적은 여러 줄 문자열

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`unfold/tests/test_material.py`:

```python
# -*- coding: utf-8 -*-
"""material.py 테스트 — 등급이 실제로 지켜지는가.

**가짜 손잡이를 막는 것이 이 모듈의 존재 이유다.** 형상을 바꾸지 않는 값을
받아 놓고 조용히 있으면, 사용자는 조정하고 있다고 믿는데 아무 일도 안 일어난다.
그래서 describe() 가 무엇이 작동했고 무엇이 기록만인지 반드시 말하게 한다.
"""

import material as mt


def test_default_is_the_proven_path():
    """기본값은 증명된 경로여야 한다 — 단조 감소가 보장되는 k=1."""
    assert mt.DEFAULT.wrinkle_penalty == 1.0


def test_wrinkle_penalty_below_one_is_rejected():
    """1 미만이면 부호가 뒤집혀 주름을 오히려 키운다."""
    p = mt.MaterialProps(wrinkle_penalty=0.5)
    assert not p.ok
    assert any("wrinkle_penalty" in m for m in p.problems)


def test_negative_thickness_is_rejected():
    p = mt.MaterialProps(thickness=-1.0)
    assert not p.ok
    assert any("두께" in m for m in p.problems)


def test_elongation_out_of_range_is_rejected():
    for bad in (-0.1, 1.5):
        p = mt.MaterialProps(elong_max=bad)
        assert not p.ok, "elong_max=%r 가 통과했다" % bad


def test_elongation_is_a_fraction_not_a_percent():
    """0.12 는 12%다. 12 를 넣으면 1200% 라 반드시 걸려야 한다."""
    assert mt.MaterialProps(elong_max=0.12).ok
    assert not mt.MaterialProps(elong_max=12.0).ok


def test_missing_source_is_a_note_not_an_error():
    """출처가 없어도 계산은 되어야 한다. 다만 조용히 넘어가지는 않는다."""
    p = mt.MaterialProps(name="AL-5052", thickness=3.0, elong_max=0.12)
    assert p.ok
    assert any("출처" in m for m in p.notes)


def test_describe_says_which_fields_changed_the_shape():
    p = mt.MaterialProps(name="AL", thickness=3.0, elong_max=0.12,
                         wrinkle_penalty=2.0, source="사내 시험성적서 2026-03")
    text = p.describe()
    assert "wrinkle_penalty" in text and "형상" in text
    assert "두께" in text and "기록" in text


def test_describe_marks_unset_judgment_fields_as_unjudged():
    """미판정을 통과로 치지 않는다."""
    text = mt.MaterialProps().describe()
    assert "미판정" in text
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest unfold/tests/test_material.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'material'`

- [ ] **Step 3: `material.py` 를 구현한다**

```python
# -*- coding: utf-8 -*-
"""재료 물성 — 그리고 무엇이 실제로 작동하는지에 대한 정직한 표시.

**ARAP 에너지에는 탄성계수도 푸아송비도 들어가지 않는다.** E 를 곱해도 최소점이
그대로라 형상이 안 바뀐다. 그런 값을 받아 두면 돌려도 아무 일이 안 일어나는
가짜 손잡이가 된다 — 사용자는 조정하고 있다고 믿는데 실제로는 아무것도 안 한다.

그래서 v1 은 필드를 셋으로 나누고 describe() 가 그걸 말한다.

  형상을 바꿈 : wrinkle_penalty
  판정만      : elong_max
  기록만      : thickness, name, source

E·ν·항복곡선·FLD·r 값은 **필드조차 만들지 않는다.** v2 소성 모델과 함께 온다.
"""

MIN_PENALTY = 1.0        # 1 미만이면 부호가 뒤집힌다
MAX_ELONG = 1.0          # 100% 를 넘는 균일연신률은 입력 실수(퍼센트를 그대로 넣음)


class MaterialProps(object):
    """판재 물성. 값이 없으면 그 항목은 '미판정'이지 '통과'가 아니다."""

    def __init__(self, name="", thickness=None, elong_max=None,
                 wrinkle_penalty=1.0, source=""):
        # type: (str, float, float, float, str) -> None
        self.name = name or ""
        self.thickness = thickness
        self.elong_max = elong_max
        self.wrinkle_penalty = wrinkle_penalty
        self.source = source or ""
        self.problems = []
        self.notes = []
        self._validate()

    def _validate(self):
        if self.wrinkle_penalty is None or self.wrinkle_penalty < MIN_PENALTY:
            self.problems.append(
                "wrinkle_penalty 는 %g 이상이어야 한다 (받은 값 %r). "
                "1 미만이면 벌점의 부호가 뒤집혀 주름을 오히려 키운다"
                % (MIN_PENALTY, self.wrinkle_penalty))
        if self.thickness is not None and self.thickness <= 0.0:
            self.problems.append("두께는 0 보다 커야 한다 (받은 값 %r mm)" % (self.thickness,))
        if self.elong_max is not None:
            if self.elong_max <= 0.0 or self.elong_max > MAX_ELONG:
                self.problems.append(
                    "elong_max 는 0 초과 %g 이하의 **비율**이다 (받은 값 %r). "
                    "12%%는 12 가 아니라 0.12 다" % (MAX_ELONG, self.elong_max))
        if not self.source:
            self.notes.append(
                "출처 미기재 — 숫자가 어디서 왔는지 적어야 나중에 검증할 수 있다")
        if self.elong_max is None:
            self.notes.append("elong_max 없음 — 찢어짐 판정은 미판정으로 남는다")

    @property
    def ok(self):
        # type: () -> bool
        return not self.problems

    def describe(self):
        # type: () -> str
        """무엇이 형상을 바꿨고 무엇이 기록일 뿐인지 말한다."""
        lines = ["재료: %s" % (self.name or "(이름 없음)")]
        lines.append("  [형상] wrinkle_penalty = %g%s"
                     % (self.wrinkle_penalty,
                        "" if self.wrinkle_penalty > 1.0 else "  (1.0 — 순수 ARAP, 벌점 없음)"))
        if self.elong_max is None:
            lines.append("  [판정] elong_max 없음 — 찢어짐 **미판정**")
        else:
            lines.append("  [판정] elong_max = %.1f%%" % (self.elong_max * 100.0))
        if self.thickness is None:
            lines.append("  [기록] 두께 없음")
        else:
            lines.append("  [기록] 두께 %g mm — 막 모델이라 **형상에는 영향 없음**"
                         % self.thickness)
        lines.append("  [기록] 출처: %s" % (self.source or "미기재"))
        return "\n".join(lines)


DEFAULT = MaterialProps()
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest unfold/tests/test_material.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: 커밋**

```bash
git add unfold/src/material.py unfold/tests/test_material.py
git commit -m "feat(unfold): 물성 등급 — 형상을 바꾸는 것과 기록뿐인 것을 나눈다"
```

---

## Task 4: `solver.py` — 희소행렬과 CG (numpy 유/무 두 경로)

**Files:**
- Create: `unfold/src/solver.py`, `unfold/tests/test_solver.py`

**Interfaces:**
- Consumes: 없음
- Produces:
  - `solver.HAS_NUMPY:bool`, `solver.FORCE_PURE:bool` (테스트가 순수 경로를 강제할 때 True 로 바꾼다)
  - `solver.Sparse(n)` — `.add(i, j, v)`, `.pin(idx)`, `.matvec(x) -> seq`
  - `solver.cg(matvec, b, x0=None, tol=1e-10, maxiter=1000) -> (x, iters)`
  - `solver.tolist(x) -> list[float]` — 백엔드에 무관하게 파이썬 리스트로 되돌린다

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`unfold/tests/test_solver.py`:

```python
# -*- coding: utf-8 -*-
"""solver.py 테스트 — 두 경로가 같은 답을 내는가.

**numpy 는 의존성이 아니라 가속기다.** Rhino 8 py39 에 numpy 가 없다는 것이
실측되어 있으므로(2026-08-14), 순수 파이썬 경로가 정본이고 numpy 는 같은 답을
더 빨리 내야 한다. 그 '같은 답'을 여기서 못박는다.
"""

import math

import pytest

import solver as sv


def path_laplacian(n):
    """1차원 사슬의 라플라시안. 손으로 답을 아는 가장 단순한 SPD 계다."""
    sp = sv.Sparse(n)
    for i in range(n - 1):
        sp.add(i, i, 1.0)
        sp.add(i + 1, i + 1, 1.0)
        sp.add(i, i + 1, -1.0)
        sp.add(i + 1, i, -1.0)
    return sp


@pytest.fixture(autouse=True)
def restore_backend():
    before = sv.FORCE_PURE
    yield
    sv.FORCE_PURE = before


def test_matvec_matches_hand_computation():
    sp = sv.Sparse(3)
    sp.add(0, 0, 2.0)
    sp.add(0, 2, 1.0)
    sp.add(2, 1, -3.0)
    got = sv.tolist(sp.matvec([1.0, 2.0, 4.0]))
    assert got == pytest.approx([2.0 * 1.0 + 1.0 * 4.0, 0.0, -3.0 * 2.0])


def test_duplicate_entries_accumulate():
    """조립은 요소마다 같은 자리에 더한다 — 덮어쓰면 강성이 통째로 틀린다."""
    sp = sv.Sparse(1)
    sp.add(0, 0, 1.5)
    sp.add(0, 0, 2.5)
    assert sv.tolist(sp.matvec([2.0])) == pytest.approx([8.0])


def test_pin_replaces_row_and_column_with_identity():
    sp = path_laplacian(3)
    sp.pin(0)
    # 0번 행은 항등이고, 0번 열도 비어야 한다 (다른 행이 x[0] 을 안 본다)
    assert sv.tolist(sp.matvec([5.0, 0.0, 0.0])) == pytest.approx([5.0, 0.0, 0.0])


def test_cg_solves_a_small_spd_system_exactly():
    """A = [[4,1],[1,3]], b = [1,2] → x = [1/11, 7/11]"""
    sp = sv.Sparse(2)
    sp.add(0, 0, 4.0); sp.add(0, 1, 1.0)
    sp.add(1, 0, 1.0); sp.add(1, 1, 3.0)
    x, iters = sv.cg(sp.matvec, [1.0, 2.0], tol=1e-14)
    assert sv.tolist(x) == pytest.approx([1.0 / 11.0, 7.0 / 11.0], abs=1e-10)
    assert iters <= 2          # 2차원이면 CG 는 2회 안에 정확히 끝난다


def test_cg_solves_pinned_laplacian_with_known_answer():
    """사슬 0-1-2-3, x0 을 고정하고 끝에 힘 1 → 기울기 1 의 직선이 답이다."""
    n = 4
    sp = path_laplacian(n)
    sp.pin(0)
    b = [0.0] * n
    b[n - 1] = 1.0
    x, _ = sv.cg(sp.matvec, b, tol=1e-14, maxiter=200)
    assert sv.tolist(x) == pytest.approx([0.0, 1.0, 2.0, 3.0], abs=1e-8)


def test_pure_and_numpy_paths_agree():
    if not sv.HAS_NUMPY:
        pytest.skip("이 환경에 numpy 가 없다")
    n = 40
    b = [math.sin(i * 0.7) for i in range(n)]

    def solve():
        sp = path_laplacian(n)
        sp.pin(0)
        bb = list(b); bb[0] = 0.0
        x, _ = sv.cg(sp.matvec, bb, tol=1e-13, maxiter=2000)
        return sv.tolist(x)

    sv.FORCE_PURE = True
    pure = solve()
    sv.FORCE_PURE = False
    fast = solve()
    assert pure == pytest.approx(fast, abs=1e-8)


def test_warm_start_reduces_iterations():
    """ARAP 반복 사이에 b 가 조금만 바뀐다 — 그때 warm start 가 값어치를 한다."""
    n = 60
    sp = path_laplacian(n)
    sp.pin(0)
    b1 = [0.0] * n; b1[n - 1] = 1.0
    x1, cold = sv.cg(sp.matvec, b1, tol=1e-12, maxiter=5000)
    b2 = list(b1); b2[n - 1] = 1.001
    _x2, warm = sv.cg(sp.matvec, b2, x0=x1, tol=1e-12, maxiter=5000)
    assert warm < cold


def test_cg_reports_when_it_did_not_converge():
    """조용히 틀린 답을 돌려주면 안 된다."""
    sp = path_laplacian(50)
    sp.pin(0)
    b = [1.0] * 50; b[0] = 0.0
    _x, iters = sv.cg(sp.matvec, b, tol=1e-30, maxiter=3)
    assert iters == 3          # 상한에 걸렸음을 호출자가 알 수 있다
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest unfold/tests/test_solver.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'solver'`

- [ ] **Step 3: `solver.py` 를 구현한다**

```python
# -*- coding: utf-8 -*-
"""희소 대칭 선형계를 켤레기울기로 푼다.

**numpy 는 의존성이 아니라 가속기다.** Rhino 8 py39 site-packages 에 numpy 가
없다는 것이 실측되어 있다(2026-08-14). 그래서 순수 파이썬 경로가 정본이고,
numpy 가 있으면 같은 답을 더 빨리 낸다. 두 경로의 일치는 테스트가 지킨다.

**왜 Cholesky 가 아니라 CG 인가.** 주름 벌점을 반복 재가중(IRLS)으로 넣기
때문에 강성행렬이 매 반복 바뀐다 → 사전 분해를 재사용할 수 없다. 반면 CG 는
직전 해에서 warm start 하면 수십 회에 수렴한다. 두 결정이 서로를 지지한다.
"""

import math

try:
    import numpy
except ImportError:          # Rhino 8 py39 의 기본 상태
    numpy = None

HAS_NUMPY = numpy is not None
FORCE_PURE = False           # 테스트가 순수 경로를 강제할 때 True


class _Pure(object):
    """리스트 기반 벡터 연산."""

    @staticmethod
    def asvec(x):
        return [float(v) for v in x]

    @staticmethod
    def zeros(n):
        return [0.0] * n

    @staticmethod
    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    @staticmethod
    def sub(a, b):
        return [x - y for x, y in zip(a, b)]

    @staticmethod
    def axpy(s, x, y):
        """s*x + y"""
        return [s * xi + yi for xi, yi in zip(x, y)]


class _Numpy(object):
    """numpy 배열 기반. 인터페이스는 _Pure 와 같다."""

    @staticmethod
    def asvec(x):
        return numpy.asarray(x, dtype=numpy.float64)

    @staticmethod
    def zeros(n):
        return numpy.zeros(n, dtype=numpy.float64)

    @staticmethod
    def dot(a, b):
        return float(numpy.dot(a, b))

    @staticmethod
    def sub(a, b):
        return a - b

    @staticmethod
    def axpy(s, x, y):
        return s * x + y


def _backend():
    return _Numpy if (HAS_NUMPY and not FORCE_PURE) else _Pure


def tolist(x):
    # type: (object) -> list
    """백엔드에 무관하게 파이썬 리스트로 되돌린다."""
    return [float(v) for v in x]


class Sparse(object):
    """대칭 희소행렬. 요소 조립처럼 같은 자리에 여러 번 더한다."""

    def __init__(self, n):
        # type: (int) -> None
        self.n = n
        self._d = {}
        self._ready = False

    def add(self, i, j, v):
        # type: (int, int, float) -> None
        if v == 0.0:
            return
        k = (i, j)
        self._d[k] = self._d.get(k, 0.0) + v
        self._ready = False

    def pin(self, idx):
        # type: (int) -> None
        """정점 하나를 0 에 고정한다 — 라플라시안의 평행이동 자유도를 없앤다.

        행과 열을 **둘 다** 지운다. 열을 남기면 다른 행이 고정된 값을 계속
        보게 되어 대칭이 깨지고 CG 가 수렴하지 않는다.
        """
        for k in [k for k in self._d if k[0] == idx or k[1] == idx]:
            del self._d[k]
        self._d[(idx, idx)] = 1.0
        self._ready = False

    def _finalize(self):
        items = sorted(self._d.items())
        self._r = [ij[0] for ij, _v in items]
        self._c = [ij[1] for ij, _v in items]
        self._v = [v for _ij, v in items]
        if HAS_NUMPY:
            self._nr = numpy.array(self._r, dtype=numpy.int64)
            self._nc = numpy.array(self._c, dtype=numpy.int64)
            self._nv = numpy.array(self._v, dtype=numpy.float64)
        self._ready = True

    def matvec(self, x):
        # type: (object) -> object
        if not self._ready:
            self._finalize()
        if HAS_NUMPY and not FORCE_PURE:
            xa = numpy.asarray(x, dtype=numpy.float64)
            return numpy.bincount(self._nr, weights=self._nv * xa[self._nc],
                                  minlength=self.n)
        out = [0.0] * self.n
        for i, j, v in zip(self._r, self._c, self._v):
            out[i] += v * x[j]
        return out


def cg(matvec, b, x0=None, tol=1e-10, maxiter=1000):
    # type: (object, object, object, float, int) -> tuple
    """켤레기울기. (해, 사용한 반복 수) 를 돌려준다.

    반복 수가 maxiter 와 같으면 **수렴하지 않은 것이다.** 호출자가 그걸
    알 수 있어야 하므로 조용히 해만 돌려주지 않는다.
    """
    V = _backend()
    n = len(b)
    b = V.asvec(b)
    x = V.zeros(n) if x0 is None else V.asvec(x0)
    r = V.sub(b, V.asvec(matvec(x)))
    p = V.asvec(r)
    rs = V.dot(r, r)
    if math.sqrt(rs) <= tol:
        return x, 0
    for it in range(1, maxiter + 1):
        ap = V.asvec(matvec(p))
        pap = V.dot(p, ap)
        if pap <= 0.0:          # 준정부호 방어 — 고정을 빠뜨리면 여기 걸린다
            return x, it
        alpha = rs / pap
        x = V.axpy(alpha, p, x)
        r = V.axpy(-alpha, ap, r)
        rs_new = V.dot(r, r)
        if math.sqrt(rs_new) <= tol:
            return x, it
        p = V.axpy(rs_new / rs, p, r)
        rs = rs_new
    return x, maxiter
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest unfold/tests/test_solver.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: 커밋**

```bash
git add unfold/src/solver.py unfold/tests/test_solver.py
git commit -m "feat(unfold): 희소 CG 솔버 — numpy 는 가속기이지 의존성이 아니다"
```

---

## Task 5: 시험용 메쉬 생성기 + `initial.py` (초기 배치)

**Files:**
- Create: `unfold/tests/meshes.py`, `unfold/src/initial.py`, `unfold/tests/test_initial.py`
- Modify: `unfold/src/solver.py` (`Sparse.pin_many` 추가), `unfold/tests/test_solver.py` (테스트 1개 추가)

**Interfaces:**
- Consumes: `topology.build`, `solver.Sparse`, `solver.cg`
- Produces:
  - `meshes.plane_grid(nx, ny, w, h) -> (verts, faces)`
  - `meshes.cylinder_patch(R, beta, h, nu, nv) -> (verts, faces)` — 반경 R, 감싼 각 beta(rad), 높이 h
  - `meshes.cone_patch(alpha, l0, l1, beta, nu, nv) -> (verts, faces)` — 반각 alpha, 모선 l0..l1
  - `meshes.sphere_cap(R, theta, nr, nt) -> (verts, faces)` — 반경 R, 반각 theta
  - `initial.project(verts, faces) -> list[(x, y)]`
  - `initial.count_flips(uv, faces) -> int`
  - `initial.tutte(verts, topo) -> list[(x, y)]`
  - `initial.layout(verts, faces, topo) -> (uv, method, flips)` — `method` 는 `"projection"` 또는 `"tutte"`
  - `initial.signed_area(uv, face) -> float` (Task 7 의 `flatten.align` 이 쓴다)
  - `solver.Sparse.pin_many(values, b)` — `values` 는 `{정점: 값}`, `b` 를 제자리에서 고친다

- [ ] **Step 1: 시험용 메쉬 생성기를 쓴다**

`unfold/tests/meshes.py`:

```python
# -*- coding: utf-8 -*-
"""이론해를 아는 시험용 메쉬들. 전부 원판 위상(경계 루프 1개)이다.

전개 결과가 맞는지는 눈으로 못 본다. 그래서 **답을 아는 곡면**으로만 검사한다.

    plane_grid      전개 = 항등
    cylinder_patch  전개 가능 → 가로 R·beta, 세로 h 의 직사각형
    cone_patch      전개 가능 → 반경 l0..l1, 각 2π·sin(alpha) 의 부채꼴 띠
    sphere_cap      전개 불가 → 외곽 반경이 2R·sin(θ/2) 와 R·θ 사이
"""

import math


def _grid_faces(nx, ny):
    """(nx × ny) 격자를 삼각형으로. 방향이 전부 같도록 고정한다."""
    faces = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            b = j * nx + (i + 1)
            c = (j + 1) * nx + (i + 1)
            d = (j + 1) * nx + i
            faces.append((a, b, c))
            faces.append((a, c, d))
    return faces


def plane_grid(nx=5, ny=4, w=100.0, h=80.0):
    verts = [(w * i / (nx - 1.0), h * j / (ny - 1.0), 0.0)
             for j in range(ny) for i in range(nx)]
    return verts, _grid_faces(nx, ny)


def cylinder_patch(R=500.0, beta=0.8, h=300.0, nu=9, nv=5):
    """x-z 평면 안에서 휜 원기둥 조각. 세로(y)는 곧다."""
    verts = []
    for j in range(nv):
        y = h * j / (nv - 1.0)
        for i in range(nu):
            u = beta * i / (nu - 1.0)
            verts.append((R * math.sin(u), y, R * (1.0 - math.cos(u))))
    return verts, _grid_faces(nu, nv)


def cone_patch(alpha=0.4, l0=200.0, l1=600.0, beta=0.9, nu=9, nv=5):
    """꼭짓점이 원점, 축이 +z 인 원뿔의 조각. 모선 길이 l0..l1, 감싼 각 beta."""
    verts = []
    sa, ca = math.sin(alpha), math.cos(alpha)
    for j in range(nv):
        l = l0 + (l1 - l0) * j / (nv - 1.0)
        for i in range(nu):
            psi = beta * i / (nu - 1.0)
            verts.append((l * sa * math.cos(psi), l * sa * math.sin(psi), l * ca))
    return verts, _grid_faces(nu, nv)


def sphere_cap(R=500.0, theta=0.6, nr=6, nt=16):
    """극점 하나 + 고리 nr 겹. 원판 위상이고 축대칭이다."""
    verts = [(0.0, 0.0, R)]

    def idx(r, t):
        return 1 + (r - 1) * nt + (t % nt)

    for r in range(1, nr + 1):
        phi = theta * r / float(nr)
        for t in range(nt):
            psi = 2.0 * math.pi * t / nt
            verts.append((R * math.sin(phi) * math.cos(psi),
                          R * math.sin(phi) * math.sin(psi),
                          R * math.cos(phi)))
    faces = []
    for t in range(nt):
        faces.append((0, idx(1, t), idx(1, t + 1)))
    for r in range(1, nr):
        for t in range(nt):
            a, b = idx(r, t), idx(r + 1, t)
            c, d = idx(r + 1, t + 1), idx(r, t + 1)
            faces.append((a, b, c))
            faces.append((a, c, d))
    return verts, faces
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`unfold/tests/test_initial.py`:

```python
# -*- coding: utf-8 -*-
"""initial.py 테스트 — 초기 배치가 뒤집히지 않는가.

ARAP 은 초기 배치가 접혀 있으면 거기서 못 빠져나온다. 그래서 얕은 곡면은
투영으로 끝내되, 깊으면 Tutte 로 내려가 **뒤집힘 0 을 보장**한다.
"""

import math

import pytest

import initial as ini
import meshes
import topology as tp


def test_plane_projection_is_isometric_up_to_rigid_motion():
    verts, faces = meshes.plane_grid()
    uv = ini.project(verts, faces)
    for (i, j, k) in faces:
        for a, b in ((i, j), (j, k), (k, i)):
            d3 = math.dist(verts[a], verts[b])
            d2 = math.dist(uv[a], uv[b])
            assert abs(d3 - d2) < 1e-9


def test_shallow_patch_projects_without_flips():
    verts, faces = meshes.cylinder_patch(R=2000.0, beta=0.3)
    assert ini.count_flips(ini.project(verts, faces), faces) == 0


def test_deep_cap_projection_folds_over():
    """이 케이스가 존재하지 않으면 Tutte 폴백은 죽은 코드다."""
    verts, faces = meshes.sphere_cap(R=300.0, theta=1.4)
    assert ini.count_flips(ini.project(verts, faces), faces) > 0


def test_tutte_has_no_flips_even_on_the_deep_cap():
    verts, faces = meshes.sphere_cap(R=300.0, theta=1.4)
    topo = tp.build(len(verts), faces)
    assert topo.ok
    assert ini.count_flips(ini.tutte(verts, topo), faces) == 0


def test_tutte_puts_the_boundary_on_a_circle():
    verts, faces = meshes.sphere_cap(R=300.0, theta=1.0)
    topo = tp.build(len(verts), faces)
    uv = ini.tutte(verts, topo)
    radii = [math.hypot(uv[v][0], uv[v][1]) for v in topo.boundary_loops[0]]
    assert max(radii) - min(radii) < 1e-6


def test_layout_uses_projection_when_it_is_clean():
    verts, faces = meshes.cylinder_patch(R=2000.0, beta=0.3)
    topo = tp.build(len(verts), faces)
    _uv, method, flips = ini.layout(verts, faces, topo)
    assert method == "projection" and flips == 0


def test_layout_falls_back_to_tutte_when_projection_folds():
    verts, faces = meshes.sphere_cap(R=300.0, theta=1.4)
    topo = tp.build(len(verts), faces)
    _uv, method, flips = ini.layout(verts, faces, topo)
    assert method == "tutte" and flips == 0


def test_all_test_meshes_are_valid_disks():
    """생성기가 틀리면 뒤의 모든 검증이 무의미해진다."""
    for name, (verts, faces) in [
            ("plane", meshes.plane_grid()),
            ("cylinder", meshes.cylinder_patch()),
            ("cone", meshes.cone_patch()),
            ("cap", meshes.sphere_cap())]:
        topo = tp.build(len(verts), faces)
        assert topo.ok, "%s: %s" % (name, " / ".join(topo.problems))
        assert len(topo.boundary_loops) == 1
```

`unfold/tests/test_solver.py` 끝에 추가:

```python
def test_pin_many_moves_known_values_to_the_right_hand_side():
    """경계를 고정하고 내부만 푸는 자리. 값을 rhs 로 안 옮기면 답이 통째로 틀린다."""
    sp = path_laplacian(3)
    b = [0.0, 0.0, 0.0]
    sp.pin_many({0: 0.0, 2: 4.0}, b)
    x, _ = sv.cg(sp.matvec, b, tol=1e-14, maxiter=100)
    assert sv.tolist(x) == pytest.approx([0.0, 2.0, 4.0], abs=1e-10)
```

- [ ] **Step 3: 테스트가 실패하는지 확인한다**

Run: `python -m pytest unfold/tests/test_initial.py unfold/tests/test_solver.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'initial'` 와 `AttributeError: 'Sparse' object has no attribute 'pin_many'`

- [ ] **Step 4: `solver.Sparse.pin_many` 를 추가한다**

`unfold/src/solver.py` 의 `pin` 메서드 바로 뒤에 넣는다:

```python
    def pin_many(self, values, b):
        # type: (dict, list) -> None
        """여러 정점을 주어진 값으로 고정한다 (Dirichlet 경계). `b` 를 제자리에서 고친다.

        **열의 기여를 rhs 로 옮기고 나서** 지워야 한다. 그냥 지우면 고정된 값이
        내부 방정식에서 사라져 답이 통째로 틀린다 — 오류가 아니라 조용히 틀린다.
        """
        for k, t in values.items():
            for ij in [ij for ij in self._d if ij[1] == k and ij[0] != k]:
                b[ij[0]] -= self._d[ij] * t
                del self._d[ij]
        for k, t in values.items():
            for ij in [ij for ij in self._d if ij[0] == k]:
                del self._d[ij]
            self._d[(k, k)] = 1.0
            b[k] = t
        self._ready = False
```

- [ ] **Step 5: `initial.py` 를 구현한다**

```python
# -*- coding: utf-8 -*-
"""ARAP 반복에 넣을 초기 평면 배치.

ARAP 은 접힌 초기값에서 못 빠져나온다. 그래서 두 단계로 간다.

  1. 최적평면 투영 — 얕은 외장 패널은 여기서 끝난다(뒤집힘 0)
  2. 뒤집힘이 있으면 Tutte 매립 — 원판 위상 + 볼록 경계면 **단사가 보장**된다.
     심하게 왜곡되지만 ARAP 이 회복시킨다.

**LSCM 을 쓰지 않는 이유**: 별도의 복소 최소자승 조립이 필요한데, Tutte 는
이미 있는 라플라시안 솔버를 그대로 쓴다. 등각성은 어차피 반복이 지운다.
"""

import math

import solver as sv

FLIP_TOL = 1e-12          # 부호면적이 이보다 작으면 뒤집힘/퇴화로 센다


def _tri_normal(p0, p1, p2):
    ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def _frame(n):
    """법선 n 에 직교하는 정규직교 기저 (u, v) 를 만든다."""
    ax = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    ux = (ax[1] * n[2] - ax[2] * n[1], ax[2] * n[0] - ax[0] * n[2],
          ax[0] * n[1] - ax[1] * n[0])
    ul = math.sqrt(sum(c * c for c in ux))
    u = (ux[0] / ul, ux[1] / ul, ux[2] / ul)
    v = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2],
         n[0] * u[1] - n[1] * u[0])
    return u, v


def project(verts, faces):
    # type: (list, list) -> list
    """면적 가중 평균 법선으로 정한 최적평면에 정사영한다."""
    nx = ny = nz = 0.0
    for (i, j, k) in faces:
        cx, cy, cz = _tri_normal(verts[i], verts[j], verts[k])
        nx += cx; ny += cy; nz += cz          # 외적 길이가 곧 2·면적이라 가중이 붙는다
    ln = math.sqrt(nx * nx + ny * ny + nz * nz)
    if ln <= 0.0:
        raise ValueError("면적 가중 법선이 0 이다 — 앞뒤가 상쇄됐거나 면적이 없다")
    n = (nx / ln, ny / ln, nz / ln)
    u, v = _frame(n)
    return [(p[0] * u[0] + p[1] * u[1] + p[2] * u[2],
             p[0] * v[0] + p[1] * v[1] + p[2] * v[2]) for p in verts]


def signed_area(uv, face):
    # type: (list, tuple) -> float
    a, b, c = uv[face[0]], uv[face[1]], uv[face[2]]
    return 0.5 * ((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))


def count_flips(uv, faces):
    # type: (list, list) -> int
    """부호면적이 양수가 아닌 면의 수. 다수가 음수면 통째로 뒤집힌 것이므로 한 번 뒤집어 센다."""
    neg = sum(1 for f in faces if signed_area(uv, f) <= FLIP_TOL)
    if neg > len(faces) - neg:
        flipped = [(x, -y) for (x, y) in uv]
        return sum(1 for f in faces if signed_area(flipped, f) <= FLIP_TOL)
    return neg


def tutte(verts, topo):
    # type: (list, object) -> list
    """경계를 원에 붙이고 내부를 균등 가중 라플라시안으로 푼다."""
    loop = topo.boundary_loops[0]
    lens = []
    for a in range(len(loop)):
        p, q = verts[loop[a]], verts[loop[(a + 1) % len(loop)]]
        lens.append(math.sqrt(sum((p[t] - q[t]) ** 2 for t in range(3))))
    total = sum(lens)
    if total <= 0.0:
        raise ValueError("경계 길이가 0 이다")

    radius = total / (2.0 * math.pi)      # 둘레를 보존하는 원
    fixed = {}
    acc = 0.0
    for a, vidx in enumerate(loop):
        ang = 2.0 * math.pi * acc / total
        fixed[vidx] = (radius * math.cos(ang), radius * math.sin(ang))
        acc += lens[a]

    n = len(verts)
    lap = sv.Sparse(n)
    seen = set()
    for (i, j, k) in topo.faces:
        for a, b in ((i, j), (j, k), (k, i)):
            e = (min(a, b), max(a, b))
            if e in seen:
                continue
            seen.add(e)
            lap.add(a, a, 1.0); lap.add(b, b, 1.0)
            lap.add(a, b, -1.0); lap.add(b, a, -1.0)

    out = []
    for axis in (0, 1):
        mat = sv.Sparse(n)
        for ij, val in lap._d.items():       # 축마다 같은 행렬을 새로 조립한다
            mat.add(ij[0], ij[1], val)
        rhs = [0.0] * n
        mat.pin_many(dict((v, p[axis]) for v, p in fixed.items()), rhs)
        sol, _it = sv.cg(mat.matvec, rhs, tol=1e-12, maxiter=20 * n + 200)
        out.append(sv.tolist(sol))
    return list(zip(out[0], out[1]))


def layout(verts, faces, topo):
    # type: (list, list, object) -> tuple
    """초기 배치를 정한다. (uv, method, flips) 를 돌려준다."""
    uv = project(verts, faces)
    flips = count_flips(uv, faces)
    if flips == 0:
        return uv, "projection", 0
    uv = tutte(verts, topo)
    return uv, "tutte", count_flips(uv, faces)
```

> **주의**: `tutte` 가 `lap._d` 를 직접 읽는다. 이건 같은 모듈 묶음 안의 의도된
> 접근이며, `Sparse` 에 공개 복사 메서드를 만들 만큼 쓰임이 많지 않다.
> 세 번째 사용처가 생기면 `Sparse.copy()` 로 승격한다.

- [ ] **Step 6: 테스트가 통과하는지 확인한다**

Run: `python -m pytest unfold/tests/test_initial.py unfold/tests/test_solver.py -q`
Expected: PASS (9 + 9 passed)

- [ ] **Step 7: 커밋**

```bash
git add unfold/src/initial.py unfold/src/solver.py unfold/tests/meshes.py unfold/tests/test_initial.py unfold/tests/test_solver.py
git commit -m "feat(unfold): 초기 배치 — 투영으로 끝내되 접히면 Tutte 로 내려간다"
```

---

## Task 6: `energy.py` — 야코비안, 부호 SVD, ARAP local 단계

**Files:**
- Create: `unfold/src/energy.py`, `unfold/tests/test_energy.py`

**Interfaces:**
- Consumes: `element.ElementData` (`.local`, `.area`, `.inv`)
- Produces:
  - `energy.jacobian(ed, u0, u1, u2) -> (a, b, c, d)` — 2×2 를 행 우선 4튜플로
  - `energy.singular_values(J) -> (s1, s2)` — **부호가 있다.** `s2 < 0` 이면 뒤집힘
  - `energy.closest_rotation(J) -> (a, b, c, d)` — ARAP local 단계
  - `energy.element_energy(area, s1, s2) -> float`
  - `energy.wrinkle_weight(s1, penalty) -> float`
  - `energy.WRINKLE_TOL = 1e-9`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`unfold/tests/test_energy.py`:

```python
# -*- coding: utf-8 -*-
"""energy.py 테스트 — 2×2 부호 SVD 와 최근접 회전.

**부호가 이 모듈의 전부다.** σ = (평면 길이)/(3D 길이) 이고

    σ < 1  평탄화에서 줄어듦 → 성형에서 늘어남   정상
    σ > 1  평탄화에서 늘어남 → 성형에서 압축됨   주름 위험

여기서 부호를 놓치면 벌점이 반대 방향으로 걸리고, 결과는 여전히 그럴듯해 보인다.
"""

import math

import pytest

import element as el
import energy as en


TRI3D = ((0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (1.0, 2.0, 0.0))


def one_element():
    return el.prepare(list(TRI3D), [(0, 1, 2)])[0]


def rot(ang):
    c, s = math.cos(ang), math.sin(ang)
    return (c, -s, s, c)


def apply(m, p):
    return (m[0] * p[0] + m[1] * p[1], m[2] * p[0] + m[3] * p[1])


def test_identity_mapping_has_identity_jacobian():
    ed = one_element()
    J = en.jacobian(ed, *ed.local)
    assert J == pytest.approx((1.0, 0.0, 0.0, 1.0), abs=1e-12)


def test_rigid_motion_costs_nothing():
    """강체 이동은 변형이 아니다. 여기서 0 이 안 나오면 에너지 자체가 틀린 것이다."""
    ed = one_element()
    m = rot(0.9)
    moved = [tuple(x + t for x, t in zip(apply(m, p), (17.0, -4.0))) for p in ed.local]
    J = en.jacobian(ed, *moved)
    s1, s2 = en.singular_values(J)
    assert s1 == pytest.approx(1.0, abs=1e-12)
    assert s2 == pytest.approx(1.0, abs=1e-12)
    assert en.element_energy(ed.area, s1, s2) == pytest.approx(0.0, abs=1e-20)


def test_uniform_scale_gives_the_hand_computed_energy():
    ed = one_element()
    s = 1.3
    scaled = [(p[0] * s, p[1] * s) for p in ed.local]
    s1, s2 = en.singular_values(en.jacobian(ed, *scaled))
    assert s1 == pytest.approx(s) and s2 == pytest.approx(s)
    assert en.element_energy(ed.area, s1, s2) == pytest.approx(ed.area * 2.0 * (s - 1.0) ** 2)


def test_anisotropic_scale_recovers_both_singular_values():
    ed = one_element()
    stretched = [(p[0] * 2.0, p[1] * 0.5) for p in ed.local]
    s1, s2 = en.singular_values(en.jacobian(ed, *stretched))
    assert sorted([s1, s2]) == pytest.approx([0.5, 2.0])


def test_singular_values_are_signed_so_a_flip_is_visible():
    """뒤집힘을 크기만 보면 놓친다 — 접힌 채로 '변형 없음'이 된다."""
    ed = one_element()
    mirrored = [(p[0], -p[1]) for p in ed.local]
    s1, s2 = en.singular_values(en.jacobian(ed, *mirrored))
    assert s1 > 0 and s2 < 0


def test_closest_rotation_of_a_rotation_is_itself():
    for ang in (0.0, 0.4, 2.0, -1.7):
        got = en.closest_rotation(rot(ang))
        assert got == pytest.approx(rot(ang), abs=1e-12)


def test_closest_rotation_of_a_pure_stretch_is_identity():
    assert en.closest_rotation((2.0, 0.0, 0.0, 0.5)) == pytest.approx((1.0, 0.0, 0.0, 1.0),
                                                                     abs=1e-12)


def test_singular_values_multiply_to_the_determinant():
    """부호 SVD 의 정의 그 자체. 틀리면 뒤집힘 판정이 무너진다."""
    for J in ((1.2, 0.3, -0.4, 0.9), (0.5, 0.0, 0.0, -2.0), (1.0, 2.0, 3.0, 4.0)):
        s1, s2 = en.singular_values(J)
        assert s1 * s2 == pytest.approx(J[0] * J[3] - J[1] * J[2])


def test_wrinkle_weight_fires_only_when_flattening_stretched():
    """σ>1 (성형에서 압축) 일 때만 벌점이 붙는다. 반대로 걸리면 주름을 키운다."""
    assert en.wrinkle_weight(1.5, 3.0) == 3.0
    assert en.wrinkle_weight(0.7, 3.0) == 1.0
    assert en.wrinkle_weight(1.0, 3.0) == 1.0        # 경계는 벌하지 않는다


def test_wrinkle_weight_of_one_is_a_no_op():
    for s in (0.3, 1.0, 2.5):
        assert en.wrinkle_weight(s, 1.0) == 1.0
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest unfold/tests/test_energy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'energy'`

- [ ] **Step 3: `energy.py` 를 구현한다**

```python
# -*- coding: utf-8 -*-
"""ARAP 의 구성모델 — 요소 에너지와 local 단계.

**이 파일이 v2 의 교체 지점이다.** solver 와 flatten 은 "요소 하나의 에너지와
최적 목표 회전을 주면 푼다"만 알고 어떤 재료인지 모른다. 소성 모델은 여기를
갈아끼우면 된다.

부호 규약(spec §3.1) — σ = (평면 길이)/(3D 길이)

    σ < 1   평탄화에서 줄어듦 → 성형에서 늘어남 (변형률 1/σ − 1)   정상
    σ > 1   평탄화에서 늘어남 → 성형에서 압축됨                    주름 위험

특이값은 **부호를 살려서** 돌려준다. 크기만 보면 뒤집힌 요소가 '변형 없음'으로
보인다 — 접힌 채로 통과하는 가장 조용한 실패다.
"""

import math

WRINKLE_TOL = 1e-9        # σ 가 1 을 이만큼 넘어야 주름 위험으로 센다


def jacobian(ed, u0, u1, u2):
    # type: (object, tuple, tuple, tuple) -> tuple
    """국소 등거리 좌표 → 현재 평면 좌표의 야코비안. 행 우선 (a, b, c, d)."""
    d00 = u1[0] - u0[0]
    d01 = u2[0] - u0[0]
    d10 = u1[1] - u0[1]
    d11 = u2[1] - u0[1]
    i00, i01, i10, i11 = ed.inv
    return (d00 * i00 + d01 * i10, d00 * i01 + d01 * i11,
            d10 * i00 + d11 * i10, d10 * i01 + d11 * i11)


def singular_values(J):
    # type: (tuple) -> tuple
    """2×2 부호 특이값 (s1, s2). s1 ≥ |s2| 이고 s1·s2 = det(J).

    s2 < 0 이면 요소가 뒤집혔다는 뜻이다.
    """
    a, b, c, d = J
    e = (a + d) * 0.5
    f = (a - d) * 0.5
    g = (c + b) * 0.5
    h = (c - b) * 0.5
    q = math.hypot(e, h)
    r = math.hypot(f, g)
    return q + r, q - r


def closest_rotation(J):
    # type: (tuple) -> tuple
    """J 에 가장 가까운 회전행렬 (ARAP local 단계).

    2차원에서는 닫힌 형식이다 — 각도가 atan2(c−b, a+d) 로 바로 나온다.
    SVD 를 완전히 분해할 필요가 없어 라이브러리도 필요 없다.
    """
    a, b, c, d = J
    ang = math.atan2(c - b, a + d)
    cs, sn = math.cos(ang), math.sin(ang)
    return (cs, -sn, sn, cs)


def element_energy(area, s1, s2):
    # type: (float, float, float) -> float
    """면적 가중 ARAP 에너지. 회전만 하면 0 이다."""
    return area * ((s1 - 1.0) ** 2 + (s2 - 1.0) ** 2)


def wrinkle_weight(s1, penalty):
    # type: (float, float) -> float
    """σ > 1 (성형에서 압축되는 자리) 에만 벌점을 준다.

    판재는 압축을 받으면 압축되는 대신 주름진다. 그래서 그 방향을 더 강하게
    벌해 해를 '성형 시 인장만' 쪽으로 민다.
    """
    if penalty <= 1.0:
        return 1.0
    return penalty if s1 > 1.0 + WRINKLE_TOL else 1.0
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest unfold/tests/test_energy.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: 커밋**

```bash
git add unfold/src/energy.py unfold/tests/test_energy.py
git commit -m "feat(unfold): ARAP 구성모델 — 부호 있는 2x2 SVD 와 주름 벌점"
```

---

## Task 7: `flatten.py` — local-global 반복과 게이지 고정

**Files:**
- Create: `unfold/src/flatten.py`, `unfold/tests/test_flatten.py`

**Interfaces:**
- Consumes: `element.prepare`, `energy.*`, `initial.layout`, `solver.Sparse/cg`, `material.MaterialProps`
- Produces:
  - `flatten.run(verts, faces, topo, props, iters=30, tol=1e-6) -> FlattenResult`
  - `FlattenResult` 속성: `.uv:list[(x,y)]`, `.faces`, `.elements`, `.sigmas:list[(s1,s2)]`, `.energy_history:list[float]`, `.iterations:int`, `.converged:bool`, `.method:str`, `.flips:int`, `.notes:list[str]`
  - `flatten.align(uv, faces) -> list[(x, y)]`
  - `flatten.DEFAULT_ITERS = 30`, `flatten.ENERGY_TOL = 1e-6`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`unfold/tests/test_flatten.py`:

```python
# -*- coding: utf-8 -*-
"""flatten.py 테스트 — 반복이 옳은 방향으로 가는가.

이론해 대조는 Task 9(test_theory.py) 가 맡는다. 여기서는 **반복 자체의 성질**만
본다: 전개 가능한 곡면은 오차 0 으로 가는가, 에너지가 단조 감소하는가,
같은 입력이 같은 답을 내는가.
"""

import math

import pytest

import flatten as fl
import material as mt
import meshes
import topology as tp


def prep(verts, faces):
    topo = tp.build(len(verts), faces)
    assert topo.ok, " / ".join(topo.problems)
    return topo


def signature(res):
    """회전·평행이동에 무관한 지문. 축대칭 형상은 정렬 방향이 자유롭기 때문이다."""
    cx = sum(p[0] for p in res.uv) / len(res.uv)
    cy = sum(p[1] for p in res.uv) / len(res.uv)
    radii = sorted(round(math.hypot(p[0] - cx, p[1] - cy), 7) for p in res.uv)
    sig = sorted((round(a, 7), round(b, 7)) for a, b in res.sigmas)
    return radii, sig


def max_sigma_error(res):
    return max(max(abs(a - 1.0), abs(b - 1.0)) for a, b in res.sigmas)


def test_plane_is_flattened_without_distortion():
    verts, faces = meshes.plane_grid()
    res = fl.run(verts, faces, prep(verts, faces), mt.DEFAULT)
    assert max_sigma_error(res) < 1e-9
    assert res.flips == 0


def test_cylinder_is_developable_so_error_goes_to_zero():
    """전개 가능한 곡면에서 오차가 남으면 조립이나 국소 좌표계가 틀린 것이다."""
    verts, faces = meshes.cylinder_patch(nu=13, nv=7)
    res = fl.run(verts, faces, prep(verts, faces), mt.DEFAULT, iters=60)
    assert max_sigma_error(res) < 1e-4


def test_cone_is_developable_too():
    verts, faces = meshes.cone_patch(nu=13, nv=7)
    res = fl.run(verts, faces, prep(verts, faces), mt.DEFAULT, iters=60)
    assert max_sigma_error(res) < 1e-4


def test_energy_decreases_monotonically_at_penalty_one():
    """k=1 에서만 단조성이 증명된다(spec §6.3). 그 증명된 경로를 여기서 지킨다."""
    verts, faces = meshes.sphere_cap(nr=5, nt=12)
    res = fl.run(verts, faces, prep(verts, faces), mt.DEFAULT, iters=40)
    hist = res.energy_history
    assert len(hist) >= 3
    for a, b in zip(hist, hist[1:]):
        assert b <= a + 1e-12, "에너지가 늘었다: %g -> %g" % (a, b)


def test_energy_history_is_recorded_even_when_penalty_is_raised():
    """k>1 은 수렴을 증명하지 않았다 — 그래서 이력을 남겨 판단할 수 있게 한다."""
    verts, faces = meshes.sphere_cap(nr=5, nt=12)
    props = mt.MaterialProps(wrinkle_penalty=3.0, source="테스트")
    res = fl.run(verts, faces, prep(verts, faces), props, iters=20)
    assert len(res.energy_history) >= 3
    assert all(e == e for e in res.energy_history)          # NaN 이 아니다


def test_result_is_deterministic():
    verts, faces = meshes.sphere_cap(nr=4, nt=10)
    topo = prep(verts, faces)
    a = fl.run(verts, faces, topo, mt.DEFAULT, iters=15)
    b = fl.run(verts, faces, topo, mt.DEFAULT, iters=15)
    assert signature(a) == signature(b)


def test_rigid_motion_of_the_input_does_not_change_the_result():
    """좌표계 혼동을 잡는다 — 구현 실수의 대부분이 여기 걸린다."""
    verts, faces = meshes.cylinder_patch(nu=9, nv=5)
    topo = prep(verts, faces)
    base = fl.run(verts, faces, topo, mt.DEFAULT, iters=25)

    ang = 0.7
    ca, sa = math.cos(ang), math.sin(ang)
    moved = [(ca * x - sa * y + 123.0, sa * x + ca * y - 45.0, z + 9.0)
             for (x, y, z) in verts]
    other = fl.run(moved, faces, topo, mt.DEFAULT, iters=25)

    ra, sga = signature(base)
    rb, sgb = signature(other)
    assert ra == pytest.approx(rb, abs=1e-6)
    assert [x for p in sga for x in p] == pytest.approx([x for p in sgb for x in p], abs=1e-6)


def test_scaling_the_input_scales_the_blank_but_not_the_strain():
    verts, faces = meshes.sphere_cap(R=400.0, theta=0.5, nr=4, nt=12)
    topo = prep(verts, faces)
    a = fl.run(verts, faces, topo, mt.DEFAULT, iters=25)
    big = [(x * 3.0, y * 3.0, z * 3.0) for (x, y, z) in verts]
    b = fl.run(big, faces, topo, mt.DEFAULT, iters=25)

    ra, sga = signature(a)
    rb, sgb = signature(b)
    assert [r * 3.0 for r in ra] == pytest.approx(rb, abs=1e-5)
    assert [x for p in sga for x in p] == pytest.approx([x for p in sgb for x in p], abs=1e-6)


def test_face_order_does_not_change_the_result():
    verts, faces = meshes.cylinder_patch(nu=9, nv=5)
    shuffled = list(reversed(faces))
    a = fl.run(verts, faces, prep(verts, faces), mt.DEFAULT, iters=25)
    b = fl.run(verts, shuffled, prep(verts, shuffled), mt.DEFAULT, iters=25)
    ra, _ = signature(a)
    rb, _ = signature(b)
    assert ra == pytest.approx(rb, abs=1e-6)


def test_iteration_count_and_convergence_flag_are_reported():
    """조용히 상한에 걸리면 안 된다."""
    verts, faces = meshes.sphere_cap(nr=5, nt=12)
    res = fl.run(verts, faces, prep(verts, faces), mt.DEFAULT, iters=2, tol=1e-30)
    assert res.iterations == 2
    assert res.converged is False
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest unfold/tests/test_flatten.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'flatten'`

- [ ] **Step 3: `flatten.py` 를 구현한다**

```python
# -*- coding: utf-8 -*-
"""ARAP 평탄화 — local-global 반복.

    사전계산 : 요소별 국소 등거리 좌표 + cotangent (3D 원본에서 한 번)
    반복 {
      local  : 요소마다 야코비안 → 최근접 회전, 그리고 주름 가중
      global : 가중 cotangent 라플라시안 L·x = b 를 x·y 축에 대해 각각
    }

**주름 벌점을 IRLS 로 넣기 때문에 L 이 매 반복 바뀐다.** 그래서 사전 분해를
쓰지 않고 CG + warm start 로 간다(solver.py 참고).

**게이지 고정**: ARAP 해는 평행이동·회전만큼 자유도가 남는다. 정점 0 을 원점에
고정해 풀고, 마지막에 강체 정렬한다. 이게 없으면 같은 입력이 매번 다른 방향으로
나와 회귀 픽스처가 성립하지 않는다.

**축대칭 형상에서는 정렬 방향이 여전히 자유롭다**(공분산이 등방이라 주축이 없다).
그래서 테스트는 좌표가 아니라 회전 불변량으로 비교한다.
"""

import math

import element as el
import energy as en
import initial as ini
import solver as sv

DEFAULT_ITERS = 30
ENERGY_TOL = 1e-6         # 상대 에너지 변화가 이보다 작으면 수렴으로 본다
CG_REL = 1e-11            # CG 잔차 허용치 (rhs 크기에 상대적)

# 삼각형의 (엣지 국소인덱스 쌍, 마주보는 정점의 국소인덱스)
_EDGES = (((0, 1), 2), ((1, 2), 0), ((2, 0), 1))


class FlattenResult(object):
    __slots__ = ("uv", "faces", "elements", "sigmas", "energy_history",
                 "iterations", "converged", "method", "flips", "notes")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def align(uv, faces):
    # type: (list, list) -> list
    """결정론적 강체 정렬 — 무게중심을 원점에, 주축을 +X 로, 앞면을 위로."""
    n = len(uv)
    cx = sum(p[0] for p in uv) / n
    cy = sum(p[1] for p in uv) / n
    pts = [(p[0] - cx, p[1] - cy) for p in uv]

    if sum(ini.signed_area(pts, f) for f in faces) < 0.0:
        pts = [(x, -y) for (x, y) in pts]        # 통째로 뒤집혔으면 되돌린다

    sxx = sum(x * x for x, _y in pts)
    syy = sum(y * y for _x, y in pts)
    sxy = sum(x * y for x, y in pts)
    ang = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    ca, sa = math.cos(-ang), math.sin(-ang)
    pts = [(ca * x - sa * y, sa * x + ca * y) for (x, y) in pts]

    # 180도 모호성 — 3차 모멘트의 부호로 고정한다
    m3x = sum(x ** 3 for x, _y in pts)
    if m3x < 0.0:
        pts = [(-x, -y) for (x, y) in pts]
    return pts


def _local_step(elements, faces, uv, penalty):
    """요소별 최근접 회전·주름 가중·에너지를 구한다."""
    rots, weights, sigmas = [], [], []
    total = 0.0
    for t, ed in enumerate(elements):
        i, j, k = faces[t]
        jac = en.jacobian(ed, uv[i], uv[j], uv[k])
        s1, s2 = en.singular_values(jac)
        rots.append(en.closest_rotation(jac))
        weights.append(en.wrinkle_weight(s1, penalty))
        sigmas.append((s1, s2))
        total += en.element_energy(ed.area, s1, s2)
    return rots, weights, sigmas, total


def _global_step(n, elements, faces, rots, weights, prev):
    """가중 cotangent 라플라시안을 조립해 x·y 를 푼다."""
    mat = sv.Sparse(n)
    bx = [0.0] * n
    by = [0.0] * n
    for t, ed in enumerate(elements):
        f = faces[t]
        rot = rots[t]
        w_t = weights[t]
        for (p, q), opp in _EDGES:
            w = w_t * ed.cot[opp]
            i, j = f[p], f[q]
            mat.add(i, i, w); mat.add(j, j, w)
            mat.add(i, j, -w); mat.add(j, i, -w)
            dx = ed.local[p][0] - ed.local[q][0]
            dy = ed.local[p][1] - ed.local[q][1]
            rx = rot[0] * dx + rot[1] * dy
            ry = rot[2] * dx + rot[3] * dy
            bx[i] += w * rx; bx[j] -= w * rx
            by[i] += w * ry; by[j] -= w * ry

    mat.pin(0)
    bx[0] = 0.0
    by[0] = 0.0

    out = []
    for b, prev_axis in ((bx, [p[0] for p in prev]), (by, [p[1] for p in prev])):
        scale = math.sqrt(sum(v * v for v in b))
        tol = CG_REL * (scale + 1.0)
        warm = list(prev_axis)
        warm[0] = 0.0
        sol, _it = sv.cg(mat.matvec, b, x0=warm, tol=tol, maxiter=20 * n + 500)
        out.append(sv.tolist(sol))
    return list(zip(out[0], out[1]))


def run(verts, faces, topo, props, iters=DEFAULT_ITERS, tol=ENERGY_TOL):
    # type: (list, list, object, object, int, float) -> FlattenResult
    """평탄화 본체."""
    notes = []
    elements = el.prepare(verts, faces)
    uv, method, flips0 = ini.layout(verts, faces, topo)
    if method == "tutte":
        notes.append("투영이 접혀 Tutte 매립으로 초기화했다 (깊은 곡면)")
    if flips0:
        notes.append("초기 배치에 뒤집힌 요소가 %d개 남았다" % flips0)

    penalty = props.wrinkle_penalty
    history = []
    sigmas = []
    converged = False
    used = 0

    for step in range(1, iters + 1):
        rots, weights, sigmas, e_now = _local_step(elements, faces, uv, penalty)
        history.append(e_now)
        used = step
        if len(history) >= 2:
            prev = history[-2]
            if prev - e_now <= tol * max(prev, 1e-30):
                converged = True
                break
        uv = _global_step(len(verts), elements, faces, rots, weights, uv)

    # 마지막 배치에 대한 σ 를 다시 잰다 — 반복 중 값은 직전 배치의 것이다
    _r, _w, sigmas, e_final = _local_step(elements, faces, uv, penalty)
    history.append(e_final)

    uv = align(uv, faces)
    flips = ini.count_flips(uv, faces)
    if flips:
        notes.append("결과에 뒤집힌 요소가 %d개 있다 — 반복을 늘리거나 메쉬를 고르게 해야 한다" % flips)
    if not converged:
        notes.append("반복 상한 %d 에서 멈췄다 — 수렴하지 않았다" % iters)

    return FlattenResult(uv=uv, faces=faces, elements=elements, sigmas=sigmas,
                         energy_history=history, iterations=used,
                         converged=converged, method=method, flips=flips,
                         notes=notes)
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest unfold/tests/test_flatten.py -q`
Expected: PASS (10 passed)

수렴이 느려 원기둥 테스트가 `1e-4` 를 못 맞추면, **허용치를 낮추지 말고** `iters` 를 올려 확인한다. 전개 가능한 곡면에서 오차가 남는 것은 수렴 속도 문제이거나 조립이 틀린 것이다 — 둘을 구별해야 한다.

- [ ] **Step 5: 커밋**

```bash
git add unfold/src/flatten.py unfold/tests/test_flatten.py
git commit -m "feat(unfold): ARAP local-global 반복 + 결정론적 강체 정렬"
```

---

## Task 8: `metrics.py` — σ, 성형 변형률, 주름·찢어짐 판정

**Files:**
- Create: `unfold/src/metrics.py`, `unfold/tests/test_metrics.py`

**Interfaces:**
- Consumes: `flatten.FlattenResult`, `material.MaterialProps`
- Produces:
  - `metrics.evaluate(res, props) -> Metrics`
  - `Metrics` 속성: `.sigma_min:float`, `.sigma_max:float`, `.max_forming_strain:float`, `.wrinkle_faces:list[int]`, `.tear_faces:list[int]`, `.flip_faces:list[int]`, `.area_3d:float`, `.area_2d:float`, `.checks:list[(name, status, detail)]`
  - `status` 는 `"통과"`, `"경고"`, `"미판정"` 셋 중 하나
  - `metrics.forming_strain(sigma) -> float` — `1/σ − 1`
  - `metrics.WRINKLE_TOL = 1e-6`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`unfold/tests/test_metrics.py`:

```python
# -*- coding: utf-8 -*-
"""metrics.py 테스트 — 판정이 실제로 판정을 하는가.

**미판정을 통과로 치지 않는다.** elong_max 가 없으면 찢어짐은 '통과'가 아니라
'미판정'이어야 한다. 빈 경고 목록이 "검사했고 괜찮다"인지 "검사를 안 했다"인지
구별되지 않으면 이 도구는 쓸모가 없다.
"""

import pytest

import flatten as fl
import material as mt
import meshes
import metrics as mx
import topology as tp


def flat(mesh, props=None, iters=40):
    verts, faces = mesh
    topo = tp.build(len(verts), faces)
    assert topo.ok
    res = fl.run(verts, faces, topo, props or mt.DEFAULT, iters=iters)
    return res, mx.evaluate(res, props or mt.DEFAULT)


def status_of(m, name):
    for n, s, _d in m.checks:
        if n == name:
            return s
    raise AssertionError("판정 항목 %r 이 없다: %r" % (name, [c[0] for c in m.checks]))


def test_forming_strain_sign_matches_the_spec_table():
    """σ<1 은 성형에서 늘어남(양수), σ>1 은 압축(음수)."""
    assert mx.forming_strain(0.5) == pytest.approx(1.0)
    assert mx.forming_strain(1.0) == pytest.approx(0.0)
    assert mx.forming_strain(2.0) == pytest.approx(-0.5)


def test_developable_cylinder_has_no_wrinkle_and_no_tear():
    _res, m = flat(meshes.cylinder_patch(nu=13, nv=7), iters=60)
    assert m.wrinkle_faces == []
    assert status_of(m, "주름") == "통과"
    assert abs(m.sigma_max - 1.0) < 1e-3 and abs(m.sigma_min - 1.0) < 1e-3


def test_dome_must_raise_a_wrinkle_warning():
    """볼록 돔은 평탄화에서 원주방향이 반드시 늘어난다(σ>1) → 성형에서 압축.
    경고가 안 뜨면 판정 쪽이 틀린 것이다."""
    _res, m = flat(meshes.sphere_cap(R=400.0, theta=0.7, nr=6, nt=16))
    assert m.wrinkle_faces
    assert status_of(m, "주름") == "경고"
    assert m.sigma_max > 1.0


def test_tear_is_unjudged_without_an_elongation_limit():
    _res, m = flat(meshes.sphere_cap(nr=5, nt=12))
    assert status_of(m, "찢어짐") == "미판정"
    assert m.tear_faces == []


def test_tear_fires_when_the_limit_is_tight():
    props = mt.MaterialProps(elong_max=0.001, source="테스트용 극단값")
    _res, m = flat(meshes.sphere_cap(R=300.0, theta=0.9, nr=6, nt=16), props)
    assert m.tear_faces
    assert status_of(m, "찢어짐") == "경고"


def test_tear_passes_when_the_limit_is_generous():
    props = mt.MaterialProps(elong_max=0.9, source="테스트용 극단값")
    _res, m = flat(meshes.sphere_cap(R=3000.0, theta=0.2, nr=5, nt=12), props)
    assert m.tear_faces == []
    assert status_of(m, "찢어짐") == "통과"


def test_every_check_reports_even_when_it_passes():
    """통과한 것도 적는다 — 빈 목록의 뜻이 모호해지면 안 된다."""
    _res, m = flat(meshes.plane_grid())
    names = [c[0] for c in m.checks]
    for want in ("주름", "찢어짐", "뒤집힘", "수렴"):
        assert want in names
    for _n, s, d in m.checks:
        assert s in ("통과", "경고", "미판정")
        assert d, "판정에 근거가 없다"


def test_areas_are_reported_for_both_sides():
    _res, m = flat(meshes.plane_grid())
    assert m.area_3d == pytest.approx(100.0 * 80.0)
    assert m.area_2d == pytest.approx(m.area_3d, rel=1e-9)


def test_non_convergence_is_a_warning_not_silence():
    verts, faces = meshes.sphere_cap(nr=5, nt=12)
    topo = tp.build(len(verts), faces)
    res = fl.run(verts, faces, topo, mt.DEFAULT, iters=2, tol=1e-30)
    m = mx.evaluate(res, mt.DEFAULT)
    assert status_of(m, "수렴") == "경고"
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest unfold/tests/test_metrics.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'metrics'`

- [ ] **Step 3: `metrics.py` 를 구현한다**

```python
# -*- coding: utf-8 -*-
"""전개 결과의 판정 — 주름·찢어짐·뒤집힘·수렴.

부호 규약(spec §3.1) — σ = (평면 길이)/(3D 길이), 성형 변형률 = 1/σ − 1

    σ < 1  → 성형에서 늘어남 (양의 변형률). 연신 한계까지 정상
    σ > 1  → 성형에서 압축됨 (음의 변형률). 주름 위험

**미판정을 통과로 치지 않는다.** elong_max 가 없으면 찢어짐 판정은 '미판정'이다.
빈 경고 목록이 "검사했고 괜찮다"인지 "검사를 안 했다"인지 구별되지 않으면
이 도구는 쓸모가 없다.
"""

WRINKLE_TOL = 1e-6        # σ 가 1 을 이만큼 넘어야 주름 위험으로 센다
MIN_SIGMA = 1e-9          # 이보다 작으면 변형률이 발산한다 — 퇴화로 본다


def forming_strain(sigma):
    # type: (float) -> float
    """성형 중 변형률. σ<1 이면 양수(인장), σ>1 이면 음수(압축)."""
    if sigma <= MIN_SIGMA:
        return float("inf")
    return 1.0 / sigma - 1.0


class Metrics(object):
    __slots__ = ("sigma_min", "sigma_max", "max_forming_strain", "wrinkle_faces",
                 "tear_faces", "flip_faces", "area_3d", "area_2d", "checks")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def _tri_area_2d(uv, face):
    a, b, c = uv[face[0]], uv[face[1]], uv[face[2]]
    return abs(0.5 * ((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])))


def evaluate(res, props):
    # type: (object, object) -> Metrics
    """FlattenResult 를 판정으로 옮긴다."""
    wrinkle, tear, flip = [], [], []
    s_min = float("inf")
    s_max = -float("inf")
    worst_strain = -float("inf")

    for t, (s1, s2) in enumerate(res.sigmas):
        s_max = max(s_max, s1)
        s_min = min(s_min, s2)
        if s2 < 0.0:
            flip.append(t)
            continue
        if s1 > 1.0 + WRINKLE_TOL:
            wrinkle.append(t)
        strain = forming_strain(s2)          # 가장 작은 σ 가 가장 큰 인장을 낳는다
        worst_strain = max(worst_strain, strain)
        if props.elong_max is not None and strain > props.elong_max:
            tear.append(t)

    area_3d = sum(ed.area for ed in res.elements)
    area_2d = sum(_tri_area_2d(res.uv, f) for f in res.faces)

    checks = []

    if wrinkle:
        checks.append(("주름", "경고",
                       "성형 중 압축되는 요소 %d개 (전체 %d개). 최대 σ = %.4f — "
                       "판재는 압축을 받으면 주름진다"
                       % (len(wrinkle), len(res.sigmas), s_max)))
    else:
        checks.append(("주름", "통과",
                       "모든 요소가 σ ≤ 1 이다 (최대 %.4f) — 성형이 인장만으로 이루어진다"
                       % s_max))

    if props.elong_max is None:
        checks.append(("찢어짐", "미판정",
                       "elong_max 가 없다. 성형 변형률 최대 %.2f%% 를 잰 것뿐이고 "
                       "한계와 비교하지 않았다" % (worst_strain * 100.0)))
    elif tear:
        checks.append(("찢어짐", "경고",
                       "연신 한계 %.1f%% 를 넘는 요소 %d개. 최대 %.2f%%"
                       % (props.elong_max * 100.0, len(tear), worst_strain * 100.0)))
    else:
        checks.append(("찢어짐", "통과",
                       "최대 성형 변형률 %.2f%% < 한계 %.1f%%"
                       % (worst_strain * 100.0, props.elong_max * 100.0)))

    if flip:
        checks.append(("뒤집힘", "경고",
                       "뒤집힌 요소 %d개 — 이 요소의 변형률은 믿을 수 없다" % len(flip)))
    else:
        checks.append(("뒤집힘", "통과", "뒤집힌 요소 없음"))

    if res.converged:
        checks.append(("수렴", "통과",
                       "%d회에서 수렴 (에너지 %.6g)" % (res.iterations, res.energy_history[-1])))
    else:
        checks.append(("수렴", "경고",
                       "반복 상한 %d 에서 멈췄다 — 반복을 늘려야 한다" % res.iterations))

    return Metrics(sigma_min=s_min, sigma_max=s_max, max_forming_strain=worst_strain,
                   wrinkle_faces=wrinkle, tear_faces=tear, flip_faces=flip,
                   area_3d=area_3d, area_2d=area_2d, checks=checks)
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest unfold/tests/test_metrics.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: 커밋**

```bash
git add unfold/src/metrics.py unfold/tests/test_metrics.py
git commit -m "feat(unfold): 주름·찢어짐 판정 — 미판정을 통과로 치지 않는다"
```

---

## Task 9: 이론해 대조와 두 솔버 경로 — spec 의 핵심 주장을 검사로 세운다

**Files:**
- Create: `unfold/tests/test_theory.py`, `unfold/tools/dump_fixture.py`, `unfold/tests/fixtures/cap_golden.json`

**Interfaces:**
- Consumes: 앞의 전부
- Produces: 없음 (검증 전용 태스크)

이 태스크는 코드를 거의 안 늘린다. 대신 **spec §10 의 주장이 참인지**를 못박는다. 여기가 통과하지 않으면 앞의 모든 것이 "그럴듯해 보이는 틀린 답"일 수 있다.

- [ ] **Step 1: 이론해 테스트를 쓴다**

`unfold/tests/test_theory.py`:

```python
# -*- coding: utf-8 -*-
"""이론해 대조 — 답을 아는 곡면으로만 검사한다 (spec §10.1).

전개 결과는 그럴듯해 보이는 것과 맞는 것을 눈으로 구별할 수 없다. 그래서
닫힌 형식으로 답이 나오는 케이스에만 기댄다.

    평면        항등
    원기둥      전개 가능 → 가로 R·β, 세로 h 의 직사각형
    원뿔        전개 가능 → 바깥 호 길이 l1·β·sin α
    구면 캡     전개 불가 → 외곽 반경이 2R·sin(θ/2) 와 R·θ **사이**
"""

import math

import pytest

import flatten as fl
import material as mt
import meshes
import metrics as mx
import solver as sv
import topology as tp


def run(mesh, iters=80, props=None):
    verts, faces = mesh
    topo = tp.build(len(verts), faces)
    assert topo.ok, " / ".join(topo.problems)
    return fl.run(verts, faces, topo, props or mt.DEFAULT, iters=iters)


def bbox(uv):
    xs = [p[0] for p in uv]
    ys = [p[1] for p in uv]
    return max(xs) - min(xs), max(ys) - min(ys)


def outer_radii(res, loop):
    cx = sum(p[0] for p in res.uv) / len(res.uv)
    cy = sum(p[1] for p in res.uv) / len(res.uv)
    return [math.hypot(res.uv[v][0] - cx, res.uv[v][1] - cy) for v in loop]


def test_cylinder_unrolls_to_a_rectangle_of_the_right_size():
    R, beta, h = 500.0, 0.8, 300.0
    res = run(meshes.cylinder_patch(R=R, beta=beta, h=h, nu=17, nv=9))
    got = sorted(bbox(res.uv))
    want = sorted([R * beta, h])
    assert got == pytest.approx(want, rel=2e-3)


def test_cone_outer_arc_length_matches_the_sector_formula():
    """원뿔 조각을 펴면 부채꼴 띠다. 바깥 호 길이 = l1 · β · sin α."""
    alpha, l0, l1, beta = 0.4, 200.0, 600.0, 0.9
    nu, nv = 17, 9
    res = run(meshes.cone_patch(alpha=alpha, l0=l0, l1=l1, beta=beta, nu=nu, nv=nv))
    outer = [(nv - 1) * nu + i for i in range(nu)]      # 마지막 행 = l1 쪽 모서리
    length = sum(math.dist(res.uv[outer[i]], res.uv[outer[i + 1]])
                 for i in range(nu - 1))
    assert length == pytest.approx(l1 * beta * math.sin(alpha), rel=3e-3)


def test_sphere_cap_lands_between_the_two_closed_form_extremes():
    """spec §10.1 의 핵심 검사.

    등면적 전개 반경 2R·sin(θ/2)  ≤  결과  ≤  등거리 전개 반경 R·θ
    벗어나면 구현이 틀린 것이다.
    """
    R, theta = 500.0, 0.6
    verts, faces = meshes.sphere_cap(R=R, theta=theta, nr=8, nt=24)
    topo = tp.build(len(verts), faces)
    res = fl.run(verts, faces, topo, mt.DEFAULT, iters=120)

    lo = 2.0 * R * math.sin(theta / 2.0)
    hi = R * theta
    assert lo < hi                                   # 검사 자체가 성립하는지
    r_mean = sum(outer_radii(res, topo.boundary_loops[0])) / len(topo.boundary_loops[0])
    assert lo - 1e-6 <= r_mean <= hi + 1e-6, \
        "외곽 반경 %.4f 가 [%.4f, %.4f] 밖이다" % (r_mean, lo, hi)


def test_sphere_cap_result_is_axisymmetric():
    R, theta = 500.0, 0.6
    verts, faces = meshes.sphere_cap(R=R, theta=theta, nr=8, nt=24)
    topo = tp.build(len(verts), faces)
    res = fl.run(verts, faces, topo, mt.DEFAULT, iters=120)
    radii = outer_radii(res, topo.boundary_loops[0])
    spread = (max(radii) - min(radii)) / (sum(radii) / len(radii))
    assert spread < 5e-3, "축대칭이 깨졌다 — 상대 폭 %.4f" % spread


def test_equal_area_bracket_is_arithmetically_right():
    """검산: 구면 캡 면적 2πR²(1−cosθ) = 원판 면적 π(2R sin(θ/2))²"""
    R, theta = 500.0, 0.6
    cap = 2.0 * math.pi * R * R * (1.0 - math.cos(theta))
    disk = math.pi * (2.0 * R * math.sin(theta / 2.0)) ** 2
    assert cap == pytest.approx(disk)


def test_refining_the_mesh_makes_the_answer_converge():
    """세분화 수렴 — 이산화가 답을 좌우하면 어떤 수치도 못 믿는다."""
    R, theta = 500.0, 0.6

    def outer(nr, nt):
        verts, faces = meshes.sphere_cap(R=R, theta=theta, nr=nr, nt=nt)
        topo = tp.build(len(verts), faces)
        res = fl.run(verts, faces, topo, mt.DEFAULT, iters=120)
        rr = outer_radii(res, topo.boundary_loops[0])
        return sum(rr) / len(rr)

    a, b, c = outer(4, 12), outer(8, 24), outer(16, 48)
    assert abs(c - b) < abs(b - a)


def test_pure_and_numpy_paths_give_the_same_flattening():
    """spec §10.3 — 두 경로가 같은 골든 픽스처를 통과해야 한다."""
    if not sv.HAS_NUMPY:
        pytest.skip("이 환경에 numpy 가 없다")
    mesh = meshes.sphere_cap(R=400.0, theta=0.5, nr=5, nt=14)
    before = sv.FORCE_PURE
    try:
        sv.FORCE_PURE = True
        pure = run(mesh, iters=60)
        sv.FORCE_PURE = False
        fast = run(mesh, iters=60)
    finally:
        sv.FORCE_PURE = before
    assert [x for p in pure.uv for x in p] == pytest.approx(
        [x for p in fast.uv for x in p], abs=1e-6)


def test_dome_wrinkle_warning_is_not_a_false_positive_on_a_cylinder():
    """경고가 아무 데서나 뜨면 아무도 안 본다."""
    cyl = mx.evaluate(run(meshes.cylinder_patch(nu=13, nv=7)), mt.DEFAULT)
    dome = mx.evaluate(run(meshes.sphere_cap(R=400.0, theta=0.7, nr=6, nt=16)), mt.DEFAULT)
    assert cyl.wrinkle_faces == []
    assert dome.wrinkle_faces
```

- [ ] **Step 2: 테스트를 돌린다**

Run: `python -m pytest unfold/tests/test_theory.py -q`
Expected: PASS (8 passed)

**하나라도 실패하면 허용치를 늘리지 말고 원인을 찾는다.** 특히 구면 캡 구간 검사가 실패하면 조립·부호·국소 좌표계 중 하나가 틀린 것이다. 이 검사는 "예뻐 보인다"와 무관하게 참/거짓이 갈리도록 만든 것이므로, 느슨하게 만들면 존재 이유가 사라진다.

- [ ] **Step 3: 골든 픽스처를 만드는 도구를 쓴다**

`unfold/tools/dump_fixture.py`:

```python
#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""회귀 픽스처를 만든다 — 지금 나오는 수치를 파일로 굳힌다.

    python unfold/tools/dump_fixture.py

**숫자를 눈으로 확인하고 커밋해야 한다.** 자동 생성된 값을 보지 않고 굳히면
그때의 버그까지 정본이 된다.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "src")))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "tests")))

import flatten as fl          # noqa: E402
import material as mt         # noqa: E402
import meshes                 # noqa: E402
import metrics as mx          # noqa: E402
import topology as tp         # noqa: E402

R, THETA, NR, NT, ITERS = 500.0, 0.6, 8, 24, 120
OUT = os.path.normpath(os.path.join(HERE, "..", "tests", "fixtures", "cap_golden.json"))


def main():
    verts, faces = meshes.sphere_cap(R=R, theta=THETA, nr=NR, nt=NT)
    topo = tp.build(len(verts), faces)
    res = fl.run(verts, faces, topo, mt.DEFAULT, iters=ITERS)
    m = mx.evaluate(res, mt.DEFAULT)
    cx = sum(p[0] for p in res.uv) / len(res.uv)
    cy = sum(p[1] for p in res.uv) / len(res.uv)
    radii = [math.hypot(res.uv[v][0] - cx, res.uv[v][1] - cy)
             for v in topo.boundary_loops[0]]
    data = {
        "case": {"R": R, "theta": THETA, "nr": NR, "nt": NT, "iters": ITERS},
        "bracket": {"equal_area": 2.0 * R * math.sin(THETA / 2.0), "isometric": R * THETA},
        "outer_radius_mean": sum(radii) / len(radii),
        "sigma_min": m.sigma_min,
        "sigma_max": m.sigma_max,
        "max_forming_strain": m.max_forming_strain,
        "area_3d": m.area_3d,
        "area_2d": m.area_2d,
        "wrinkle_face_count": len(m.wrinkle_faces),
        "iterations": res.iterations,
        "converged": res.converged,
    }
    if not os.path.isdir(os.path.dirname(OUT)):
        os.makedirs(os.path.dirname(OUT))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 픽스처를 만들고 숫자를 눈으로 검증한다**

Run: `python unfold/tools/dump_fixture.py`

출력을 보고 **손으로 확인한다**:

1. `outer_radius_mean` 이 `bracket.equal_area`(≈ 295.5) 와 `bracket.isometric`(300.0) 사이에 있는가
2. `sigma_max` 가 1 보다 큰가 (돔이므로 원주방향이 늘어나야 한다)
3. `area_2d / area_3d` 가 1 근처인가 (ARAP 은 등면적에 가깝게 나온다)
4. `converged` 가 true 인가

넷 중 하나라도 어긋나면 **픽스처를 커밋하지 말고** 원인을 찾는다.

- [ ] **Step 5: 픽스처 대조 테스트를 추가한다**

`unfold/tests/test_theory.py` 끝에 추가:

```python
def test_golden_fixture_still_matches():
    """회귀 방어 — 리팩터링이 수치를 조용히 바꾸면 여기서 걸린다."""
    import json
    import os

    path = os.path.join(os.path.dirname(__file__), "fixtures", "cap_golden.json")
    with open(path, encoding="utf-8") as f:
        want = json.load(f)

    c = want["case"]
    verts, faces = meshes.sphere_cap(R=c["R"], theta=c["theta"], nr=c["nr"], nt=c["nt"])
    topo = tp.build(len(verts), faces)
    res = fl.run(verts, faces, topo, mt.DEFAULT, iters=c["iters"])
    m = mx.evaluate(res, mt.DEFAULT)
    radii = outer_radii(res, topo.boundary_loops[0])

    assert sum(radii) / len(radii) == pytest.approx(want["outer_radius_mean"], rel=1e-6)
    assert m.sigma_min == pytest.approx(want["sigma_min"], rel=1e-6)
    assert m.sigma_max == pytest.approx(want["sigma_max"], rel=1e-6)
    assert m.area_2d == pytest.approx(want["area_2d"], rel=1e-6)
    assert len(m.wrinkle_faces) == want["wrinkle_face_count"]
```

- [ ] **Step 6: 전체 테스트를 돌린다**

Run: `python -m pytest unfold/tests -q`
Expected: PASS (전부)

- [ ] **Step 7: 커밋**

```bash
git add unfold/tests/test_theory.py unfold/tools/dump_fixture.py unfold/tests/fixtures/cap_golden.json
git commit -m "test(unfold): 이론해 대조 — 구면 캡이 두 극단 사이에 있는가"
```

---

## Task 10: `blank.py` — 경계 추출 → 단순화 → 바깥 오프셋

**Files:**
- Create: `unfold/src/blank.py`, `unfold/tests/test_blank.py`

**Interfaces:**
- Consumes: `flatten.FlattenResult.uv`, `topology.Topology.boundary_loops`
- Produces:
  - `blank.boundary_polyline(uv, topo) -> list[(x, y)]` — 항상 반시계
  - `blank.feature_indices(poly, feature_deg=30.0) -> list[int]`
  - `blank.simplify(poly, features, tol) -> list[(x, y)]`
  - `blank.offset(poly, dist) -> list[(x, y)]`
  - `blank.self_intersections(poly) -> list[(i, j)]`
  - `blank.point_in_polygon(pt, poly) -> bool`
  - `blank.distance_to_polygon(pt, poly) -> float`
  - `blank.build(uv, topo, allow_mm, fit_tol=1.0, feature_deg=30.0) -> BlankResult`
  - `BlankResult` 속성: `.curve:list`, `.source:list`, `.features:list[int]`, `.clearance_min:float`, `.intersections:list`, `.notes:list[str]`

**보증의 구조** — spec §8 은 "적합 오차를 바깥으로만 허용"이라 썼다. 구현은 같은
보증을 더 단순하게 얻는다: **단순화 오차를 오프셋 거리에 더한다.**

```
단순화가 안쪽으로 최대 fit_tol 파고들 수 있다  →  오프셋을 allow + fit_tol 로 준다
                                              →  최종 곡선은 원 폴리라인 바깥으로 ≥ allow
```

증명이 한 줄이고, 테스트가 그 한 줄을 그대로 잰다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`unfold/tests/test_blank.py`:

```python
# -*- coding: utf-8 -*-
"""blank.py 테스트 — 과소재단 보증이 실제로 성립하는가.

**이 파일이 spec §3 의 유일한 주장을 지킨다.** 재단선이 평탄화 경계를 한 군데라도
침범하면 그 자리가 곧 과소재단이다.
"""

import math

import pytest

import blank as bk
import flatten as fl
import material as mt
import meshes
import topology as tp


SQUARE = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
CW_SQUARE = list(reversed(SQUARE))


def poly_area(poly):
    s = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        s += x0 * y1 - x1 * y0
    return 0.5 * s


def test_boundary_polyline_is_counterclockwise_whatever_the_input_order():
    verts, faces = meshes.plane_grid()
    topo = tp.build(len(verts), faces)
    uv = [(x, y) for (x, y, _z) in verts]
    assert poly_area(bk.boundary_polyline(uv, topo)) > 0
    mirrored = [(x, -y) for (x, y) in uv]
    assert poly_area(bk.boundary_polyline(mirrored, topo)) > 0


def test_offset_of_a_square_grows_by_exactly_the_distance():
    out = bk.offset(SQUARE, 10.0)
    assert len(out) == 4
    assert poly_area(out) == pytest.approx(120.0 * 120.0)


def test_offset_normalizes_clockwise_input():
    """방향을 안 맞추면 오프셋이 안쪽으로 간다 — 과소재단이 조용히 만들어진다."""
    assert poly_area(bk.offset(CW_SQUARE, 10.0)) == pytest.approx(120.0 * 120.0)


def test_every_source_point_ends_up_inside_with_the_promised_clearance():
    """보증 그 자체. 한 점이라도 밖에 있거나 여유가 모자라면 실패다."""
    verts, faces = meshes.sphere_cap(R=500.0, theta=0.6, nr=6, nt=20)
    topo = tp.build(len(verts), faces)
    res = fl.run(verts, faces, topo, mt.DEFAULT, iters=80)
    allow = 15.0
    b = bk.build(res.uv, topo, allow_mm=allow, fit_tol=1.0)
    for pt in b.source:
        assert bk.point_in_polygon(pt, b.curve), "원 경계점 %r 이 재단선 밖에 있다" % (pt,)
    assert b.clearance_min >= allow - 1e-6


def test_feature_points_survive_simplification():
    """평활화가 코너를 뭉개면 재단물이 원래 패널이 아니게 된다."""
    dense = []
    for i in range(21):
        dense.append((100.0 * i / 20.0, 0.0))
    for i in range(1, 21):
        dense.append((100.0, 100.0 * i / 20.0))
    feats = bk.feature_indices(dense, feature_deg=30.0)
    simple = bk.simplify(dense, feats, tol=1.0)
    assert (100.0, 0.0) in simple, "직각 코너가 사라졌다"


def test_simplify_removes_points_from_a_straight_run():
    straight = [(float(i), 0.0) for i in range(11)] + [(10.0, 5.0), (0.0, 5.0)]
    feats = bk.feature_indices(straight, feature_deg=30.0)
    simple = bk.simplify(straight, feats, tol=0.5)
    assert len(simple) < len(straight)


def test_self_intersection_is_detected_not_silently_accepted():
    """오목 모서리에서 오프셋이 겹칠 수 있다. v1 은 고치지 않고 **알린다**."""
    bowtie = [(0.0, 0.0), (100.0, 100.0), (100.0, 0.0), (0.0, 100.0)]
    assert bk.self_intersections(bowtie)
    assert bk.self_intersections(SQUARE) == []


def test_build_notes_say_what_was_done():
    verts, faces = meshes.plane_grid()
    topo = tp.build(len(verts), faces)
    uv = [(x, y) for (x, y, _z) in verts]
    b = bk.build(uv, topo, allow_mm=12.0, fit_tol=1.0)
    text = " ".join(b.notes)
    assert "12" in text and ("여유" in text or "오프셋" in text)


def test_clearance_is_measured_against_the_worst_point_not_the_average():
    verts, faces = meshes.plane_grid()
    topo = tp.build(len(verts), faces)
    uv = [(x, y) for (x, y, _z) in verts]
    b = bk.build(uv, topo, allow_mm=20.0, fit_tol=0.0)
    worst = min(bk.distance_to_polygon(p, b.curve) for p in b.source)
    assert b.clearance_min == pytest.approx(worst, abs=1e-9)
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest unfold/tests/test_blank.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'blank'`

- [ ] **Step 3: `blank.py` 를 구현한다**

```python
# -*- coding: utf-8 -*-
"""평면 메쉬의 경계를 재단선으로 다듬는다.

    ① 추출   경계 루프 → 폴리라인 (항상 반시계) + 특징점 표시
    ② 단순화 특징점 사이만 Douglas-Peucker, 허용치 fit_tol
    ③ 오프셋 바깥으로 (allow_mm + fit_tol) → 자기교차 검사

**보증**: 단순화가 안쪽으로 최대 fit_tol 파고들 수 있으므로 오프셋을 그만큼 더
준다. 그러면 최종 곡선은 원 폴리라인 바깥으로 항상 allow_mm 이상 떨어져 있다.
재료를 조금 더 쓰는 대신 과소재단이 구조적으로 불가능해진다.

**알려진 한계**: 오목 모서리에서 오프셋이 자기교차할 수 있다. v1 은 고치지 않고
검출해서 알린다(spec §8.1). 외장 패널은 대개 볼록 사각형이라 드물다.
"""

import math

FEATURE_DEG = 30.0        # 꺾임각이 이보다 크면 코너로 본다
MITER_MIN = 0.2           # 뾰족한 모서리에서 오프셋이 폭발하는 것을 막는다
EPS = 1e-12


def _signed_area(poly):
    s = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        s += x0 * y1 - x1 * y0
    return 0.5 * s


def boundary_polyline(uv, topo):
    # type: (list, object) -> list
    """경계 루프를 평면 좌표 폴리라인으로. 반시계로 맞춘다."""
    loop = topo.boundary_loops[0]
    poly = [uv[v] for v in loop]
    if _signed_area(poly) < 0.0:
        poly.reverse()
    return poly


def feature_indices(poly, feature_deg=FEATURE_DEG):
    # type: (list, float) -> list
    """꺾임각이 임계를 넘는 정점. 여기는 단순화가 건드리지 않는다."""
    n = len(poly)
    limit = math.radians(feature_deg)
    out = []
    for i in range(n):
        p, q, r = poly[i - 1], poly[i], poly[(i + 1) % n]
        ax, ay = q[0] - p[0], q[1] - p[1]
        bx, by = r[0] - q[0], r[1] - q[1]
        la = math.hypot(ax, ay)
        lb = math.hypot(bx, by)
        if la < EPS or lb < EPS:
            continue
        cross = ax * by - ay * bx
        dot = ax * bx + ay * by
        if abs(math.atan2(cross, dot)) > limit:
            out.append(i)
    return out


def _dp(points, tol):
    """열린 구간 하나에 대한 Douglas-Peucker."""
    if len(points) < 3:
        return list(points)
    x0, y0 = points[0]
    x1, y1 = points[-1]
    dx, dy = x1 - x0, y1 - y0
    seg = math.hypot(dx, dy)
    worst, wi = -1.0, 0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        if seg < EPS:
            d = math.hypot(px - x0, py - y0)
        else:
            d = abs(dy * px - dx * py + x1 * y0 - y1 * x0) / seg
        if d > worst:
            worst, wi = d, i
    if worst <= tol:
        return [points[0], points[-1]]
    left = _dp(points[:wi + 1], tol)
    right = _dp(points[wi:], tol)
    return left[:-1] + right


def simplify(poly, features, tol):
    # type: (list, list, float) -> list
    """특징점을 고정한 채 그 사이 구간만 단순화한다."""
    n = len(poly)
    if tol <= 0.0 or n < 4:
        return list(poly)
    anchors = sorted(set(features)) or [0]
    out = []
    for a in range(len(anchors)):
        i = anchors[a]
        j = anchors[(a + 1) % len(anchors)]
        span = [poly[(i + k) % n] for k in range(((j - i) % n) + 1)]
        kept = _dp(span, tol)
        out.extend(kept[:-1])          # 끝점은 다음 구간의 시작점이다
    return out


def offset(poly, dist):
    # type: (list, float) -> list
    """반시계 폴리곤을 바깥으로 dist 만큼 민다 (마이터)."""
    pts = list(poly)
    if _signed_area(pts) < 0.0:
        pts.reverse()
    n = len(pts)
    normals = []
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy)
        if ln < EPS:
            normals.append((0.0, 0.0))
        else:
            normals.append((dy / ln, -dx / ln))   # 반시계에서 바깥 법선
    out = []
    for i in range(n):
        nx0, ny0 = normals[i - 1]
        nx1, ny1 = normals[i]
        bx, by = nx0 + nx1, ny0 + ny1
        bl = math.hypot(bx, by)
        if bl < EPS:
            bx, by, bl = nx1, ny1, 1.0
        bx, by = bx / bl, by / bl
        denom = bx * nx1 + by * ny1
        if denom < MITER_MIN:
            denom = MITER_MIN
        out.append((pts[i][0] + bx * dist / denom, pts[i][1] + by * dist / denom))
    return out


def _seg_cross(a, b, c, d):
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2 = side(a, b, c), side(a, b, d)
    d3, d4 = side(c, d, a), side(c, d, b)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def self_intersections(poly):
    # type: (list) -> list
    """서로 인접하지 않은 변끼리 교차하는 쌍."""
    n = len(poly)
    hits = []
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            if _seg_cross(poly[i], poly[(i + 1) % n], poly[j], poly[(j + 1) % n]):
                hits.append((i, j))
    return hits


def point_in_polygon(pt, poly):
    # type: (tuple, list) -> bool
    """광선 투사. 경계 위의 점은 안쪽으로 친다."""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            t = (y - y0) / (y1 - y0)
            if x < x0 + t * (x1 - x0):
                inside = not inside
    return inside


def distance_to_polygon(pt, poly):
    # type: (tuple, list) -> float
    """폴리곤 변까지의 최단거리 (부호 없음)."""
    x, y = pt
    best = float("inf")
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        ln2 = dx * dx + dy * dy
        if ln2 < EPS:
            best = min(best, math.hypot(x - x0, y - y0))
            continue
        t = ((x - x0) * dx + (y - y0) * dy) / ln2
        t = max(0.0, min(1.0, t))
        best = min(best, math.hypot(x - (x0 + t * dx), y - (y0 + t * dy)))
    return best


class BlankResult(object):
    __slots__ = ("curve", "source", "features", "clearance_min", "intersections", "notes")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def build(uv, topo, allow_mm, fit_tol=1.0, feature_deg=FEATURE_DEG):
    # type: (list, object, float, float, float) -> BlankResult
    """재단 외곽을 만든다."""
    notes = []
    src = boundary_polyline(uv, topo)
    feats = feature_indices(src, feature_deg)
    simple = simplify(src, feats, fit_tol)
    dist = allow_mm + fit_tol
    curve = offset(simple, dist)

    notes.append("경계 %d점 → 단순화 %d점 (허용 %.2f mm, 코너 %d개 고정)"
                 % (len(src), len(simple), fit_tol, len(feats)))
    notes.append("여유 %.2f mm + 단순화 허용 %.2f mm = 오프셋 %.2f mm"
                 % (allow_mm, fit_tol, dist))

    hits = self_intersections(curve)
    if hits:
        notes.append("재단선이 %d군데에서 자기교차한다 — 오목 모서리다. "
                     "v1 은 고치지 않으니 손으로 확인해야 한다" % len(hits))

    outside = [p for p in src if not point_in_polygon(p, curve)]
    if outside:
        notes.append("경계점 %d개가 재단선 **밖에** 있다 — 과소재단이다. "
                     "여유를 키우거나 자기교차를 먼저 해결해야 한다" % len(outside))
        clearance = 0.0
    else:
        clearance = min(distance_to_polygon(p, curve) for p in src)
        notes.append("최소 여유 실측 %.3f mm" % clearance)

    return BlankResult(curve=curve, source=src, features=feats,
                       clearance_min=clearance, intersections=hits, notes=notes)
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python -m pytest unfold/tests/test_blank.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: 커밋**

```bash
git add unfold/src/blank.py unfold/tests/test_blank.py
git commit -m "feat(unfold): 재단 외곽 — 단순화 오차를 오프셋에 더해 과소재단을 구조적으로 막는다"
```

---

## Task 11: `report.py` + `pipeline.py` — 공개 진입점

**Files:**
- Create: `unfold/src/report.py`, `unfold/src/pipeline.py`, `unfold/tests/test_pipeline.py`

**Interfaces:**
- Consumes: 앞의 전부
- Produces:
  - `report.summarize(res, m, bl, props) -> (info:str, warn:list[str])`
  - `pipeline.run(verts, faces, props=None, allow_mm=15.0, fit_tol=1.0, iters=30, max_verts=5000) -> Outcome`
  - `Outcome` 속성: `.ok:bool`, `.uv:list`, `.faces:list`, `.curve:list`, `.sigmas:list`, `.warn:list[str]`, `.info:str`, `.metrics`, `.flatten`, `.blank`
  - `pipeline.DEFAULT_ALLOW_MM = 15.0`, `pipeline.DEFAULT_MAX_VERTS = 5000`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`unfold/tests/test_pipeline.py`:

```python
# -*- coding: utf-8 -*-
"""pipeline.py 테스트 — 실패가 조용하지 않은가.

**어댑터(GH)는 이 결과를 그대로 화면에 옮긴다.** 그러니 실패든 성공이든 여기서
말이 완성되어 있어야 한다. 어댑터가 판단을 하기 시작하면 판단이 두 곳에 생긴다.
"""

import material as mt
import meshes
import pipeline as pl


def test_plane_runs_end_to_end():
    verts, faces = meshes.plane_grid()
    out = pl.run(verts, faces, allow_mm=10.0)
    assert out.ok
    assert len(out.curve) >= 4
    assert out.info


def test_warn_lists_passing_checks_too():
    """빈 경고 목록이 '검사 안 함'과 구별되어야 한다."""
    verts, faces = meshes.plane_grid()
    out = pl.run(verts, faces)
    joined = " ".join(out.warn)
    assert "통과" in joined
    assert "미판정" in joined            # elong_max 가 없으므로


def test_bad_topology_stops_before_the_solver():
    """나쁜 메쉬를 통과시키면 솔버가 그럴듯한 틀린 답을 낸다."""
    out = pl.run([(0.0, 0.0, 0.0)] * 4, [(0, 1, 2), (0, 2, 1)])   # 닫힌 껍질
    assert not out.ok
    assert out.curve == []
    assert any("위상" in w for w in out.warn)
    assert any("경계가 없" in w for w in out.warn)


def test_vertex_cap_refuses_instead_of_freezing_rhino():
    verts, faces = meshes.sphere_cap(nr=8, nt=24)
    out = pl.run(verts, faces, max_verts=10)
    assert not out.ok
    joined = " ".join(out.warn)
    assert "10" in joined and ("요소 크기" in joined or "정점" in joined)


def test_bad_material_is_reported_not_swallowed():
    out = pl.run(*meshes.plane_grid(), props=mt.MaterialProps(wrinkle_penalty=0.2))
    assert not out.ok
    assert any("wrinkle_penalty" in w for w in out.warn)


def test_info_carries_the_numbers_a_person_needs():
    verts, faces = meshes.sphere_cap(R=500.0, theta=0.5, nr=5, nt=14)
    out = pl.run(verts, faces, allow_mm=12.0)
    assert out.ok
    for token in ("σ", "반복", "면적", "여유"):
        assert token in out.info, "info 에 %r 가 없다:\n%s" % (token, out.info)


def test_info_says_which_material_fields_did_nothing():
    props = mt.MaterialProps(name="AL", thickness=3.0, source="테스트")
    out = pl.run(*meshes.plane_grid(), props=props)
    assert "형상에는 영향 없음" in out.info


def test_degenerate_triangle_is_reported_not_raised():
    """예외가 GH 캔버스까지 올라가면 사용자는 빨간 상자만 본다."""
    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    out = pl.run(verts, [(0, 1, 2), (0, 2, 3)])
    assert not out.ok
    assert any("퇴화" in w or "면적" in w for w in out.warn)
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python -m pytest unfold/tests/test_pipeline.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline'`

- [ ] **Step 3: `report.py` 를 구현한다**

```python
# -*- coding: utf-8 -*-
"""사람이 읽는 요약. 숫자와 그 숫자의 뜻을 같이 적는다."""


def summarize(res, m, bl, props):
    # type: (object, object, object, object) -> tuple
    """(info 문자열, warn 목록) 을 만든다.

    **통과한 판정도 warn 에 넣는다.** 빈 목록이 "검사했고 괜찮다"인지
    "검사를 안 했다"인지 구별되지 않으면 판정이 쓸모가 없다.
    """
    warn = ["[%s] %s: %s" % (status, name, detail) for name, status, detail in m.checks]

    ratio = (m.area_2d / m.area_3d) if m.area_3d else float("nan")
    lines = [
        "반복 %d회, %s (에너지 %.6g)"
        % (res.iterations, "수렴" if res.converged else "**미수렴**",
           res.energy_history[-1]),
        "초기 배치: %s" % res.method,
        "σ 범위 %.4f ~ %.4f   (σ>1 은 성형에서 압축 = 주름 위험)"
        % (m.sigma_min, m.sigma_max),
        "최대 성형 변형률 %.2f%%" % (m.max_forming_strain * 100.0),
        "면적 3D %.1f mm² → 평면 %.1f mm² (비 %.4f)" % (m.area_3d, m.area_2d, ratio),
    ]
    if bl is not None:
        lines.append("재단선 %d점, 최소 여유 %.3f mm" % (len(bl.curve), bl.clearance_min))
        lines.extend("  " + n for n in bl.notes)
    lines.extend("  " + n for n in res.notes)
    lines.append(props.describe())
    return "\n".join(lines), warn
```

- [ ] **Step 4: `pipeline.py` 를 구현한다**

```python
# -*- coding: utf-8 -*-
"""공개 진입점 — 위상 검사부터 재단선까지 한 번에.

**판단은 전부 여기 아래에서 끝난다.** GH 어댑터는 이 결과를 화면에 옮기기만
한다. 어댑터가 판단을 시작하면 같은 판단이 두 곳에 생기고, 둘이 어긋나는 날
화면과 숫자가 다른 말을 하게 된다(J-006 TRAP-03 과 같은 종류의 사고다).
"""

import blank as bk
import element as el
import flatten as fl
import material as mt
import metrics as mx
import report as rp
import topology as tp

DEFAULT_ALLOW_MM = 15.0
DEFAULT_FIT_TOL = 1.0
DEFAULT_ITERS = 30
DEFAULT_MAX_VERTS = 5000


class Outcome(object):
    __slots__ = ("ok", "uv", "faces", "curve", "sigmas", "warn", "info",
                 "metrics", "flatten", "blank")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def _fail(warn):
    return Outcome(ok=False, uv=[], faces=[], curve=[], sigmas=[], warn=warn,
                   info="\n".join(warn), metrics=None, flatten=None, blank=None)


def run(verts, faces, props=None, allow_mm=DEFAULT_ALLOW_MM, fit_tol=DEFAULT_FIT_TOL,
        iters=DEFAULT_ITERS, max_verts=DEFAULT_MAX_VERTS):
    # type: (list, list, object, float, float, int, int) -> Outcome
    """전개 한 판."""
    props = props or mt.DEFAULT
    if not props.ok:
        return _fail(["[경고] 물성: " + p for p in props.problems])

    if len(verts) > max_verts:
        return _fail(["[경고] 정점이 %d개로 상한 %d개를 넘었다 — 요소 크기(edge_mm)를 키워야 한다. "
                      "그대로 돌리면 Rhino 가 오래 얼어붙는다" % (len(verts), max_verts)])

    topo = tp.build(len(verts), faces)
    if not topo.ok:
        return _fail(["[경고] 위상: " + p for p in topo.problems])

    try:
        res = fl.run(verts, faces, topo, props, iters=iters)
    except el.DegenerateTriangle as ex:
        return _fail(["[경고] 메쉬: %s — 요소 크기를 바꾸거나 곡면을 정리해야 한다" % ex])

    m = mx.evaluate(res, props)
    bl = bk.build(res.uv, topo, allow_mm=allow_mm, fit_tol=fit_tol)
    info, warn = rp.summarize(res, m, bl, props)
    for note in props.notes:
        warn.append("[참고] 물성: " + note)

    return Outcome(ok=True, uv=res.uv, faces=faces, curve=bl.curve, sigmas=res.sigmas,
                   warn=warn, info=info, metrics=m, flatten=res, blank=bl)
```

- [ ] **Step 5: 테스트가 통과하는지 확인한다**

Run: `python -m pytest unfold/tests -q`
Expected: PASS (전부)

- [ ] **Step 6: 커밋**

```bash
git add unfold/src/report.py unfold/src/pipeline.py unfold/tests/test_pipeline.py
git commit -m "feat(unfold): 공개 진입점 — 판단은 전부 코어에서 끝낸다"
```

---

## Task 12: `rhino_io.py` — Brep ↔ 메쉬, 결과 → Curve/Mesh

**Files:**
- Create: `unfold/src/rhino_io.py`, `unfold/tests/rhino/check_rhino_io.py`, `unfold/tools/run_rhino_check.py`

**Interfaces:**
- Consumes: `pipeline.Outcome`
- Produces:
  - `rhino_io.mesh_from_brep(brep, edge_mm) -> (verts, faces, notes)` — `verts` 는 `(x,y,z)` 튜플 리스트
  - `rhino_io.to_mesh(uv, faces) -> Rhino.Geometry.Mesh` (z=0 평면)
  - `rhino_io.to_strain_mesh(uv, faces, sigmas) -> Mesh` — 정점 색으로 σ 를 칠한다
  - `rhino_io.to_curve(poly) -> Rhino.Geometry.PolylineCurve` (닫힘)

**이 파일만 Rhino 를 import 한다.** 그래서 pytest 로 못 돈다 — `adaptive_mold` 와 같은 방식으로 브리지를 거쳐 Rhino 안에서 돌리고 로그 파일로 결과를 받는다.

선결 조건: Rhino 8 이 떠 있고 명령창에 `mcpstart` (포트 1999).

- [ ] **Step 1: `rhino_io.py` 를 구현한다**

```python
# -*- coding: utf-8 -*-
"""Rhino 경계면 — **이 파일만 Rhino 를 import 한다.**

코어가 Rhino 를 모르게 유지하는 대가로, Rhino 쪽 함정은 전부 여기 모인다.

  · Mesh.CreateFromBrep 은 None 이나 빈 배열을 돌려줄 수 있다 → 반드시 검사
  · 트림된 Brep 은 조각으로 나오므로 Append 로 합치고 CombineIdentical 로 꿰맨다
  · 사각형 면이 섞여 나오므로 ConvertQuadsToTriangles 를 반드시 부른다
    (코어는 삼각형만 받는다)
"""

import math

import Rhino.Geometry as rg
import System.Drawing as sd

MIN_EDGE_RATIO = 0.25     # 최소 변 길이 = edge_mm × 이것
WELD_DEG = 180.0          # 정점 병합 각도


def mesh_from_brep(brep, edge_mm):
    # type: (object, float) -> tuple
    """Brep 을 삼각망으로. (verts, faces, notes) 를 돌려준다."""
    notes = []
    if brep is None:
        return [], [], ["Brep 이 None 이다"]

    mp = rg.MeshingParameters(0.0)
    mp.MaximumEdgeLength = float(edge_mm)
    mp.MinimumEdgeLength = float(edge_mm) * MIN_EDGE_RATIO
    mp.SimplePlanes = False
    mp.JaggedSeams = False

    pieces = rg.Mesh.CreateFromBrep(brep, mp)
    if pieces is None or len(pieces) == 0:
        return [], [], ["Mesh.CreateFromBrep 이 아무것도 못 만들었다 — "
                        "곡면이 유효한지, edge_mm 이 너무 크지 않은지 확인해야 한다"]

    mesh = rg.Mesh()
    for piece in pieces:
        if piece is not None:
            mesh.Append(piece)
    if len(pieces) > 1:
        notes.append("Brep 이 면 %d개로 나뉘어 메쉬화됐다 — 합쳐서 꿰맸다" % len(pieces))

    mesh.Vertices.CombineIdentical(True, True)
    mesh.Weld(math.radians(WELD_DEG))
    quads = mesh.Faces.QuadCount
    if quads:
        mesh.Faces.ConvertQuadsToTriangles()
        notes.append("사각형 면 %d개를 삼각형으로 쪼갰다" % quads)
    mesh.Faces.CullDegenerateFaces()
    mesh.Compact()

    verts = [(v.X, v.Y, v.Z) for v in mesh.Vertices.ToPoint3dArray()]
    faces = []
    for f in mesh.Faces:
        faces.append((f.A, f.B, f.C))
    notes.append("메쉬 정점 %d개, 삼각형 %d개 (목표 변 길이 %.1f mm)"
                 % (len(verts), len(faces), edge_mm))
    return verts, faces, notes


def to_mesh(uv, faces):
    # type: (list, list) -> object
    """평면 결과를 z=0 메쉬로."""
    mesh = rg.Mesh()
    for (x, y) in uv:
        mesh.Vertices.Add(float(x), float(y), 0.0)
    for (a, b, c) in faces:
        mesh.Faces.AddFace(a, b, c)
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return mesh


def _sigma_color(s):
    """σ<1 (성형에서 인장) 은 파랑, 1 은 흰색, σ>1 (주름 위험) 은 빨강."""
    t = max(-1.0, min(1.0, (s - 1.0) * 5.0))     # ±20% 를 만색으로
    if t >= 0.0:
        return sd.Color.FromArgb(255, int(255 - 200 * t), int(255 - 200 * t))
    u = -t
    return sd.Color.FromArgb(int(255 - 200 * u), int(255 - 200 * u), 255)


def to_strain_mesh(uv, faces, sigmas):
    # type: (list, list, list) -> object
    """요소별 σ 를 정점으로 평균 내 색칠한다."""
    mesh = to_mesh(uv, faces)
    acc = [0.0] * len(uv)
    cnt = [0] * len(uv)
    for t, (s1, _s2) in enumerate(sigmas):
        for v in faces[t]:
            acc[v] += s1
            cnt[v] += 1
    mesh.VertexColors.Clear()
    for i in range(len(uv)):
        mesh.VertexColors.Add(_sigma_color(acc[i] / cnt[i] if cnt[i] else 1.0))
    return mesh


def to_curve(poly):
    # type: (list) -> object
    """평면 폴리라인을 닫힌 곡선으로."""
    if not poly:
        return None
    pts = [rg.Point3d(float(x), float(y), 0.0) for (x, y) in poly]
    pts.append(pts[0])
    return rg.PolylineCurve(pts)
```

- [ ] **Step 2: Rhino 안에서 돌 검사 스크립트를 쓴다**

`unfold/tests/rhino/check_rhino_io.py` — **pytest 가 수집하지 않도록 `test_` 로 시작하지 않는다.**

```python
#! python 3
# -*- coding: utf-8 -*-
"""rhino_io.py 검사 — Rhino 안에서 돈다.

    python unfold/tools/run_rhino_check.py

결과는 `_rhino_io_log.txt` 에 쓴다. Rhino 콘솔 출력은 밖에서 보이지 않는다.
로그를 **먼저 지우므로** 파일이 없으면 "통과"가 아니라 "실행되지 않았다"다.
"""

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "src")))

for _name in [n for n in list(sys.modules) if getattr(sys.modules.get(n), "__file__", None)
              and os.path.normcase(os.path.normpath(sys.modules[n].__file__)).startswith(
                  os.path.normcase(os.path.normpath(os.path.join(HERE, "..", "..", "src"))))]:
    del sys.modules[_name]

import Rhino.Geometry as rg          # noqa: E402

import material as mt                # noqa: E402
import pipeline as pl                # noqa: E402
import rhino_io as rio               # noqa: E402

LOG = os.path.join(HERE, "_rhino_io_log.txt")
lines = []
fails = [0]


def check(name, cond, detail=""):
    lines.append("%s %s %s" % ("OK  " if cond else "FAIL", name, detail))
    if not cond:
        fails[0] += 1


try:
    # 반지름 2000, 60도 구면 조각을 Brep 으로 만든다 (복곡면 + 트림 경계)
    sphere = rg.Sphere(rg.Point3d(0, 0, 0), 2000.0)
    srf = sphere.ToNurbsSurface()
    face = rg.Brep.CreateFromSurface(srf)
    box = rg.Box(rg.Plane.WorldXY, rg.Interval(-600, 600), rg.Interval(-600, 600),
                 rg.Interval(1000, 2500))
    trimmed = rg.Brep.CreateBooleanIntersection([face], [box.ToBrep()], 0.01)
    brep = trimmed[0] if trimmed else face

    verts, faces, notes = rio.mesh_from_brep(brep, 60.0)
    lines.extend("    " + n for n in notes)
    check("메쉬화", len(verts) > 50 and len(faces) > 50,
          "정점 %d 면 %d" % (len(verts), len(faces)))
    check("삼각형만", all(len(f) == 3 for f in faces))

    out = pl.run(verts, faces, mt.MaterialProps(name="검사용", elong_max=0.12,
                                                source="검사 스크립트"),
                 allow_mm=15.0, max_verts=20000)
    lines.append("    ok=%s" % out.ok)
    lines.extend("    " + w for w in out.warn)
    check("파이프라인", out.ok)

    if out.ok:
        m = rio.to_mesh(out.uv, out.faces)
        check("평면 메쉬", m is not None and m.Vertices.Count == len(out.uv))
        sm = rio.to_strain_mesh(out.uv, out.faces, out.sigmas)
        check("변형률 색칠", sm is not None and sm.VertexColors.Count == len(out.uv))
        crv = rio.to_curve(out.curve)
        check("재단 곡선", crv is not None and crv.IsClosed)

        amp = rg.AreaMassProperties.Compute(crv)
        check("재단 면적 > 평면 메쉬 면적",
              amp is not None and amp.Area > out.metrics.area_2d,
              "재단 %.1f vs 평면 %.1f" % (amp.Area if amp else -1, out.metrics.area_2d))
        check("최소 여유가 요구치 이상", out.blank.clearance_min >= 15.0 - 1e-6,
              "%.3f mm" % out.blank.clearance_min)
except Exception:
    lines.append("EXCEPTION")
    lines.append(traceback.format_exc())
    fails[0] += 1

lines.append("실패 %d건" % fails[0])
with open(LOG, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
```

- [ ] **Step 3: 브리지 실행 도구를 쓴다**

`unfold/tools/run_rhino_check.py`:

```python
#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""unfold 의 Rhino 검사 스크립트를 밖에서 돌린다.

`adaptive_mold/tools/run_tests_via_bridge.py` 와 같은 경로다:
    이 스크립트(CPython 3, 밖) → 브리지 1999(IronPython 2.7, Rhino 안)
      → _-RunPythonScript → shebang 대로 CPython 3 로 실행 → 로그 파일

선결 조건: Rhino 8 + 명령창에 `mcpstart`.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "adaptive_mold", "tools"))

from rhino_cli import Rhino  # noqa: E402

SCRIPT = os.path.normpath(os.path.join(HERE, "..", "tests", "rhino", "check_rhino_io.py"))
LOG = os.path.join(os.path.dirname(SCRIPT), "_rhino_io_log.txt")

# 브리지는 IronPython 2.7 이다. 여기서 도는 것은 이 조각뿐이고, 실제 검사는
# shebang(`#! python 3`) 대로 CPython 3 에서 돈다.
# `run_tests_via_bridge.py` 의 BRIDGE_CODE 와 같은 방식이다.
BRIDGE_CODE = r'''
import Rhino, io, traceback
lines = []
try:
    ok = Rhino.RhinoApp.RunScript('_-RunPythonScript "{script}"', True)
    lines.append("RunScript=%s" % ok)
except Exception:
    lines.append(traceback.format_exc())
f = io.open(r"{out}", "w", encoding="utf-8")
try:
    f.write(u"\n".join([unicode(x) for x in lines]))
finally:
    f.close()
'''


def main():
    out_path = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                            "uf_check_result.txt")
    for p in (LOG, out_path):
        if os.path.exists(p):
            os.remove(p)        # 먼저 지운다 — 없으면 "실행되지 않았다"로 읽는다

    code = BRIDGE_CODE.format(script=SCRIPT.replace("\\", "\\\\"), out=out_path)
    r = Rhino()
    try:
        r.py(code)
    finally:
        r.close()

    if not os.path.exists(LOG):
        print("로그가 없다 — 스크립트가 실행되지 않았다. "
              "Rhino 가 떠 있고 mcpstart 를 했는가?")
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as f:
                print(f.read())
        return 1
    with open(LOG, encoding="utf-8") as f:
        text = f.read()
    print(text)
    return 0 if "실패 0건" in text else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Rhino 를 띄우고 검사를 돌린다**

Rhino 8 을 열고 명령창에 `mcpstart` 를 친 뒤:

Run: `python unfold/tools/run_rhino_check.py`
Expected: 마지막 줄이 `실패 0건`

실패가 있으면 로그의 해당 줄을 보고 고친다. **로그가 아예 없으면 통과가 아니라 미실행이다.**

- [ ] **Step 5: 커밋**

```bash
git add unfold/src/rhino_io.py unfold/tests/rhino/check_rhino_io.py unfold/tools/run_rhino_check.py
git commit -m "feat(unfold): Rhino 경계면 — Brep 메쉬화와 결과 지오메트리"
```

---

## Task 13: GH 컴포넌트 `UFv1 Material` / `UFv1 Flatten`

**Files:**
- Create: `unfold/gh_scripts/UFv1_Material.py`, `unfold/gh_scripts/UFv1_Flatten.py`, `unfold/tools/build_uf_components.py`, `unfold/gh_scripts/param_docs.py`
- Test: Rhino 캔버스에서 수동 검증 (아래 절차)

**Interfaces:**
- Consumes: `pipeline.run`, `rhino_io.*`, `material.MaterialProps`
- Produces: GH 캔버스의 컴포넌트 둘

**먼저 `gh-component-dev` 스킬을 읽는다** (`~/.claude/skills/gh-component-dev/SKILL.md`). 파라미터 정렬·코드 push·툴팁 재적용 절차와 함정 여섯이 거기 있다.

- [ ] **Step 1: 캔버스에 컴포넌트 둘을 만든다**

Rhino/Grasshopper 에서 Python 3 스크립트 컴포넌트 두 개를 놓고 **NickName** 을 정확히 다음으로 바꾼다:

```
UFv1 Material
UFv1 Flatten
```

빌더는 NickName 으로 컴포넌트를 찾는다. 이름이 한 글자만 달라도 "못 찾음"이 된다.

- [ ] **Step 2: 어댑터 스크립트를 쓴다**

`unfold/gh_scripts/UFv1_Material.py`:

```python
# -*- coding: utf-8 -*-
# UFv1 Material — 물성을 한 덩어리로 묶어 내보낸다
#
# Flatten 의 입력을 물성 수만큼 늘리는 대신 객체 하나를 물린다.
# AMv1 을 Base/Check/Play 로 쪼갠 것과 같은 이유다.
#
# **프리셋은 없다.** 알루미늄 균일연신률을 출처와 함께 댈 수 없기 때문이다.
# 근거 없는 기본값을 넣으면 아무도 안 고치고 그대로 쓴다.
#
# Inputs:
#   platform_path  str    repo root (필수)
#   name           str    재료 이름
#   thickness      float  두께 mm — **형상에는 영향 없음** (막 모델)
#   elong_max      float  균일연신률 **비율**. 12% 는 0.12
#   wrinkle_penalty float σ>1 쪽 벌점. 1.0 이 순수 ARAP(증명된 경로)
#   source         str    이 숫자들이 어디서 왔는가
#
# Outputs:
#   props  object  UFv1 Flatten 에 물린다
#   info   str     무엇이 형상을 바꿨고 무엇이 기록인지

import os
import sys

props = None
info = ""

root = str(platform_path or "").strip().strip('"').strip("'")
if not root or not os.path.isdir(root):
    info = "platform_path 가 필요하다 (repo root 폴더)"
else:
    src = os.path.join(root, "unfold", "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    for _n in [n for n in list(sys.modules)
               if getattr(sys.modules.get(n), "__file__", None)
               and os.path.normcase(os.path.normpath(sys.modules[n].__file__)).startswith(
                   os.path.normcase(os.path.normpath(src)))]:
        del sys.modules[_n]

    import material as mt

    props = mt.MaterialProps(
        name=str(name or ""),
        thickness=float(thickness) if thickness is not None else None,
        elong_max=float(elong_max) if elong_max is not None else None,
        wrinkle_penalty=float(wrinkle_penalty) if wrinkle_penalty is not None else 1.0,
        source=str(source or ""))
    parts = [props.describe()]
    for p in props.problems:
        parts.append("[경고] " + p)
    for n in props.notes:
        parts.append("[참고] " + n)
    info = "\n".join(parts)
    if not props.ok:
        props = None          # 잘못된 물성을 하류로 흘려보내지 않는다
```

`unfold/gh_scripts/UFv1_Flatten.py`:

```python
# -*- coding: utf-8 -*-
# UFv1 Flatten — 복곡면 한 장을 성형 전 블랭크로 편다
#
# **판단은 여기서 하지 않는다.** pipeline.run() 이 끝낸 결과를 화면에 옮기기만
# 한다. 어댑터가 판단을 시작하면 같은 판단이 두 곳에 생기고, 둘이 어긋나는 날
# 화면과 숫자가 다른 말을 하게 된다.
#
# **run 토글이 있는 이유**: GH 스크립트 컴포넌트는 Rhino UI 스레드에서 돈다.
# 5초 걸리는 계산은 5초 동안 Rhino 를 얼린다. 슬라이더를 만질 때마다 도는 것을
# 막아야 한다.
#
# Inputs:
#   platform_path str    repo root (필수)
#   srf           Brep   전개할 곡면 한 장
#   props         object UFv1 Material 출력. 없으면 기본 물성 + 경고
#   edge_mm       float  목표 요소 크기 (기본 40)
#   allow_mm      float  트림 여유 (기본 15)
#   iters         int    최대 반복 (기본 30)
#   max_verts     int    정점 상한 (기본 5000). 넘으면 계산하지 않는다
#   run           bool   계산 스위치
#
# Outputs:
#   flat   Mesh    평면 메쉬
#   blank  Curve   재단 외곽 (여유 포함)
#   strain Mesh    σ 색칠
#   warn   str*    경고·판정. 통과한 것도 적는다
#   info   str     요약

import os
import sys

flat = None
blank = None
strain = None
warn = []
info = ""

root = str(platform_path or "").strip().strip('"').strip("'")
if not root or not os.path.isdir(root):
    warn = ["platform_path 가 필요하다 (repo root 폴더)"]
elif not run:
    warn = ["run 이 꺼져 있다 — 계산하지 않았다. **미판정이지 통과가 아니다**"]
elif srf is None:
    warn = ["srf 가 비어 있다"]
else:
    src = os.path.join(root, "unfold", "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    for _n in [n for n in list(sys.modules)
               if getattr(sys.modules.get(n), "__file__", None)
               and os.path.normcase(os.path.normpath(sys.modules[n].__file__)).startswith(
                   os.path.normcase(os.path.normpath(src)))]:
        del sys.modules[_n]

    import material as mt
    import pipeline as pl
    import rhino_io as rio

    use = props if props is not None else mt.DEFAULT
    if props is None:
        warn.append("[참고] props 가 없어 기본 물성으로 돌았다 — "
                    "찢어짐 판정은 미판정이다")

    verts, faces, notes = rio.mesh_from_brep(srf, float(edge_mm or 40.0))
    if not faces:
        warn.extend("[경고] " + n for n in notes)
        info = "\n".join(notes)
    else:
        out = pl.run(verts, faces, use,
                     allow_mm=float(allow_mm if allow_mm is not None else 15.0),
                     iters=int(iters or 30),
                     max_verts=int(max_verts or 5000))
        warn.extend(out.warn)
        info = "\n".join(notes) + "\n" + out.info
        if out.ok:
            flat = rio.to_mesh(out.uv, out.faces)
            strain = rio.to_strain_mesh(out.uv, out.faces, out.sigmas)
            blank = rio.to_curve(out.curve)
```

- [ ] **Step 3: 빌더를 만든다**

`adaptive_mold/tools/build_gh_components.py` 를 `unfold/tools/build_uf_components.py` 로 복사하고 다음만 바꾼다:

1. `SCRIPTS` 를 `os.path.join(REPO_ROOT, "unfold", "gh_scripts")` 로
2. `sys.path` 에 넣는 `rhino_cli` 경로를 `adaptive_mold/tools` 로 (복사본이 상위 폴더를 기준으로 잡으므로 확인 필요)
3. `SPECS` 를 아래로 교체

입력 형식은 원본과 같은 **`(nick, 힌트클래스명, is_list, 위젯스펙)` 4튜플**이다. 힌트는 GH 의 힌트 클래스 이름을 문자열로 준다(`GH_StringHint_CS`, `GH_DoubleHint_CS`, `GH_IntegerHint_CS`, `GH_BooleanHint_CS`, `GH_BrepHint` 등). 위젯 스펙은 `None`, `("path",)`, `("slider", 최소, 최대, 초기값, 소수자리)`, `("toggle", 초기값)` 중 하나다.

```python
MATERIAL_INPUTS = [
    ("platform_path",   "GH_StringHint_CS", False, ("path",)),
    ("name",            "GH_StringHint_CS", False, None),
    ("thickness",       "GH_DoubleHint_CS", False, ("slider", 0.5, 10.0, 3.0, 1)),
    ("elong_max",       "GH_DoubleHint_CS", False, ("slider", 0.0, 0.5, 0.0, 3)),
    ("wrinkle_penalty", "GH_DoubleHint_CS", False, ("slider", 1.0, 10.0, 1.0, 1)),
    ("source",          "GH_StringHint_CS", False, None),
]

FLATTEN_INPUTS = [
    ("platform_path", "GH_StringHint_CS",  False, ("path",)),
    ("srf",           "GH_BrepHint",       False, None),
    # props 는 파이썬 객체다 — 힌트를 주지 않아야 그대로 통과한다.
    ("props",         None,                False, None),
    ("edge_mm",       "GH_DoubleHint_CS",  False, ("slider", 10, 200, 40, 0)),
    ("allow_mm",      "GH_DoubleHint_CS",  False, ("slider", 0, 100, 15, 0)),
    ("iters",         "GH_IntegerHint_CS", False, ("slider", 5, 200, 30, 0)),
    ("max_verts",     "GH_IntegerHint_CS", False, ("slider", 500, 20000, 5000, 0)),
    ("run",           "GH_BooleanHint_CS", False, ("toggle", False)),
]

SPECS = {
    # 순서가 중요하다 — Material 을 먼저 만들어야 Flatten 이 그 출력에 물린다.
    "Material": {
        "nick": "UFv1 Material",
        "code": os.path.join(SCRIPTS, "UFv1_Material.py"),
        "inputs": MATERIAL_INPUTS,
        "outputs": ["props", "info"],
        "reorder": True,
        "anchor": None,
        "wiring": [],
        "share": [],
    },
    "Flatten": {
        "nick": "UFv1 Flatten",
        "code": os.path.join(SCRIPTS, "UFv1_Flatten.py"),
        "inputs": FLATTEN_INPUTS,
        "outputs": ["flat", "blank", "strain", "warn", "info"],
        "reorder": True,
        "anchor": "UFv1 Material",
        "wiring": [
            ("props", "UFv1 Material", "props"),
        ],
        "share": [
            ("platform_path", "UFv1 Material", "platform_path"),
        ],
    },
}
```

> `anchor` / `wiring` / `share` 키가 원본에서 어떻게 쓰이는지 확인하고 맞춘다.
> `anchor` 는 배치 기준 컴포넌트, `wiring` 은 `(내 입력, 상대 컴포넌트 NickName, 상대 출력)`,
> `share` 는 다른 컴포넌트에 이미 물려 있는 소스를 그대로 물려받는 것이다.
> `UFv1 Material` 에는 앞선 컴포넌트가 없으므로 셋 다 비운다.

**함정 (스킬에 실측으로 기록됨)**: 토글 값이 전파되지 않으면 위젯에 `ExpireSolution(True)` 를 불러야 한다. 컴포넌트에만 부르는 것으로는 부족하다.

- [ ] **Step 4: 컴포넌트를 맞추고 코드를 밀어 넣는다**

Run: `python unfold/tools/build_uf_components.py`
Expected: 두 컴포넌트의 입출력이 맞춰지고 코드가 들어간다. 출력에 `hint FAIL` 이 있으면 그 파라미터의 형 힌트를 손으로 확인한다.

- [ ] **Step 5: 캔버스에서 실제 곡면으로 확인한다**

1. Rhino 에서 복곡면 패널 한 장을 만들거나 `adaptive_mold/grasshopper/test_panels.3dm` 의 곡면을 쓴다
2. `UFv1 Material` 에 이름·두께·연신률·출처를 넣는다
3. `UFv1 Flatten` 의 `srf` 에 곡면을, `props` 에 위 출력을 물린다
4. `run` 토글을 켠다
5. 확인:
   - `blank` 곡선이 나온다
   - `flat` 메쉬가 `blank` 안에 완전히 들어간다
   - `warn` 에 통과 항목과 경고가 **둘 다** 보인다
   - `info` 의 "형상에는 영향 없음"이 두께에 대해 찍혀 있다
   - 돔 형태면 주름 경고가 뜬다

- [ ] **Step 6: 툴팁을 적용하고 저장 후 재확인한다**

`adaptive_mold/gh_components/param_docs.py` 와 `tools/apply_param_docs.py` 의 방식을 그대로 따라 `unfold/gh_scripts/param_docs.py` 를 만들고 적용한다.

**`.gh` 는 파라미터 설명을 보존하지 못한다** — 저장·재시작 시 125개 중 120개 소실이 실측되어 있다. 그래서:

1. 툴팁 적용
2. `.gh` 저장
3. **Rhino 재시작**
4. 툴팁이 남아 있는지 확인 → 사라졌으면 `apply_param_docs` 를 다시 돌리는 것이 정상 절차다

- [ ] **Step 7: 커밋**

```bash
git add unfold/gh_scripts unfold/tools/build_uf_components.py
git commit -m "feat(unfold): GH 컴포넌트 UFv1 Material / UFv1 Flatten"
```

---

## Task 14: 개발저널

**Files:**
- Create: `docs/journal/J-014-unfold-blank-v1.md`

- [ ] **Step 1: 저널을 쓴다**

`docs/journal/TEMPLATE.md` 형식(TRAP / DECISION / FACT / PROCEDURE)을 따른다. 반드시 담을 것:

- **DECISION** — 기각한 대안과 **뒤집을 조건**: ExactFlat 상용 API, 스트립 분할, LSCM 초기값, v1 소성 FEM, 이방성
- **FACT** — 실측: Rhino 8 py39 에 numpy 없음 / 시스템 파이썬에는 있음. 구현 후 실제 소요 시간(spec §6.5 의 추정을 실측으로 갱신)
- **TRAP** — 설계 중 부호가 두 번 뒤집힌 일. 증상(결과가 그럴듯해 보임) → 원인(σ 의 방향) → 해결(spec §3.1 부호표) → 재발 조건(변수명을 "압축"으로 부르는 순간)
- **PROCEDURE** — 이론해 4케이스로 검증하는 절차

- [ ] **Step 2: spec 의 추정치를 실측으로 갱신한다**

`docs/superpowers/specs/2026-08-14-unfold-blank-development-design.md` §6.5 의 표를 실제 측정값으로 바꾸고 `[추정]` 을 `[실측]` 으로 고친다. 측정하지 않았으면 **고치지 말고 그대로 둔다.**

- [ ] **Step 3: 커밋**

```bash
git add docs/journal/J-014-unfold-blank-v1.md docs/superpowers/specs/2026-08-14-unfold-blank-development-design.md
git commit -m "docs(unfold): 저널 J-014 + spec 추정치를 실측으로 갱신"
```

---

## 완료 정의 (spec §12)

- [ ] 이론해 4케이스 통과 — 구면 캡이 두 극단 사이 (Task 9)
- [ ] 불변량 6종 통과 (Task 7, 9)
- [ ] numpy 경로와 순수 경로가 같은 픽스처 통과 (Task 4, 9)
- [ ] Rhino 에서 실제 패널로 `blank` 가 나오고, 재단선이 평탄화 경계를 침범하지 않으며, 주름·연신 판정이 `warn` 에 찍힌다 (Task 12, 13)
- [ ] 툴팁이 `.gh` 저장·재시작 후에도 살아 있다 (Task 13)
- [ ] `docs/journal` 에 저널 한 편 — 기각한 대안과 재발 조건 포함 (Task 14)

