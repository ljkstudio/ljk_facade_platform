using NUnit.Framework;
using AdaptiveMold.GH;

namespace AdaptiveMold.Tests
{
    public class ParamDocsTests
    {
        [Test]
        public void Embedded_json_is_reachable_and_has_all_sixteen()
        {
            Assert.That(ParamDocs.Inputs.Count, Is.EqualTo(8), "입력 설명 8개");
            Assert.That(ParamDocs.Outputs.Count, Is.EqualTo(8), "출력 설명 8개");
        }

        [Test]
        public void Known_names_return_the_real_text()
        {
            Assert.That(ParamDocs.In("target_srf"), Does.StartWith("목표 곡면"));
            Assert.That(ParamDocs.Out("nx"), Does.Contain("floor(width / spacing) + 1"));
        }

        [Test]
        public void Unknown_name_is_loud_but_does_not_throw()
        {
            // 던지면 정적 생성자·등록 단계에서 터지고, GH 는 그런 컴포넌트를
            // **조용히 팔레트에서 뺀다**(J-015 TRAP-03 과 같은 실패 방식).
            // 사라지는 것보다 이상한 툴팁이 낫다 — 그리고 자동검사 1 이 잡는다.
            var s = ParamDocs.In("no_such_param");
            Assert.That(s, Does.StartWith(ParamDocs.MissingPrefix));
            Assert.That(s, Does.Contain("no_such_param"));
        }
    }
}
