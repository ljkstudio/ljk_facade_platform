"""Phase A: 베이스 그리드 생성 모듈.

width/length/spacing으로 nx×ny 직교 그리드를 생성합니다.
인덱싱 규약: idx = j * nx + i (row-major, j=Y방향, i=X방향)
"""

import Rhino.Geometry as rg
import math


def compute_grid_counts(width, length, spacing):
    # type: (float, float, float) -> tuple[int, int]
    """width/length/spacing으로 그리드 개수를 계산합니다.

    Args:
        width: mold 가로(X) 크기 (mm).
        length: mold 세로(Y) 크기 (mm).
        spacing: 액추에이터 간격 (mm).

    Returns:
        (nx, ny) 튜플.

    Raises:
        ValueError: spacing이 0 이하이거나 width/length가 0 이하인 경우.
    """
    if spacing <= 0:
        raise ValueError("spacing은 0보다 커야 합니다. 현재: {}".format(spacing))
    if width <= 0 or length <= 0:
        raise ValueError("width와 length는 0보다 커야 합니다.")

    nx = int(math.floor(width / spacing)) + 1
    ny = int(math.floor(length / spacing)) + 1

    if nx < 2:
        nx = 2
    if ny < 2:
        ny = 2

    return (nx, ny)


def build_grid(base_plane, width, length, spacing):
    # type: (rg.Plane, float, float, float) -> tuple[list[rg.Point3d], int, int]
    """Base Plane 좌표계에서 nx×ny 직교 그리드를 생성합니다.

    그리드 원점은 base_plane.Origin이며, +X(width), +Y(length) 방향으로 배치됩니다.

    Args:
        base_plane: 몰드 베이스 평면.
        width: mold 가로(X) 크기 (mm).
        length: mold 세로(Y) 크기 (mm).
        spacing: 액추에이터 간격 (mm).

    Returns:
        (grid_pts, nx, ny) 튜플.
        grid_pts: Point3d 리스트 (nx * ny 개, row-major: idx = j * nx + i).
        nx: X 방향 개수.
        ny: Y 방향 개수.

    Raises:
        ValueError: 유효하지 않은 입력값.
    """
    nx, ny = compute_grid_counts(width, length, spacing)

    grid_pts = []
    for j in range(ny):
        for i in range(nx):
            local_x = i * spacing
            local_y = j * spacing
            world_pt = base_plane.PointAt(local_x, local_y, 0)
            grid_pts.append(world_pt)

    return (grid_pts, nx, ny)


def get_grid_indices(index, nx):
    # type: (int, int) -> tuple[int, int]
    """1D 인덱스를 (i, j) 2D 인덱스로 변환합니다.

    Args:
        index: 1D 인덱스 (row-major).
        nx: X 방향 개수.

    Returns:
        (i, j) 튜플. i=X인덱스, j=Y인덱스.
    """
    j = index // nx
    i = index % nx
    return (i, j)


def get_flat_index(i, j, nx):
    # type: (int, int, int) -> int
    """2D 인덱스를 1D 인덱스로 변환합니다."""
    return j * nx + i


def get_grid_center(base_plane, width, length):
    # type: (rg.Plane, float, float) -> rg.Point3d
    """그리드 중심점을 World 좌표로 반환합니다."""
    return base_plane.PointAt(width / 2.0, length / 2.0, 0)
