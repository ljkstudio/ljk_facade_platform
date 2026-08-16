using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using NUnit.Framework;
using Grasshopper.Kernel;
using AdaptiveMold.GH;

namespace AdaptiveMold.Tests
{
    public class HelpContractTests
    {
        static readonly string[] ExpectedInputs =
        {
            "target_srf", "base_plane", "width", "length",
            "spacing", "max_height", "min_height", "compute",
        };

        static readonly string[] ExpectedOutputs =
        {
            "pin_heights", "pin_tops", "grid_pts", "clamp_flags",
            "extension_flags", "info", "nx", "ny",
        };

        [Test]
        public void Component_registers_eight_in_and_eight_out_in_order()
        {
            var c = new AMv1PinsComponent();

            // 순서까지 본다. SolveInstance 가 DA.GetData(인덱스) 로 읽으므로
            // 순서가 바뀌면 값이 조용히 뒤섞인다 — 타입이 같은 double 이 5개다.
            Assert.That(c.Params.Input.Select(p => p.Name).ToArray(),
                Is.EqualTo(ExpectedInputs));
            Assert.That(c.Params.Output.Select(p => p.Name).ToArray(),
                Is.EqualTo(ExpectedOutputs));
        }

        static string ParamsJsonPath =>
            typeof(HelpContractTests).Assembly
                .GetCustomAttributes<AssemblyMetadataAttribute>()
                .First(a => a.Key == "ParamsJsonPath").Value;

        static (string[] inputs, string[] outputs) JsonNames()
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(ParamsJsonPath));
            var comp = doc.RootElement.GetProperty(ParamDocs.Component);
            return (comp.GetProperty("inputs").EnumerateObject().Select(p => p.Name).ToArray(),
                    comp.GetProperty("outputs").EnumerateObject().Select(p => p.Name).ToArray());
        }

        [Test]
        public void Check1_component_and_json_agree_both_ways()
        {
            // 스펙 §4.4 검사 1. 양방향이다 — 한쪽만 보면
            // "설명은 있는데 파라미터가 없다"나 그 반대가 조용히 남는다.
            var c = new AMv1PinsComponent();
            var (jsonIn, jsonOut) = JsonNames();

            Assert.Multiple(() =>
            {
                Assert.That(c.Params.Input.Select(p => p.Name), Is.EquivalentTo(jsonIn),
                    "입력: 컴포넌트와 params.ko.json 의 이름 집합이 다르다");
                Assert.That(c.Params.Output.Select(p => p.Name), Is.EquivalentTo(jsonOut),
                    "출력: 컴포넌트와 params.ko.json 의 이름 집합이 다르다");
            });
        }

        [Test]
        public void Check2_every_param_has_a_real_description()
        {
            // 스펙 §4.4 검사 2. build_gh_components.py:258 이 설명을 NickName 으로
            // 채우므로 그 상태를 "미작성"으로 판정한다.
            var c = new AMv1PinsComponent();
            var all = c.Params.Input.Cast<IGH_Param>().Concat(c.Params.Output.Cast<IGH_Param>());

            Assert.Multiple(() =>
            {
                foreach (var p in all)
                {
                    Assert.That(p.Description, Is.Not.Null.And.Not.Empty, $"{p.Name}: 설명이 비었다");
                    Assert.That(p.Description, Is.Not.EqualTo(p.NickName),
                        $"{p.Name}: 설명이 NickName 과 같다 = 미작성");
                    Assert.That(p.Description, Does.Not.StartWith(ParamDocs.MissingPrefix),
                        $"{p.Name}: params.ko.json 에 항목이 없다");
                    Assert.That(p.Description, Does.Not.Contain("**"),
                        $"{p.Name}: GH 툴팁은 평문이다 — 마크다운 금지");
                }
            });
        }

        [Test]
        public void Component_has_an_icon()
        {
            // 아이콘 리소스 이름은 csproj 의 LogicalName 에 달려 있어
            // 파일을 옮기면 조용히 null 이 된다. 검사로 묶어 둔다.
            var c = new AMv1PinsComponent();
            var icon = typeof(AMv1PinsComponent)
                .GetProperty("Icon", System.Reflection.BindingFlags.NonPublic
                                   | System.Reflection.BindingFlags.Instance)
                .GetValue(c) as System.Drawing.Bitmap;

            Assert.That(icon, Is.Not.Null, "아이콘 리소스를 못 찾았다 — LogicalName 확인");
            Assert.That(icon.Width, Is.EqualTo(24));
            Assert.That(icon.Height, Is.EqualTo(24));
        }

        [Test]
        public void Component_description_carries_the_indexing_rule()
        {
            // 컴포넌트 설명 계층(설계 §4.2)에 반드시 있어야 하는 것.
            // 인덱싱 규약을 모르면 grid_pts 를 되접을 수 없다.
            var c = new AMv1PinsComponent();
            Assert.That(c.Description, Does.Contain("idx = j * nx + i"));
            Assert.That(c.Description, Does.Contain("mm"));
        }
    }
}
