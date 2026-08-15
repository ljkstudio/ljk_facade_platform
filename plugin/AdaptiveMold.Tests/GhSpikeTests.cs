using NUnit.Framework;

namespace AdaptiveMold.Tests
{
    /// <summary>
    /// M3 Task 1 의 탐침. 자동검사 1·2 가 이 위에 선다.
    ///
    /// 여기가 깨지면 어댑터 계약 검사를 NUnit 이 아니라 브리지 스크립트로
    /// 옮겨야 한다 — 결론을 J-017 에 적을 것.
    /// </summary>
    public class GhSpikeTests
    {
        [Test]
        public void Can_construct_the_component_inside_the_test_alc()
        {
            var c = new AdaptiveMold.GH.AMv1PinsComponent();

            TestContext.WriteLine($"in={c.Params.Input.Count} out={c.Params.Output.Count} "
                                + $"name={c.Name} guid={c.ComponentGuid}");

            Assert.That(c.Params.Input.Count, Is.GreaterThan(0),
                "PostConstructor 가 RegisterInputParams 를 부르지 않았다");
            Assert.That(c.Params.Output.Count, Is.GreaterThan(0));
        }
    }
}
