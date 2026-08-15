using System;
using System.Collections.Generic;
using System.Text;
using Rhino.Geometry;

namespace AdaptiveMold.Core
{
    /// <summary>
    /// <c>run_adaptive_mold</c> 에서 Phase E 를 뺀 것.
    ///
    /// 여기 있는 것은 "조립"이 아니라 **계약**이다 — 입력 정규화, min>=max 의
    /// 에러 종료, compute=false 의 빈 결과, pin_tops 산식, 리포트 문자열.
    /// 이것들이 어댑터로 흩어지면 대조가 불가능해진다(설계 §3.2).
    /// </summary>
    public static class MoldSolver
    {
        public static MoldResult Run(
            GeometryBase targetSrf, Plane? basePlaneOrNull,
            double width, double length, double spacing,
            double maxHeight, double minHeight, bool compute)
        {
            var result = new MoldResult();

            if (!compute)
            {
                result.Info = "Compute is disabled. Set compute=True to run.";
                result.AddRemark("compute 가 꺼져 있다. 계산하려면 Boolean Toggle 을 True 로.");
                return result;
            }

            var basePlane = basePlaneOrNull ?? Plane.WorldXY;

            width = Validation.PositiveOrDefault(width, 1000.0);
            length = Validation.PositiveOrDefault(length, 1000.0);
            spacing = Validation.PositiveOrDefault(spacing, 200.0);
            maxHeight = Validation.PositiveOrDefault(maxHeight, 400.0);
            minHeight = Validation.NonNegativeOrDefault(minHeight, 0.0);

            if (minHeight >= maxHeight)
            {
                result.AddError($"min_height ({Num(minHeight)}) 가 max_height ({Num(maxHeight)}) 보다 "
                              + "크거나 같다. 계산하지 않았다. 두 값을 확인할 것.");
                return result;
            }

            if (targetSrf == null)
            {
                result.AddError("target_srf 가 비어 있다. Surface 또는 Brep 을 물릴 것.");
                return result;
            }

            var targetBrep = Validation.ToBrep(targetSrf);
            if (targetBrep == null)
            {
                result.AddError("target_srf 에서 Brep 을 얻지 못했다. Surface 또는 Brep 을 "
                              + "물릴 것 (Mesh·Curve·Point 는 받지 않는다).");
                return result;
            }

            // --- Phase A ---
            List<Point3d> gridPts;
            int nx, ny;
            try
            {
                (gridPts, nx, ny) = Grid.Build(basePlane, width, length, spacing);
            }
            catch (ArgumentException e)
            {
                result.AddError(e.Message);
                return result;
            }

            result.GridPts = gridPts;
            result.Nx = nx;
            result.Ny = ny;
            int totalPins = nx * ny;

            double remX = width - (nx - 1) * spacing;
            double remY = length - (ny - 1) * spacing;
            if (remX > 1e-9 || remY > 1e-9)
            {
                result.AddRemark(
                    $"spacing {spacing:G} 이 몰드 크기를 나누지 못한다. 핀은 X 방향 "
                    + $"{(nx - 1) * spacing:G}mm, Y 방향 {(ny - 1) * spacing:G}mm 까지만 덮는다 "
                    + $"(나머지 {remX:G}/{remY:G}mm 는 비어 있다).");
            }

            // --- Phase B ---
            var (positioned, optInfo, optBranch) = Optimization.Run(
                targetBrep, gridPts, basePlane, width, length, minHeight, maxHeight,
                result.Messages);
            result.OptBranch = optBranch;

            if (positioned == null)
            {
                result.AddError("Phase B 정렬이 실패했다 (DuplicateBrep 실패). "
                              + "곡면이 유효한지 확인할 것.");
                return result;
            }

            // --- Phase C ---
            // 다중 face 경고는 Extension.Run 안에 있다 (파이썬과 같은 자리).
            var (extended, extMethod, extBranch) = Extension.Run(
                positioned, width, length, result.Messages);
            result.ExtBranch = extBranch;

            // --- Phase D ---
            var (heights, clamps, exts) = Projection.CalculateHeights(
                gridPts, positioned, extended, basePlane,
                minHeight, maxHeight, extMethod, result.BranchTaken);

            result.PinHeights = heights;
            result.ClampFlags = clamps;
            result.ExtensionFlags = exts;

            int nClamped = 0;
            foreach (var c in clamps) if (c) nClamped++;
            if (nClamped > 0)
            {
                result.AddWarning($"핀 {nClamped}/{totalPins} 개가 행정 한계에 걸렸다. "
                    + "그 지점은 목표 곡면을 재현하지 못한다. clamp_flags 로 위치를 "
                    + "확인하고, max_height 를 늘리거나 곡면을 완만하게 할 것.");
            }

            // pin_tops — housing 높이 0 기준 (설계 §3.5). 파이썬은
            // transformation.get_housing_height 를 더하지만 그 모듈은 범위 밖이고
            // get_housing_height(None) == 0.0 이라 값이 같다.
            var normal = basePlane.ZAxis;
            result.PinTops = new List<Point3d>(gridPts.Count);
            for (int i = 0; i < gridPts.Count; i++)
                result.PinTops.Add(gridPts[i] + normal * heights[i]);

            result.Info = BuildReport(nx, ny, width, length, optInfo, extMethod,
                                      heights, clamps, exts, totalPins);

            result.AddRemark($"AdaptiveMold v1 계산 완료. 핀 {totalPins}개.");
            return result;
        }

