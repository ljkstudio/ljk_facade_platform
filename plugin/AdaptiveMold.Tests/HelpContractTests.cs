using System.Linq;
using NUnit.Framework;
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
    }
}
