# -*- coding: utf-8 -*-
"""로봇 팔이 몰드에 파고드는지 값싸게 걸러낸다.

**검사가 아니라 스크리닝이다.** 표본으로 보므로 "걸리면 확실히 문제"이고
"안 걸리면 아마 괜찮다"이다. 이 구분을 흐리면 안 된다 — 통과를 안전 증명으로
쓰면 실물에서 팔이 몰드를 친다.

──────────────────────────────────────────────────────────
왜 이 방법인가
──────────────────────────────────────────────────────────

전면 메시-메시 검사는 못 쓴다: 포즈 1,175개 × 파트 9개 × 12만 면.

그런데 **이 몰드는 높이장(heightfield)이다.** 핀이 아래에서 밀어 올린 면이라
언더컷이 없고, 한 (x, y) 에 높이가 하나다. 그래서 "점이 몰드 안인가"가

    발자국 안에 있고, z 가 그 자리의 몰드 높이보다 낮다

로 끝난다 — 격자 조회 O(1). 로봇 쪽은 표면점을 솎아 쓰면 포즈당 수백 번이다.

**기각한 대안 — 캡슐 근사:** 링크를 선분+반경으로 보는 흔한 방법인데, 이
로봇에는 잘 안 맞는다. link4 는 j4~j5 피벗 선분보다 250 mm 더 튀어나와 있어
선분 기준 반경을 잡으면 반경이 과하게 커지고 거짓 경보가 쏟아진다.
메시 점을 직접 솎는 편이 형상을 그대로 반영한다.

──────────────────────────────────────────────────────────
한계 (반드시 알고 쓸 것)
──────────────────────────────────────────────────────────

- **표본이다.** 가느다란 돌출부는 점 사이로 빠져나갈 수 있다.
- **몰드만 본다.** 자기 자신끼리의 간섭, 몰드 프레임·테이블·주변 설비는 안 본다.
- **높이장 가정.** 언더컷이 있는 형상에는 쓸 수 없다.
- 표시용으로 48% 줄인 메시를 쓰면 그만큼 형상이 안쪽으로 들어와 있다.
  `margin` 으로 상쇄한다.
"""

import Rhino.Geometry as rg

import robot as rb
import robot_body as rbb


# 안전 여유 (mm). 표본·감축 메시·높이장 근사를 한꺼번에 덮는 값이다.
DEFAULT_MARGIN = 30.0

# 파트별 표본 점 개수. 늘리면 정확해지고 느려진다.
DEFAULT_SAMPLES = 80


class Heightfield(object):
    """(x, y) → 높이. 격자 + 이중선형 보간."""

    def __init__(self, x0, y0, dx, dy, nx, ny, z):
        self.x0 = float(x0)
        self.y0 = float(y0)
        self.dx = float(dx)
        self.dy = float(dy)
        self.nx = int(nx)
        self.ny = int(ny)
        self.z = list(z)              # row-major: idx = j*nx + i

    # ── 만들기 ──────────────────────────────────────────

    @classmethod
    def from_grid_points(cls, pts, nx, ny, offset=0.0):
        """정렬된 격자점(핀 상단 등)에서 만든다. 격자 노드에서는 정확하다.

        `offset` 은 위로 올릴 양이다 — 핀 상단에서 성형면까지의 스택 두께
        같은 것. 몰드를 실제보다 높게 보면 판정이 보수적으로 된다.
        """
        if not pts or nx < 2 or ny < 2 or len(pts) < nx * ny:
            return None
        x0, y0 = pts[0].X, pts[0].Y
        dx = pts[1].X - pts[0].X
        dy = pts[nx].Y - pts[0].Y
        if abs(dx) < 1e-9 or abs(dy) < 1e-9:
            return None
        z = [p.Z + offset for p in pts[:nx * ny]]
        return cls(x0, y0, dx, dy, nx, ny, z)

    @classmethod
    def from_surface(cls, srf, nx=40, ny=40, offset=0.0):
        """곡면을 월드 XY 격자로 훑어 만든다. 격자점 위에서 수직으로 내려본다.

        위에서 아주 먼 점의 최근접점을 쓴다 — 완만한 면에서는 수직 투영과 같고,
        곡률이 큰 곳에서 조금 어긋난다. 격자를 촘촘히 하면 줄어든다.
        """
        if srf is None:
            return None
        geo = srf
        if hasattr(geo, "Faces") is False and hasattr(geo, "ToBrep"):
            geo = geo.ToBrep()
        bb = geo.GetBoundingBox(True)
        if not bb.IsValid:
            return None
        span_x = bb.Max.X - bb.Min.X
        span_y = bb.Max.Y - bb.Min.Y
        if span_x <= 0 or span_y <= 0:
            return None
        dx = span_x / (nx - 1)
        dy = span_y / (ny - 1)
        high = bb.Max.Z + max(span_x, span_y) * 10.0

        z = []
        for j in range(ny):
            for i in range(nx):
                q = rg.Point3d(bb.Min.X + i * dx, bb.Min.Y + j * dy, high)
                cp = geo.ClosestPoint(q)
                z.append((cp.Z if cp is not None else bb.Min.Z) + offset)
        return cls(bb.Min.X, bb.Min.Y, dx, dy, nx, ny, z)

    # ── 쓰기 ────────────────────────────────────────────

    def z_at(self, x, y):
        """그 자리의 몰드 높이. 발자국 밖이면 None."""
        fi = (x - self.x0) / self.dx
        fj = (y - self.y0) / self.dy
        if fi < 0.0 or fj < 0.0 or fi > self.nx - 1 or fj > self.ny - 1:
            return None
        i = int(fi)
        j = int(fj)
        if i >= self.nx - 1:
            i = self.nx - 2
        if j >= self.ny - 1:
            j = self.ny - 2
        tx = fi - i
        ty = fj - j
        z = self.z
        n = self.nx
        z00 = z[j * n + i]
        z10 = z[j * n + i + 1]
        z01 = z[(j + 1) * n + i]
        z11 = z[(j + 1) * n + i + 1]
        a = z00 + (z10 - z00) * tx
        b = z01 + (z11 - z01) * tx
        return a + (b - a) * ty

    def penetration(self, pt):
        """점이 몰드 면 아래로 들어간 깊이 (mm). 밖이거나 위면 0 이하."""
        zs = self.z_at(pt.X, pt.Y)
        if zs is None:
            return -1.0e9
        return zs - pt.Z


