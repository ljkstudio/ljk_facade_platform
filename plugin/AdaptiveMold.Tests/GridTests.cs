using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using AdaptiveMold.Core;
using Rhino.Geometry;

namespace AdaptiveMold.Tests
{
    public class GridTests
    {
        static string FixtureDir =>
            Path.Combine(TestContext.CurrentContext.TestDirectory, "fixtures");

        public static IEnumerable<string> FixtureFiles()
        {
            foreach (var p in Directory.GetFiles(FixtureDir, "T*.json"))
                yield return p;
        }

        [TestCaseSource(nameof(FixtureFiles))]
        public void Grid_points_match_python(string path)
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            var input = doc.RootElement.GetProperty("input");
            var prm = input.GetProperty("params");

            var planeOrNull = TestSurfaceBuilder.BuildPlane(input.GetProperty("base_plane"));
            var plane = planeOrNull ?? Plane.WorldXY;

            var (pts, nx, ny) = Grid.Build(plane,
                prm.GetProperty("width").GetDouble(),
                prm.GetProperty("length").GetDouble(),
                prm.GetProperty("spacing").GetDouble());

            var expected = doc.RootElement.GetProperty("expected").GetProperty("grid_pts");

            Assert.That(pts.Count, Is.EqualTo(expected.GetArrayLength()), "핀 개수");
            Assert.That(nx * ny, Is.EqualTo(pts.Count), "nx*ny 와 개수가 어긋난다");

            for (int k = 0; k < pts.Count; k++)
            {
                var e = expected[k];
                Assert.That(pts[k].X, Is.EqualTo(e[0].GetDouble()).Within(1e-6), $"pt[{k}].X");
                Assert.That(pts[k].Y, Is.EqualTo(e[1].GetDouble()).Within(1e-6), $"pt[{k}].Y");
                Assert.That(pts[k].Z, Is.EqualTo(e[2].GetDouble()).Within(1e-6), $"pt[{k}].Z");
            }
        }

        [Test]
        public void Counts_clamp_to_two()
        {
            // grid.py:35-38 — nx<2 면 2로 올린다. 하류가 이 클램프를 빠뜨리고
            // int(width // spacing) + 1 로 재유도하고 있었다(AMv1_Inspect.py:322).
            var (nx, ny) = Grid.ComputeCounts(100.0, 100.0, 1000.0);
            Assert.That(nx, Is.EqualTo(2));
            Assert.That(ny, Is.EqualTo(2));
        }

        [Test]
        public void Invalid_spacing_throws()
        {
            var ex = Assert.Throws<System.ArgumentException>(
                () => Grid.ComputeCounts(1000.0, 1000.0, 0.0));
            Assert.That(ex.Message, Does.Contain("spacing"));
        }

        [Test]
        public void Index_roundtrip()
        {
            // idx = j * nx + i. 여기서 순서가 바뀌면 픽스처 대조가 전부 무의미해진다.
            const int nx = 6;
            for (int j = 0; j < 4; j++)
                for (int i = 0; i < nx; i++)
                {
                    int idx = Grid.FlatIndex(i, j, nx);
                    var (bi, bj) = Grid.Indices(idx, nx);
                    Assert.That((bi, bj), Is.EqualTo((i, j)));
                }
        }
    }
}
