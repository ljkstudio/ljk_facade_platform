using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using AdaptiveMold.Core;
using Rhino.Geometry;

namespace AdaptiveMold.Tests
{
    public class OptimizationTests
    {
        static string FixtureDir =>
            Path.Combine(TestContext.CurrentContext.TestDirectory, "fixtures");

        public static IEnumerable<string> FixtureFiles()
        {
            foreach (var p in Directory.GetFiles(FixtureDir, "T*.json"))
                yield return p;
        }

        [TestCaseSource(nameof(FixtureFiles))]
        public void Positioned_surface_matches_python(string path)
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
            var (positioned, _, branch) = Optimization.Run(target, gridPts, plane, w, l, minH, maxH);

            Assert.That(branch, Is.EqualTo(expected.GetProperty("opt_branch").GetString()),
                "Phase B 가 다른 가지를 탔다");

            var fp = expected.GetProperty("positioned_fingerprint");
            if (fp.ValueKind == JsonValueKind.Null)
            {
                Assert.That(positioned, Is.Null);
                return;
            }

            var actual = GeometryFingerprint.Compute(positioned);
            Assert.Multiple(() =>
            {
                for (int i = 0; i < 3; i++)
                {
                    Assert.That(actual.BBoxMin[i],
                        Is.EqualTo(fp.GetProperty("bbox_min")[i].GetDouble()).Within(1e-6), $"bbox_min[{i}]");
                    Assert.That(actual.BBoxMax[i],
                        Is.EqualTo(fp.GetProperty("bbox_max")[i].GetDouble()).Within(1e-6), $"bbox_max[{i}]");
                }
                Assert.That(actual.Area,
                    Is.EqualTo(fp.GetProperty("area").GetDouble()).Within(1e-6), "area");
            });
        }
    }
}
