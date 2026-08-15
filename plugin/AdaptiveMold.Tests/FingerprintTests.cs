using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using Rhino.Geometry;

namespace AdaptiveMold.Tests
{
    /// <summary>
    /// **입력 동일성 증명.** 픽스처의 input.surface 는 직렬화된 지오메트리가 아니라
    /// 생성 스펙이므로, C# 이 같은 스펙으로 같은 곡면을 만드는지 먼저 증명해야
    /// 이후의 출력 대조(핀 높이·플래그·폴백 가지)가 의미를 갖는다.
    ///
    /// 이 테스트가 깨지면 Core 를 의심하기 전에 TestSurfaceBuilder 를 본다.
    /// </summary>
    public class FingerprintTests
    {
        static string FixtureDir =>
            Path.Combine(TestContext.CurrentContext.TestDirectory, "fixtures");

        public static IEnumerable<string> FixtureFiles()
        {
            foreach (var p in Directory.GetFiles(FixtureDir, "T*.json"))
                yield return p;
        }

        [TestCaseSource(nameof(FixtureFiles))]
        public void Csharp_builds_the_same_surface(string path)
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            var input = doc.RootElement.GetProperty("input");
            var expected = input.GetProperty("fingerprint");

            var brep = TestSurfaceBuilder.BuildSurface(input.GetProperty("surface"));
            var actual = GeometryFingerprint.Compute(brep);

            Assert.Multiple(() =>
            {
                Assert.That(actual.FaceCount,
                    Is.EqualTo(expected.GetProperty("face_count").GetInt32()), "face_count");
                Assert.That(actual.DegreeU,
                    Is.EqualTo(expected.GetProperty("degree_u").GetInt32()), "degree_u");
                Assert.That(actual.DegreeV,
                    Is.EqualTo(expected.GetProperty("degree_v").GetInt32()), "degree_v");
                Assert.That(actual.CvU,
                    Is.EqualTo(expected.GetProperty("cv_u").GetInt32()), "cv_u");
                Assert.That(actual.CvV,
                    Is.EqualTo(expected.GetProperty("cv_v").GetInt32()), "cv_v");

                AssertTriple(expected.GetProperty("bbox_min"), actual.BBoxMin, "bbox_min");
                AssertTriple(expected.GetProperty("bbox_max"), actual.BBoxMax, "bbox_max");

                var area = expected.GetProperty("area");
                if (area.ValueKind != JsonValueKind.Null)
                    Assert.That(actual.Area,
                        Is.EqualTo(area.GetDouble()).Within(1e-6), "area");
            });
        }

        [TestCaseSource(nameof(FixtureFiles))]
        public void Csharp_builds_the_same_base_plane(string path)
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            var input = doc.RootElement.GetProperty("input");
            var expected = input.GetProperty("plane_fingerprint");

            var plane = TestSurfaceBuilder.BuildPlane(input.GetProperty("base_plane"));

            if (expected.ValueKind == JsonValueKind.Null)
            {
                Assert.That(plane.HasValue, Is.False,
                    "파이썬은 base_plane 이 없다고(= WorldXY) 했다");
                return;
            }

            Assert.That(plane.HasValue, Is.True);
            var p = plane.Value;

            Assert.Multiple(() =>
            {
                AssertTriple(expected.GetProperty("origin"),
                    new[] { p.Origin.X, p.Origin.Y, p.Origin.Z }, "origin");
                AssertTriple(expected.GetProperty("x_axis"),
                    new[] { p.XAxis.X, p.XAxis.Y, p.XAxis.Z }, "x_axis");
                AssertTriple(expected.GetProperty("y_axis"),
                    new[] { p.YAxis.X, p.YAxis.Y, p.YAxis.Z }, "y_axis");
                AssertTriple(expected.GetProperty("z_axis"),
                    new[] { p.ZAxis.X, p.ZAxis.Y, p.ZAxis.Z }, "z_axis");
            });
        }

        static void AssertTriple(JsonElement expected, double[] actual, string label)
        {
            for (int i = 0; i < 3; i++)
                Assert.That(actual[i],
                    Is.EqualTo(expected[i].GetDouble()).Within(1e-6), $"{label}[{i}]");
        }
    }
}
