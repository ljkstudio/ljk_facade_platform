using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using AdaptiveMold.Core;
using Rhino.Geometry;

namespace AdaptiveMold.Tests
{
    public class ProjectionTests
    {
        static string FixtureDir =>
            Path.Combine(TestContext.CurrentContext.TestDirectory, "fixtures");

        public static IEnumerable<string> FixtureFiles()
        {
            foreach (var p in Directory.GetFiles(FixtureDir, "T*.json"))
                yield return p;
        }

        [TestCaseSource(nameof(FixtureFiles))]
        public void Heights_flags_and_branches_match_python(string path)
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            var input = doc.RootElement.GetProperty("input");
            var prm = input.GetProperty("params");
            var expected = doc.RootElement.GetProperty("expected");

            var plane = TestSurfaceBuilder.BuildPlane(input.GetProperty("base_plane")) ?? Plane.WorldXY;
            var target = TestSurfaceBuilder.BuildSurface(input.GetProperty("surface"));

            double w = prm.GetProperty("width").GetDouble();
            double l = prm.GetProperty("length").GetDouble();
            double s = prm.GetProperty("spacing").GetDouble();
            double minH = prm.GetProperty("min_height").GetDouble();
            double maxH = prm.GetProperty("max_height").GetDouble();

            var (gridPts, _, _) = Grid.Build(plane, w, l, s);
            var (positioned, _, _) = Optimization.Run(target, gridPts, plane, w, l, minH, maxH);
            var (extended, method, _) = Extension.Run(positioned, w, l);

            var branches = new List<string>();
            var (heights, clamps, exts) = Projection.CalculateHeights(
                gridPts, positioned, extended, plane, minH, maxH, method, branches);

            var eH = expected.GetProperty("pin_heights");
            var eC = expected.GetProperty("clamp_flags");
            var eE = expected.GetProperty("extension_flags");
            var eB = expected.GetProperty("branch_taken");

            Assert.That(heights.Count, Is.EqualTo(eH.GetArrayLength()), "핀 개수");

            Assert.Multiple(() =>
            {
                for (int i = 0; i < heights.Count; i++)
                {
                    Assert.That(heights[i], Is.EqualTo(eH[i].GetDouble()).Within(1e-6), $"pin_heights[{i}]");
                    // 플래그와 가지는 허용오차가 없다. 어긋나면 다른 경로를 탄 것이다.
                    Assert.That(clamps[i], Is.EqualTo(eC[i].GetBoolean()), $"clamp_flags[{i}]");
                    Assert.That(exts[i], Is.EqualTo(eE[i].GetBoolean()), $"extension_flags[{i}]");
                    Assert.That(branches[i], Is.EqualTo(eB[i].GetString()), $"branch_taken[{i}]");
                }
            });
        }
    }
}
