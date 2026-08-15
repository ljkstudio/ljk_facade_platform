using System;
using System.Collections.Generic;
using Rhino.Geometry;
using Rhino.Geometry.Intersect;

namespace AdaptiveMold.Core
{
    /// <summary>
    /// Phase B — 목표 곡면을 stroke 범위 안에 맞도록 정렬한다.
    /// <c>optimization.py</c> 의 1:1 포팅.
    ///
    /// **순차 누산 평균을 유지한다.** <c>sum(valid)/len(valid)</c> 가 delta_z 로
    /// 쓰이고 그 값이 모든 핀 높이에 실린다 — 누산 순서가 바뀌면 최하위 비트가
    /// 흔들리고 클램프 경계에서 불리언이 뒤집힌다. 병렬화·재정렬 금지.
    /// </summary>
    public static class Optimization
    {
        public const string BranchInvalidSurface = "invalid_surface";
        public const string BranchTranslateOnly = "translate_only";
        public const string BranchNoPoints = "no_points";

        /// <summary>
        /// **C# 에서는 도달할 수 없다.** 파이썬은 <c>FitPlaneToPoints</c> 가 None 이나
        /// 짧은 튜플을 돌려줄 때를 대비하는데, C# 시그니처는
        /// <c>PlaneFitResult</c> + <c>out Plane</c> 이라 그런 반환이 없다.
        /// 값을 지우지 않는 이유: 파이썬 쪽 상수와 짝을 이룬 목록이라
        /// 하나만 빠지면 "왜 6개지"가 된다.
        /// </summary>
        public const string BranchFitNone = "fit_none";

        public const string BranchFitFailed = "fit_failed";
        public const string BranchDupFailed = "dup_failed";
        public const string BranchFull = "full";

        /// <param name="messages">
        /// 런타임 메시지를 받을 목록. null 이면 아무것도 하지 않는다 —
        /// 파이썬의 <c>component=None</c> 과 같은 자리다. 메시지 문안은
        /// 픽스처 <c>expected.messages</c> 의 대조 대상이므로 파이썬과
        /// 한 글자도 달라지면 안 된다.
        /// </param>
        public static (Brep positioned, string info, string branch) Run(
            GeometryBase targetSrf, IList<Point3d> gridPts, Plane basePlane,
            double width, double length, double minHeight, double maxHeight,
            IList<MoldMessage> messages = null)
        {
            var brep = Validation.ToBrep(targetSrf);
            if (brep == null)
                return (null, "optimization skipped: invalid surface", BranchInvalidSurface);

            var (rawDistances, samplePts) = MeasureDistances(gridPts, basePlane, brep);

            var valid = new List<double>();
            foreach (var d in rawDistances) if (d.HasValue) valid.Add(d.Value);

            double targetH = (minHeight + maxHeight) / 2.0;

            if (valid.Count < 3)
            {
                // width·length 는 파이썬이 {:g} 로 찍는다. C# 의 G 와 같은 결과가
                // 나오는 범위(1e6 미만)에서만 같다 — 이 메시지는 T1~T9 이 태우지
                // 않아 대조로 검증되지 않는다.
                Warn(messages,
                    $"곡면 위에 놓인 격자점이 {valid.Count}개다 (정렬에 최소 3개 필요). "
                    + "Phase B 정렬을 건너뛰었고 모든 핀 높이가 외삽값이다. "
                    + "base_plane 의 원점은 몰드의 모서리다 — 곡면이 "
                    + $"X [0, {width:G}] · Y [0, {length:G}] 밖에 있는지 확인할 것.");

                var pos = Validation.SafeDuplicate(brep);
                if (valid.Count > 0)
                {
                    double avgD = Mean(valid);
                    double dz = targetH - avgD;
                    pos.Transform(Transform.Translation(basePlane.ZAxis * dz));
                    return (pos, $"translate only (dz={dz:F1}mm, {valid.Count} pts)", BranchTranslateOnly);
                }
                return (pos, "no optimization (0 in-bounds points)", BranchNoPoints);
            }

            // 파이썬은 `fit_result[0] == Success` 하나로 갈린다. Success 가 아닌 것은
            // Failure 든 Inconclusive 든 **전부** 평행이동 가지(OPT_FIT_FAILED)다.
            // 계획 초안은 Failure 를 BranchFitNone(평행이동 없음)으로 보냈는데,
            // 그러면 파이썬이 옮기는 곡면을 C# 은 안 옮긴다 — 성공 기준이
            // "똑같다"이므로 파이썬을 따른다. T1~T9 이 이 가지를 타지 않아
            // 대조로는 잡히지 않는 차이였다.
            var fitRc = Plane.FitPlaneToPoints(samplePts, out Plane fitPlane);
            if (fitRc != PlaneFitResult.Success)
            {
                var pos = Validation.SafeDuplicate(brep);
                double avgD = Mean(valid);
                double dz = targetH - avgD;
                pos.Transform(Transform.Translation(basePlane.ZAxis * dz));
                return (pos, $"plane fit failed, translate only (dz={dz:F1}mm)", BranchFitFailed);
            }

            var positioned = Validation.SafeDuplicate(brep);
            if (positioned == null)
                return (null, "DuplicateBrep failed", BranchDupFailed);

            var currentNormal = fitPlane.Normal;
            var targetNormal = Vector3d.ZAxis;

            // FitPlaneToPoints 는 법선 부호를 보장하지 않는다. 정규화하지 않으면
            // 회전각이 실제 기울기가 아니라 (180 - 기울기)로 나온다.
            if (currentNormal * targetNormal < 0) currentNormal = -currentNormal;

            var rotAxis = Vector3d.CrossProduct(currentNormal, targetNormal);
            double tiltAngle = 0.0;

            if (rotAxis.Length > 1e-10)
            {
                rotAxis.Unitize();
                double dot = Math.Max(-1.0, Math.Min(1.0, currentNormal * targetNormal));
                double rotAngle = Math.Acos(dot);
                // math.degrees 와 같은 식으로 쓴다 (미리 계산한 상수를 곱한다).
                // 이 값이 info 문자열과 Phase B Remark 에 실리고 그 메시지는
                // 대조 대상이다.
                tiltAngle = rotAngle * (180.0 / Math.PI);

                var pivot = Grid.Center(basePlane, width, length);

                var rotAxisWorld =
                    basePlane.XAxis * rotAxis.X +
                    basePlane.YAxis * rotAxis.Y +
                    basePlane.ZAxis * rotAxis.Z;
                rotAxisWorld.Unitize();

                // 벡터 a 를 b 로 돌리려면 축 (a x b) 둘레로 **+각도**만큼 돌린다.
                // 옛 파이썬 구현이 -rot_angle 을 써서 기울기를 정확히 2배로
                // 키웠다(J-003). 부호를 뒤집지 말 것.
                positioned.Transform(Transform.Rotation(rotAngle, rotAxisWorld, pivot));
            }

            var (newRaw, _) = MeasureDistances(gridPts, basePlane, positioned);
            var newValid = new List<double>();
            foreach (var d in newRaw) if (d.HasValue) newValid.Add(d.Value);

            double avgNew = newValid.Count > 0 ? Mean(newValid) : targetH;
            double deltaZ = targetH - avgNew;
            positioned.Transform(Transform.Translation(basePlane.ZAxis * deltaZ));

            var optInfo = $"tilt={tiltAngle:F1}deg, dz={deltaZ:F1}mm";
            Remark(messages, $"Phase B 정렬 완료 — {optInfo}.");

            return (positioned, optInfo, BranchFull);
        }

