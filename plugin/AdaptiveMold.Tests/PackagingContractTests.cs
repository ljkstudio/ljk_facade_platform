using System.IO;
using System.Linq;
using System.Reflection;
using System.Xml.Linq;
using NUnit.Framework;

namespace AdaptiveMold.Tests
{
    /// <summary>
    /// 배포 가능성에 걸리는 빌드 설정을 지킨다.
    ///
    /// 여기 있는 규칙은 전부 **실제로 당한 것**이다 (J-015).
    /// 증상이 조용해서 특히 위험하다 — Grasshopper 는 자기보다 높은 API 로
    /// 빌드된 .gha 를 로드는 하고 등록만 안 하며, 예외도 남기지 않는다.
    /// </summary>
    public class PackagingContractTests
    {
        static XDocument Project(string key)
        {
            var path = typeof(PackagingContractTests).Assembly
                .GetCustomAttributes<AssemblyMetadataAttribute>()
                .First(a => a.Key == key).Value;

            Assert.That(File.Exists(path), Is.True, $"프로젝트 파일을 못 찾았다: {path}");
            return XDocument.Load(path);
        }

        static (string name, string version)[] Packages(XDocument proj) =>
            proj.Descendants("PackageReference")
                .Select(e => ((string)e.Attribute("Include"), (string)e.Attribute("Version")))
                .ToArray();

        [TestCase("CoreCsprojPath")]
        [TestCase("GhCsprojPath")]
        public void Rhino_packages_are_pinned_not_floating(string key)
        {
            foreach (var (name, version) in Packages(Project(key)))
            {
                if (name != "RhinoCommon" && name != "Grasshopper") continue;

                Assert.That(version, Does.Not.Contain("*"),
                    $"{name} 버전이 부동({version})이다. NuGet 이 최신을 끌어오면 "
                    + "설치된 Rhino 보다 높은 API 로 빌드되고, Grasshopper 는 "
                    + "그런 .gha 를 **조용히 등록 거부**한다 (J-015 TRAP-03). "
                    + "지원하는 가장 낮은 버전으로 고정할 것.");

                Assert.That(version, Does.StartWith("8.0."),
                    $"{name} 을 8.0 기준선으로 고정할 것 (현재 {version}). "
                    + "높게 잡으면 그보다 낮은 Rhino 에서 침묵 실패한다.");
            }
        }

        [TestCase("CoreCsprojPath")]
        [TestCase("GhCsprojPath")]
        public void Rhino_packages_exclude_runtime_assets(string key)
        {
            var proj = Project(key);
            foreach (var e in proj.Descendants("PackageReference"))
            {
                var name = (string)e.Attribute("Include");
                if (name != "RhinoCommon" && name != "Grasshopper") continue;

                Assert.That((string)e.Attribute("ExcludeAssets"), Is.EqualTo("runtime"),
                    $"{name} 은 ExcludeAssets=runtime 이어야 한다. "
                    + "Rhino 가 이미 로드해 둔 것을 출력에 복사하면 버전이 갈린다.");
            }
        }

        [Test]
        public void Gha_copies_its_dependencies()
        {
            var v = Project("GhCsprojPath").Descendants("CopyLocalLockFileAssemblies")
                .Select(e => e.Value).FirstOrDefault();

            Assert.That(v, Is.EqualTo("true"),
                "없으면 NuGet 의존 DLL 이 출력에 복사되지 않아 "
                + "의존성 빠진 .gha 가 패키징된다.");
        }
    }
}
