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
    anchors = sorted(set(features))
    if len(anchors) < 2:
        # 매끄러운 경계(원판 등)는 코너가 없다. 고정점이 하나뿐이면 구간이
        # 자기 자신으로 닫혀 결과가 **빈 리스트**가 된다 — 재단선이 사라진다.
        # 그래서 반대편에 하나를 더 세워 닫힌 고리를 두 구간으로 자른다.
        start = anchors[0] if anchors else 0
        anchors = sorted({start, (start + n // 2) % n})
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