        static void Warn(IList<MoldMessage> msgs, string text) =>
            msgs?.Add(new MoldMessage(MoldMessageLevel.Warning, text));

        static void Remark(IList<MoldMessage> msgs, string text) =>
            msgs?.Add(new MoldMessage(MoldMessageLevel.Remark, text));

        /// <summary>순차 누산. Sum()/Average() 로 바꾸지 말 것 — 순서가 값을 정한다.</summary>
        static double Mean(IList<double> xs)
        {
            double s = 0.0;
            for (int i = 0; i < xs.Count; i++) s += xs[i];
            return s / xs.Count;
        }

        static (List<double?> raw, List<Point3d> samples) MeasureDistances(
            IList<Point3d> gridPts, Plane basePlane, Brep brep)
        {
            var normal = basePlane.ZAxis;
            var raw = new List<double?>(gridPts.Count);
            var samples = new List<Point3d>();

            foreach (var pt in gridPts)
            {
                double? hit = RayCastDistance(pt, normal, brep);
                raw.Add(hit);
                if (hit.HasValue && basePlane.RemapToPlaneSpace(pt, out Point3d local))
                    samples.Add(new Point3d(local.X, local.Y, hit.Value));
            }

            return (raw, samples);
        }

        /// <summary>
        /// 양방향 ray-cast. <c>Intersection.RayShoot</c> 는 **교점 배열**을 돌려준다 —
        /// 곡선 파라미터가 아니다(J-002 TRAP-01, 파이썬이 이것을 오용해 죽었었다).
        /// </summary>
        static double? RayCastDistance(Point3d pt, Vector3d direction, Brep brep)
        {
            var geo = new GeometryBase[] { brep };

            var hitsPos = Intersection.RayShoot(new Ray3d(pt, direction), geo, 1);
            if (hitsPos != null && hitsPos.Length > 0) return pt.DistanceTo(hitsPos[0]);

            var hitsNeg = Intersection.RayShoot(new Ray3d(pt, -direction), geo, 1);
            if (hitsNeg != null && hitsNeg.Length > 0) return pt.DistanceTo(hitsNeg[0]);

            return null;
        }
    }
}
