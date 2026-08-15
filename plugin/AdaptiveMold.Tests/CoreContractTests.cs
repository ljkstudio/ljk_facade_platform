using System.IO;
using System.Linq;
using System.Reflection;
using System.Xml.Linq;
using NUnit.Framework;

namespace AdaptiveMold.Tests
{
    /// <summary>
    /// 설계 §3.1 — Core 의 규약을 기계가 지키게 한다.
    /// 사람이 지키기로 한 규약은 언젠가 깨진다.
    ///
    /// 검사 대상은 컴파일된 어셈블리가 아니라 **프로젝트 파일**이다.
    /// C# 컴파일러는 쓰지 않는 참조를 어셈블리 매니페스트에서 지우므로,
    /// Core 가 Grasshopper 를 참조하더라도 아직 쓰지 않았다면
    /// GetReferencedAssemblies() 에 안 나온다 — 통과해도 아무것도 보증하지 못한다.
    /// (2026-08-15 실측으로 확인. 처음 이 테스트를 어셈블리 기준으로 썼다가
    ///  RhinoCommon 참조가 System.Runtime 하나로 사라지는 것을 보고 고쳤다.)
    /// </summary>
    public class CoreContractTests
    {
        static XDocument CoreProject()
        {
            var path = typeof(CoreContractTests).Assembly
                .GetCustomAttributes<AssemblyMetadataAttribute>()
                .First(a => a.Key == "CoreCsprojPath")
                .Value;

            Assert.That(File.Exists(path), Is.True, $"Core 프로젝트 파일을 못 찾았다: {path}");
            return XDocument.Load(path);
        }

        static string[] PackageReferences(XDocument proj) =>
            proj.Descendants("PackageReference")
                .Select(e => (string)e.Attribute("Include"))
                .ToArray();

        [Test]
        public void Core_does_not_reference_Grasshopper()
        {
            Assert.That(PackageReferences(CoreProject()), Has.No.Member("Grasshopper"),
                "Core 가 Grasshopper 를 참조하면 테스트가 GH 를 요구하게 되고 "
                + ".rhp·REST 재사용이 막힌다 (설계 §3.1)");
        }

        [Test]
        public void Core_references_RhinoCommon()
        {
            Assert.That(PackageReferences(CoreProject()), Has.Member("RhinoCommon"),
                "역산 알고리즘은 RhinoCommon 기하 연산 위에서만 성립한다");
        }

        [Test]
        public void Core_does_not_reference_any_other_project()
        {
            var refs = CoreProject().Descendants("ProjectReference")
                .Select(e => (string)e.Attribute("Include"))
                .ToArray();

            Assert.That(refs, Is.Empty,
                "Core 는 아무것도 의존하지 않는 맨 아래층이다. "
                + "여기에 의존이 생기면 .rhp·REST 재사용이 그만큼 무거워진다");
        }

        [Test]
        public void Core_targets_net7_windows()
        {
            var tfm = CoreProject().Descendants("TargetFramework")
                .Select(e => e.Value).FirstOrDefault();

            Assert.That(tfm, Is.EqualTo("net7.0-windows"),
                "net8.0 은 구형 Rhino 8 에서 깨진다 (지시서 §3.1)");
        }
    }
}
