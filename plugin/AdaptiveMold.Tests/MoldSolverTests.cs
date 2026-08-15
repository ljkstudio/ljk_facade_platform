using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using AdaptiveMold.Core;
using Rhino.Geometry;

namespace AdaptiveMold.Tests
{
    public class MoldSolverTests
    {
        static string FixtureDir =>
            Path.Combine(TestContext.CurrentContext.TestDirectory, "fixtures");

        public static IEnumerable<string> FixtureFiles()
        {
            foreach (var p in Directory.GetFiles(FixtureDir, "T*.json"))
                yield return p;
        }

        [Test]
        public void Compute_false_returns_empty_lists_not_null()
        {
            var r = MoldSolver.Run(null, null, 1000, 1000, 200, 400, 0, compute: false);

            Assert.That(r.PinHeights, Is.Empty);
            Assert.That(r.GridPts, Is.Empty);
            Assert.That(r.Info, Does.Contain("Compute is disabled"));
            Assert.That(r.Messages, Has.Some.Matches<MoldMessage>(
                m => m.Level == MoldMessageLevel.Remark && m.Text.Contains("compute")));
        }

        [Test]
        public void Min_ge_max_is_an_error_not_an_exception()
        {
            var srf = new PlaneSurface(Plane.WorldXY, new Interval(-500, 500), new Interval(-500, 500));
            var r = MoldSolver.Run(srf.ToBrep(), null, 1000, 1000, 200, 100, 100, compute: true);

            Assert.That(r.PinHeights, Is.Empty);
            Assert.That(r.Messages, Has.Some.Matches<MoldMessage>(
                m => m.Level == MoldMessageLevel.Error));
        }

        [Test]
        public void Negative_width_falls_back_silently()
        {
            var srf = new PlaneSurface(Plane.WorldXY, new Interval(-2000, 2000), new Interval(-2000, 2000));
            var r = MoldSolver.Run(srf.ToBrep(), null, -5, 1000, 200, 400, 0, compute: true);

            // width -5 -> 1000 이므로 nx = floor(1000/200)+1 = 6
            Assert.That(r.Nx, Is.EqualTo(6));
        }

        [TestCaseSource(nameof(FixtureFiles))]
        public void Full_pipeline_matches_python(string path)
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            var input = doc.RootElement.GetProperty("input");
            var prm = input.GetProperty("params");
            var expected = doc.RootElement.GetProperty("expected");

            Plane? plane = TestSurfaceBuilder.BuildPlane(input.GetProperty("base_plane"));
            var target = TestSurfaceBuilder.BuildSurface(input.GetProperty("surface"));

            var r = MoldSolver.Run(target, plane,
                prm.GetProperty("width").GetDouble(),
                prm.GetProperty("length").GetDouble(),
                prm.GetProperty("spacing").GetDouble(),
                prm.GetProperty("max_height").GetDouble(),
                prm.GetProperty("min_height").GetDouble(),
                compute: true);

            var eH = expected.GetProperty("pin_heights");
            var eT = expected.GetProperty("pin_tops");
            var eC = expected.GetProperty("clamp_flags");
            var eE = expected.GetProperty("extension_flags");
            var eB = expected.GetProperty("branch_taken");

            Assert.That(r.PinHeights.Count, Is.EqualTo(eH.GetArrayLength()), "핀 개수");

            Assert.Multiple(() =>
            {
                for (int i = 0; i < r.PinHeights.Count; i++)
                {
                    Assert.That(r.PinHeights[i], Is.EqualTo(eH[i].GetDouble()).Within(1e-6), $"h[{i}]");
                    Assert.That(r.PinTops[i].X, Is.EqualTo(eT[i][0].GetDouble()).Within(1e-6), $"top[{i}].X");
                    Assert.That(r.PinTops[i].Y, Is.EqualTo(eT[i][1].GetDouble()).Within(1e-6), $"top[{i}].Y");
                    Assert.That(r.PinTops[i].Z, Is.EqualTo(eT[i][2].GetDouble()).Within(1e-6), $"top[{i}].Z");
                    Assert.That(r.ClampFlags[i], Is.EqualTo(eC[i].GetBoolean()), $"clamp[{i}]");
                    Assert.That(r.ExtensionFlags[i], Is.EqualTo(eE[i].GetBoolean()), $"ext[{i}]");
                    Assert.That(r.BranchTaken[i], Is.EqualTo(eB[i].GetString()), $"branch[{i}]");
                }
                Assert.That(r.OptBranch, Is.EqualTo(expected.GetProperty("opt_branch").GetString()));
                Assert.That(r.ExtBranch, Is.EqualTo(expected.GetProperty("ext_branch").GetString()));
            });
        }

        [TestCaseSource(nameof(FixtureFiles))]
        public void Messages_match_python(string path)
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            var input = doc.RootElement.GetProperty("input");
            var prm = input.GetProperty("params");
            var expected = doc.RootElement.GetProperty("expected").GetProperty("messages");

            Plane? plane = TestSurfaceBuilder.BuildPlane(input.GetProperty("base_plane"));
            var target = TestSurfaceBuilder.BuildSurface(input.GetProperty("surface"));

            var r = MoldSolver.Run(target, plane,
                prm.GetProperty("width").GetDouble(), prm.GetProperty("length").GetDouble(),
                prm.GetProperty("spacing").GetDouble(), prm.GetProperty("max_height").GetDouble(),
                prm.GetProperty("min_height").GetDouble(), compute: true);

            Assert.That(r.Messages.Count, Is.EqualTo(expected.GetArrayLength()),
                "메시지 개수가 다르다 — 등급이나 문안이 아니라 '몇 개 올라가는가'부터 맞춰야 한다");

            for (int i = 0; i < r.Messages.Count; i++)
            {
                Assert.That(r.Messages[i].Level.ToString(),
                    Is.EqualTo(expected[i][0].GetString()), $"messages[{i}].level");
                Assert.That(r.Messages[i].Text,
                    Is.EqualTo(expected[i][1].GetString()), $"messages[{i}].text");
            }
        }

        [Test]
        public void T8_is_under_500ms_median()
        {
            var path = Path.Combine(FixtureDir, "T8_large_grid.json");
            using var doc = JsonDocument.Parse(File.ReadAllText(path));
            var input = doc.RootElement.GetProperty("input");
            var prm = input.GetProperty("params");
            var target = TestSurfaceBuilder.BuildSurface(input.GetProperty("surface"));

            double w = prm.GetProperty("width").GetDouble();
            double l = prm.GetProperty("length").GetDouble();
            double s = prm.GetProperty("spacing").GetDouble();
            double minH = prm.GetProperty("min_height").GetDouble();
            double maxH = prm.GetProperty("max_height").GetDouble();

            // 워밍업 1회 — 첫 호출은 프로세스 1회성 비용을 포함한다(J-015 Q1 실측).
            MoldSolver.Run(target, null, w, l, s, maxH, minH, true);

            var times = new List<double>();
            for (int i = 0; i < 5; i++)
            {
                var sw = System.Diagnostics.Stopwatch.StartNew();
                MoldSolver.Run(target, null, w, l, s, maxH, minH, true);
                sw.Stop();
                times.Add(sw.Elapsed.TotalMilliseconds);
            }
            times.Sort();
            double median = times[times.Count / 2];

            TestContext.WriteLine($"T8 median = {median:F1} ms  (all: {string.Join(", ", times)})");
            Assert.That(median, Is.LessThan(500.0),
                "파이썬 실측이 25~49ms 다. 500ms 를 넘으면 회귀다.");
        }
    }
}
