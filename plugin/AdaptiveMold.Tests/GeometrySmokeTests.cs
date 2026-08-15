using NUnit.Framework;
using Rhino.Geometry;

namespace AdaptiveMold.Tests
{
    /// <summary>
    /// 러너가 **네이티브 기하 연산**까지 태울 수 있는지 본다.
    ///
    /// 메타데이터만 읽는 테스트(CoreContractTests)는 Rhino 없이도 돈다.
    /// 그러나 역산 알고리즘은 전부 openNURBS 네이티브 호출이므로,
    /// 이 테스트가 도는지가 러너 선택을 정한다.
    /// </summary>
    public class GeometrySmokeTests
    {
        [Test]
        public void Sphere_to_brep_works()
        {
            var sphere = new Sphere(new Point3d(500, 500, 0), 400.0);
            var brep = sphere.ToBrep();

            Assert.That(brep, Is.Not.Null, "네이티브 openNURBS 호출이 되지 않는다");
            Assert.That(brep.Faces.Count, Is.EqualTo(1));

            var bb = brep.GetBoundingBox(true);
            Assert.That(bb.Min.X, Is.EqualTo(100.0).Within(1e-6));
            Assert.That(bb.Max.X, Is.EqualTo(900.0).Within(1e-6));
        }
    }
}