        /// <summary>
        /// 파이썬 <c>"{}".format(float)</c> 는 200.0 을 "200.0" 으로 찍는다.
        /// .NET 의 기본 <c>ToString()</c> 은 "200" 이라 메시지 문안이 갈린다.
        /// </summary>
        static string Num(double v) =>
            v == Math.Floor(v) && !double.IsInfinity(v)
                ? v.ToString("0.0##############", System.Globalization.CultureInfo.InvariantCulture)
                : v.ToString("R", System.Globalization.CultureInfo.InvariantCulture);

        /// <summary>
        /// 리포트 문자열. **대조 대상이 아니다**(설계 §5.1) — 파이썬 <c>{:.0f}</c> 는
        /// 짝수 반올림, .NET <c>F0</c> 은 away-from-zero 라 .5 경계에서 갈린다.
        /// 항목 구성은 <c>_build_report</c> 를 그대로 따른다 — 사용자가 보는 것이다.
        /// </summary>
        static string BuildReport(int nx, int ny, double width, double length,
            string optInfo, string extMethod, IList<double> heights,
            IList<bool> clamps, IList<bool> exts, int totalPins)
        {
            int nClamp = 0; foreach (var c in clamps) if (c) nClamp++;
            int nExt = 0; foreach (var e in exts) if (e) nExt++;
            int nPanel = exts.Count - nExt;

            double hMin = 0, hMax = 0, hAvg = 0;
            if (heights.Count > 0)
            {
                hMin = double.MaxValue; hMax = double.MinValue;
                double sum = 0.0;
                foreach (var h in heights)
                {
                    if (h < hMin) hMin = h;
                    if (h > hMax) hMax = h;
                    sum += h;
                }
                hAvg = sum / heights.Count;
            }

            var lines = new List<string>
            {
                "AdaptiveMold v1 Report",
                new string('=', 30),
                $"Mold:        {width:F0} x {length:F0} mm   Grid: {nx} x {ny}  ({totalPins} actuators)",
                $"Surface:     optimized via {optInfo}",
                $"Extension:   {extMethod}",
                $"Coverage:    {nPanel} / {totalPins} on panel,  {nExt} / {totalPins} in extension zone",
                $"Heights:     min={hMin:F0}, max={hMax:F0}, avg={hAvg:F0} mm",
                $"Clamped:     {nClamp} / {totalPins}",
            };

            return string.Join("\n", lines);
        }
    }
}
