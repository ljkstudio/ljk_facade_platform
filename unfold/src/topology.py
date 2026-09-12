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
