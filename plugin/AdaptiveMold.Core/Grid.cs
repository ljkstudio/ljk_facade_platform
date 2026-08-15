using System;
using System.Collections.Generic;
using Rhino.Geometry;

namespace AdaptiveMold.Core
{
    /// <summary>
    /// Phase A — 베이스 그리드 생성. <c>grid.py</c> 의 1:1 포팅.
    ///
    /// 인덱싱 규약 <c>idx = j * nx + i</c> (row-major, j=Y, i=X).
    /// 그리드 원점은 <c>basePlane.Origin</c> 이며 +X·+Y 로 뻗는다 —
    /// **몰드의 중심이 아니라 모서리다.**
    /// </summary>
    public static class Grid
    {
        public static (int nx, int ny) ComputeCounts(double width, double length, double spacing)
        {
            if (spacing <= 0)
                throw new ArgumentException($"spacing은 0보다 커야 합니다. 현재: {spacing}");
            if (width <= 0 || length <= 0)
                throw new ArgumentException("width와 length는 0보다 커야 합니다.");

            int nx = (int)Math.Floor(width / spacing) + 1;
            int ny = (int)Math.Floor(length / spacing) + 1;

            if (nx < 2) nx = 2;
            if (ny < 2) ny = 2;

            return (nx, ny);
        }

        public static (List<Point3d> pts, int nx, int ny) Build(
            Plane basePlane, double width, double length, double spacing)
        {
            var (nx, ny) = ComputeCounts(width, length, spacing);

            var pts = new List<Point3d>(nx * ny);
            for (int j = 0; j < ny; j++)
                for (int i = 0; i < nx; i++)
                    pts.Add(basePlane.PointAt(i * spacing, j * spacing, 0));

            return (pts, nx, ny);
        }

        public static (int i, int j) Indices(int index, int nx) => (index % nx, index / nx);

        public static int FlatIndex(int i, int j, int nx) => j * nx + i;

        public static Point3d Center(Plane basePlane, double width, double length) =>
            basePlane.PointAt(width / 2.0, length / 2.0, 0);
    }
}
