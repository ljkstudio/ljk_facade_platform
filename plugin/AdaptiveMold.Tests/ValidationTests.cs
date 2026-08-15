using NUnit.Framework;
using AdaptiveMold.Core;
using Rhino.Geometry;

namespace AdaptiveMold.Tests
{
    public class ValidationTests
    {
        [Test]
        public void Negative_and_zero_fall_back_to_default_silently()
        {
            // utils.py:52-63 — 음수·0·null 을 조용히 기본값으로 되돌린다.
            // GH 파라미터 기본값만 주고 이 정규화를 생략하면 -5 가 그대로 들어와
            // 동작이 갈린다(설계 §3.5).
            Assert.That(Validation.PositiveOrDefault(-5.0, 1000.0), Is.EqualTo(1000.0));
            Assert.That(Validation.PositiveOrDefault(0.0, 1000.0), Is.EqualTo(1000.0));
            Assert.That(Validation.PositiveOrDefault(null, 1000.0), Is.EqualTo(1000.0));
            Assert.That(Validation.PositiveOrDefault(250.0, 1000.0), Is.EqualTo(250.0));
        }

        [Test]
        public void Non_negative_allows_zero()
        {
            Assert.That(Validation.NonNegativeOrDefault(0.0, 0.0), Is.EqualTo(0.0));
            Assert.That(Validation.NonNegativeOrDefault(-1.0, 0.0), Is.EqualTo(0.0));
            Assert.That(Validation.NonNegativeOrDefault(50.0, 0.0), Is.EqualTo(50.0));
        }

        [Test]
        public void Nan_and_infinity_fall_back_too()
        {
            // 파이썬에서 벗어나는 **유일한** 지점이다. float('nan') <= 0 은 False 라
            // 파이썬은 NaN 을 통과시키고, 그 값이 흘러가면 전 핀이 NaN 이 된다.
            // 여기서만 막는다 — 저널에 적었다.
            Assert.That(Validation.PositiveOrDefault(double.NaN, 1000.0), Is.EqualTo(1000.0));
            Assert.That(Validation.PositiveOrDefault(double.PositiveInfinity, 1000.0), Is.EqualTo(1000.0));
            Assert.That(Validation.NonNegativeOrDefault(double.NaN, 0.0), Is.EqualTo(0.0));
        }

        [Test]
        public void Surface_becomes_brep_and_brep_stays()
        {
            var srf = new PlaneSurface(Plane.WorldXY, new Interval(-1, 1), new Interval(-1, 1));
            Assert.That(Validation.ToBrep(srf), Is.Not.Null);

            var brep = srf.ToBrep();
            Assert.That(Validation.ToBrep(brep), Is.SameAs(brep));

            Assert.That(Validation.ToBrep(null), Is.Null);
        }

        [Test]
        public void First_face_only_for_surface_extraction()
        {
            // utils.py:136 — Brep 이면 Faces[0].UnderlyingSurface() 를 쓴다.
            // 다중 face 를 물리면 Phase C 가 첫 face 만 본다는 뜻이고,
            // 그래서 경고를 새로 넣었다(파이썬 쪽 Task 4).
            var srf = new PlaneSurface(Plane.WorldXY, new Interval(-1, 1), new Interval(-1, 1));
            var brep = srf.ToBrep();
            Assert.That(Validation.ToSurface(brep), Is.Not.Null);
        }
    }
}
