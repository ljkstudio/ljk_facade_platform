using System;
using Rhino.Geometry;

namespace AdaptiveMold.Tests
{
    public class Fingerprint
    {
        public double[] BBoxMin;
        public double[] BBoxMax;
        public double Area;
        public int FaceCount;
        public int DegreeU;
        public int DegreeV;
        public int CvU;
        public int CvV;
    }

    /// <summary>
    /// 파이썬 <c>dump_fixtures.geometry_fingerprint</c> 와 같은 규칙으로 지문을 만든다.
    ///
    /// 값 자체에 의미는 없다. 양쪽이 같기만 하면 된다.
    /// 6자리 반올림도 같게 맞춘다 — 최하위 비트 차이로 지문이 어긋나면
    /// 정작 보려던 것(스펙 해석이 다른가)을 못 본다.
    /// </summary>
    public static class GeometryFingerprint
    {
        public static Fingerprint Compute(GeometryBase geo)
        {
            var brep = geo as Brep;
            if (brep == null && geo is Surface srf) brep = srf.ToBrep();
            if (brep == null)
                throw new ArgumentException("Brep 으로 만들 수 없다", nameof(geo));

            var bb = brep.GetBoundingBox(true);
            var amp = AreaMassProperties.Compute(brep);
            var ns = brep.Faces[0].UnderlyingSurface().ToNurbsSurface();

            return new Fingerprint
            {
                BBoxMin = R3(bb.Min),
                BBoxMax = R3(bb.Max),
                Area = amp != null ? Math.Round(amp.Area, 6) : 0.0,
                FaceCount = brep.Faces.Count,
                DegreeU = ns.Degree(0),
                DegreeV = ns.Degree(1),
                CvU = ns.Points.CountU,
                CvV = ns.Points.CountV,
            };
        }

        static double[] R3(Point3d p) => new[]
        {
            Math.Round(p.X, 6), Math.Round(p.Y, 6), Math.Round(p.Z, 6)
        };
    }
}
