using Rhino.Geometry;

namespace AdaptiveMold.Core
{
    /// <summary>
    /// <c>utils.py</c> 의 입력 정규화·지오메트리 추출 1:1 포팅.
    ///
    /// **조용히 기본값으로 되돌리는 동작을 그대로 옮긴다.** 파이썬이 그렇게 하고
    /// 성공 기준은 "똑같다"이므로, 여기서 예외를 던지도록 "개선"하면 안 된다.
    ///
    /// 유일한 이탈은 NaN·Infinity 다. 파이썬의 <c>float('nan') &lt;= 0</c> 은
    /// False 라 통과하는데, 그 값이 흘러가면 전 핀이 NaN 이 된다.
    /// </summary>
    public static class Validation
    {
        public static double PositiveOrDefault(double? value, double def)
        {
            if (!value.HasValue) return def;
            double v = value.Value;
            if (double.IsNaN(v) || double.IsInfinity(v)) return def;
            return v <= 0 ? def : v;
        }

        public static double NonNegativeOrDefault(double? value, double def)
        {
            if (!value.HasValue) return def;
            double v = value.Value;
            if (double.IsNaN(v) || double.IsInfinity(v)) return def;
            return v < 0 ? def : v;
        }

        public static Brep ToBrep(GeometryBase geo)
        {
            if (geo == null) return null;
            if (geo is Brep b) return b;
            if (geo is Surface s) return s.ToBrep();
            return null;
        }

        public static Surface ToSurface(GeometryBase geo)
        {
            if (geo == null) return null;
            if (geo is Surface s) return s;
            if (geo is Brep b && b.Faces.Count > 0) return b.Faces[0].UnderlyingSurface();
            return null;
        }

        public static Brep SafeDuplicate(Brep brep) => brep?.DuplicateBrep();
    }
}
