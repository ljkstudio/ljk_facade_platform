using System;
using System.Text.Json;
using Rhino.Geometry;

namespace AdaptiveMold.Tests
{
    /// <summary>
    /// <c>adaptive_mold/tools/dump_fixtures.py</c> 의 <c>_make_*</c> / <c>build_surface</c> /
    /// <c>build_plane</c> 을 1:1 로 옮긴 것.
    ///
    /// 픽스처의 <c>input.surface</c> 는 직렬화된 지오메트리가 아니라 **생성 스펙**이다
    /// (<c>{"kind":"hemisphere","radius":400.0,...}</c>). 따라서 C# 쪽이 같은 곡면을
    /// 다시 만들어야 하는데, **여기서 조금이라도 달라지면 T1~T9 대조 전체가
    /// 무의미해진다** — Core 가 옳아도 깨지고, 우연히 상쇄되면 틀린 채로 통과한다.
    ///
    /// 그래서 <c>Grid</c> 포팅보다 이것이 먼저이고, <c>FingerprintTests</c> 가 지킨다.
    /// 고칠 일이 생기면 파이썬 쪽과 **같이** 고치고 지문을 다시 뽑을 것.
    /// </summary>
    public static class TestSurfaceBuilder
    {
        public static Brep BuildSurface(JsonElement spec)
        {
            var kind = spec.GetProperty("kind").GetString();
            switch (kind)
            {
                case "flat":
                    return MakeFlat(
                        spec.GetProperty("z_height").GetDouble(),
                        spec.GetProperty("size").GetDouble());
                case "tilted":
                    return MakeTilted(
                        spec.GetProperty("tilt_degrees").GetDouble(),
                        spec.GetProperty("z_base").GetDouble(),
                        spec.GetProperty("size").GetDouble());
                case "hemisphere":
                    return MakeHemisphere(
                        spec.GetProperty("radius").GetDouble(),
                        spec.GetProperty("center_z").GetDouble());
                default:
                    throw new ArgumentException("unknown surface kind: " + kind);
            }
        }

        /// <summary>base_plane spec. null 은 "WorldXY 를 쓴다"는 뜻이므로 null 을 돌려준다.</summary>
        public static Plane? BuildPlane(JsonElement spec)
        {
            if (spec.ValueKind == JsonValueKind.Null) return null;

            var kind = spec.GetProperty("kind").GetString();
            if (kind == "rotated") return MakeRotatedPlane();

            throw new ArgumentException("unknown plane kind: " + kind);
        }

        // _make_flat_surface
        static Brep MakeFlat(double zHeight, double size)
        {
            var plane = new Plane(new Point3d(0, 0, zHeight), Vector3d.ZAxis);
            var interval = new Interval(-size / 2.0, size / 2.0);
            return new PlaneSurface(plane, interval, interval).ToBrep();
        }

        // _make_tilted_surface
        static Brep MakeTilted(double tiltDegrees, double zBase, double size)
        {
            double angle = tiltDegrees * Math.PI / 180.0;
            var normal = new Vector3d(Math.Sin(angle), 0, Math.Cos(angle));
            var origin = new Point3d(size / 2.0, size / 2.0, zBase);
            var plane = new Plane(origin, normal);
            var interval = new Interval(-size / 2.0, size / 2.0);
            return new PlaneSurface(plane, interval, interval).ToBrep();
        }

        // _make_hemisphere — 이름과 달리 온전한 구를 만든다. 파이썬이 그렇다.
        static Brep MakeHemisphere(double radius, double centerZ)
        {
            var center = new Point3d(500, 500, centerZ);
            return new Sphere(center, radius).ToBrep();
        }

        // _make_rotated_plane
        static Plane MakeRotatedPlane()
        {
            var origin = new Point3d(500, 300, 100);
            var xAxis = new Vector3d(1, 1, 0);
            xAxis.Unitize();
            var yAxis = Vector3d.CrossProduct(Vector3d.ZAxis, xAxis);
            yAxis.Unitize();
            return new Plane(origin, xAxis, yAxis);
        }
    }
}
