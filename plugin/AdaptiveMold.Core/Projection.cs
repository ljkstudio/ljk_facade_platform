using System;
using System.Collections.Generic;
using Rhino.Geometry;
using Rhino.Geometry.Intersect;

namespace AdaptiveMold.Core
{
    /// <summary>
    /// Phase D — 격자점마다 높이를 산출하고 stroke 범위로 클램핑한다.
    /// <c>projection.py</c> 1:1 포팅. **가장 위험한 모듈이다** — 폴백이 4단계이고,
    /// 어느 가지를 탔는지가 값으로는 드러나지 않는다.
    ///
    /// 가지 문자열은 파이썬과 **정확히 일치**해야 한다.
    /// </summary>
    public static class Projection
    {
        public const string BranchRayPosPanel = "ray+/panel";
        public const string BranchRayNegPanel = "ray-/panel";
        public const string BranchRayPosExt = "ray+/ext";
        public const string BranchRayNegExt = "ray-/ext";
        public const string BranchTangent = "tangent";
        public const string BranchClosest = "closest";
        public const string BranchDefault = "default";

        public static (List<double> heights, List<bool> clamps, List<bool> extensions) CalculateHeights(
            IList<Point3d> gridPts, GeometryBase positionedSrf, GeometryBase extendedSrf,
            Plane basePlane, double minHeight, double maxHeight, string extensionMethod,
            IList<string> branchOut = null)
        {
            var positionedBrep = Validation.ToBrep(positionedSrf);
            var extendedBrep = Validation.ToBrep(extendedSrf);

            var normal = basePlane.ZAxis;
            var heights = new List<double>(gridPts.Count);
            var clamps = new List<bool>(gridPts.Count);
            var extensions = new List<bool>(gridPts.Count);

            foreach (var pt in gridPts)
            {
                double? h = null;
                bool isExtension;
                string branch = null;

                if (positionedBrep != null)
                {
                    var (hit, sign) = RayCastHeight(pt, normal, positionedBrep);
                    h = hit;
                    if (h.HasValue)
                        branch = sign == "+" ? BranchRayPosPanel : BranchRayNegPanel;
                }

                if (h.HasValue)
                {
                    isExtension = false;
                }
                else
                {
                    isExtension = true;

                    // Phase C 가 "Surface.Extend 였나 tangent 폴백이었나"를 여기로
                    // 실어 보낸다. 이 결합 때문에 C·D 를 캔버스에서 나누지 않는다.
                    if (extendedBrep != null && extensionMethod != Extension.MethodTangent)
                    {
                        var (hit, sign) = RayCastHeight(pt, normal, extendedBrep);
                        h = hit;
                        if (h.HasValue)
                            branch = sign == "+" ? BranchRayPosExt : BranchRayNegExt;
                    }

                    if (!h.HasValue && positionedBrep != null)
                    {
                        h = Extension.TangentExtrapolate(pt, positionedBrep, basePlane);
                        if (h.HasValue) branch = BranchTangent;
                    }

                    if (!h.HasValue)
                    {
                        h = ClosestPointHeight(pt, normal, extendedBrep ?? positionedBrep);
                        if (h.HasValue) branch = BranchClosest;
                    }
                }

                if (!h.HasValue)
                {
                    h = (minHeight + maxHeight) / 2.0;
                    isExtension = true;
                    branch = BranchDefault;
                }

                var (clamped, didClamp) = Clamp(h.Value, minHeight, maxHeight);
                heights.Add(clamped);
                clamps.Add(didClamp);
                extensions.Add(isExtension);
                branchOut?.Add(branch);
            }

            return (heights, clamps, extensions);
        }

        static (double? height, string sign) RayCastHeight(Point3d pt, Vector3d direction, Brep brep)
        {
            if (brep == null) return (null, null);

            var geo = new GeometryBase[] { brep };

            var hitsPos = Intersection.RayShoot(new Ray3d(pt, direction), geo, 1);
            if (hitsPos != null && hitsPos.Length > 0) return (pt.DistanceTo(hitsPos[0]), "+");

            var hitsNeg = Intersection.RayShoot(new Ray3d(pt, -direction), geo, 1);
            if (hitsNeg != null && hitsNeg.Length > 0) return (pt.DistanceTo(hitsNeg[0]), "-");

            return (null, null);
        }

        static double? ClosestPointHeight(Point3d pt, Vector3d normal, Brep brep)
        {
            if (brep == null) return null;
            var cp = brep.ClosestPoint(pt);   // 구조체 — null 이 될 수 없다
            var vec = cp - pt;
            return Math.Abs(vec * normal);
        }

        /// <summary>높이가 항상 양수인 것은 파이썬과 같다 — 부호 소실은 그대로 옮긴다.</summary>
        static (double h, bool clamped) Clamp(double h, double minHeight, double maxHeight)
        {
            if (h < minHeight) return (minHeight, true);
            if (h > maxHeight) return (maxHeight, true);
            return (h, false);
        }
    }
}