def sample_points(parts, per_part=DEFAULT_SAMPLES):
    """파트별 표면 표본점 (영각 좌표). 이름 → [Point3d]

    정점을 일정 간격으로 솎는다. 메시 정점은 형상 전체에 퍼져 있으므로
    간격 솎기로도 골고루 뽑힌다. **베이스는 뺀다** — 움직이지 않고, 몰드와의
    겹침은 robot.base_overlap() 이 따로 본다.
    """
    out = {}
    for name, mesh in parts.items():
        if name == "base":
            continue
        verts = mesh.Vertices
        n = verts.Count
        if n == 0:
            continue
        stride = max(1, n // max(1, int(per_part)))
        pts = []
        i = 0
        while i < n:
            v = verts[i]
            pts.append(rg.Point3d(v.X, v.Y, v.Z))
            i += stride
        out[name] = pts
    return out


def check_pose(pose, samples, hf, base_plane=None, margin=DEFAULT_MARGIN):
    """한 포즈의 최대 침투 깊이와 그 파트. `(깊이, 파트이름)`

    깊이 > 0 이면 몰드 면(+margin) 아래로 들어갔다는 뜻이다.
    """
    if hf is None or not samples:
        return -1.0e9, None
    xfs = rbb.part_transforms(pose, base_plane=base_plane)
    worst = -1.0e9
    who = None
    for name, pts in samples.items():
        xf = xfs.get(name)
        if xf is None:
            continue
        for p in pts:
            q = rg.Point3d(p)
            q.Transform(xf)
            pen = hf.penetration(q) + margin
            if pen > worst:
                worst = pen
                who = name
    return worst, who


def scan_poses(poses, samples, hf, base_plane=None,
               margin=DEFAULT_MARGIN, step=1):
    """포즈 전체를 훑는다. `(깊이 목록, 파트 목록)` — step 으로 건너뛸 수 있다.

    건너뛰면 그 사이의 포즈는 보지 않는다. **건너뛴 검사를 통과라고 부르지 말 것.**
    """
    step = max(1, int(step))
    pens = []
    whos = []
    for i in range(0, len(poses), step):
        pen, who = check_pose(poses[i], samples, hf, base_plane, margin)
        pens.append(pen)
        whos.append(who)
    return pens, whos


def summarize(pens, whos, step=1, total=None, margin=DEFAULT_MARGIN):
    """리포트용 요약 dict.

    **`min_clear` 가 이 판정의 핵심 숫자다.** 걸렸다/안 걸렸다는 margin 을
    어떻게 잡았는지에 달린 이진값이지만, 최소 여유는 형상이 정하는 실측값이다.
    위치를 잡을 때 "얼마나 아슬아슬한가"를 이 값으로 읽는다.

        침투 = margin - 실제여유   →   실제여유 = margin - 침투

    실측 예: margin 200 에서 최대 침투 134 mm → 최소 여유 66 mm (link2/link3).
    같은 배치에서 margin 30 이면 걸림 0 이다 — 두 결과가 같은 형상을 말한다.
    """
    hits = [i for i, p in enumerate(pens) if p > 0.0]
    per_part = {}
    for i in hits:
        w = whos[i] or "?"
        per_part[w] = per_part.get(w, 0) + 1

    worst = max(pens) if pens else 0.0
    known = worst > -1.0e8          # 전부 발자국 밖이면 판정 불가
    return {
        "checked": len(pens),
        "total": total if total is not None else len(pens) * step,
        "step": step,
        "hits": len(hits),
        "hit_indices": [i * step for i in hits],
        "worst": worst if known else 0.0,
        "worst_at": (hits[0] * step) if hits else -1,
        "per_part": per_part,
        "min_clear": (margin - worst) if known else None,
        "margin": margin,
    }
