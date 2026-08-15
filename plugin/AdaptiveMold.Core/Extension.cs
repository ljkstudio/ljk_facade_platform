using System;
using Rhino.Geometry;
using Rhino.Geometry.Intersect;

namespace AdaptiveMold.Core
{
    /// <summary>
    /// Phase C — positioned 곡면을 몰드 전체로 확장한다. <c>extension.py</c> 1:1 포팅.
    /// </summary>
    public static class Extension
    {
        public const string MethodSurface = "surface_extend";
        public const string MethodTangent = "tangent_fallback";

        public const string BranchNoSurface = "no_surface";
        public const string BranchSurfaceExtend = "surface_extend";
        public const string BranchTangentFallback = "tangent_fallback";

        public static (Brep extended, string method, string branch) Run(
            GeometryBase positionedSrf, double width, double length)
        {
            var srf = Validation.ToSurface(positionedSrf);
            if (srf == null)
                return (Validation.ToBrep(positionedSrf), MethodTangent, BranchNoSurface);

            double extensionLength = Math.Max(width, length) * 1.5;

            try
            {
                var extended = srf;
                extended = TryExtend(extended, IsoStatus.South, extensionLength);
                extended = TryExtend(extended, IsoStatus.North, extensionLength);
                extended = TryExtend(extended, IsoStatus.West, extensionLength);
                extended = TryExtend(extended, IsoStatus.East, extensionLength);

                // 파이썬은 `extended is not srf` — **참조 동등성**이다.
                // == 나 Equals 로 바꾸면 의미가 달라진다.
                if (extended != null && !ReferenceEquals(extended, srf))
                {
                    var b = extended.ToBrep();
                    if (b != null) return (b, MethodSurface, BranchSurfaceExtend);
                }
            }
            catch (Exception)
            {
                // 파이썬이 통째로 삼킨다. 그대로 옮긴다.
            }

            return (Validation.ToBrep(positionedSrf), MethodTangent, BranchTangentFallback);
        }

        static Surface TryExtend(Surface surface, IsoStatus iso, double length)
        {
            if (surface == null) return null;
            try
            {
                var result = surface.Extend(iso, length, true);
                if (result != null) return result;
            }
            catch (Exception) { }
            return surface;
        }

        /// <summary>
        /// 곡면 밖 점의 높이를 접평면 외삽으로 구한다.
        ///
        /// <c>Brep.ClosestPoint(Point3d)</c> 는 C# 에서 **구조체**를 돌려주므로
        /// 파이썬의 <c>cp is None</c> 가지가 여기서는 사라진다. 없어지는 가지를
        /// 적어 둔다 — 나중에 "왜 가지 수가 다르지"가 된다.
        /// </summary>
        public static double? TangentExtrapolate(Point3d gridPt, GeometryBase positionedSrf, Plane basePlane)
        {
            var brep = Validation.ToBrep(positionedSrf);
            if (brep == null) return null;

            var closestPt = brep.ClosestPoint(gridPt);

            var srfNormal = SurfaceNormalAt(positionedSrf, closestPt) ?? basePlane.ZAxis;
            var tangentPlane = new Plane(closestPt, srfNormal);

            var normal = basePlane.ZAxis;
            var line = new Line(gridPt, gridPt + normal * 10000.0);

            if (Intersection.LinePlane(line, tangentPlane, out double t))
            {
                var hitPt = line.PointAt(t);
                var vec = hitPt - gridPt;
                return Math.Abs(vec * normal);
            }

            return null;
        }

        static Vector3d? SurfaceNormalAt(GeometryBase geo, Point3d point)
        {
            var srf = Validation.ToSurface(geo);
            if (srf == null) return null;
            if (srf.ClosestPoint(point, out double u, out double v))
            {
                var n = srf.NormalAt(u, v);
                if (n.IsValid) return n;
            }
            return null;
        }
    }
}
