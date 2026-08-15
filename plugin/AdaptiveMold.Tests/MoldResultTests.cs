using NUnit.Framework;
using AdaptiveMold.Core;

namespace AdaptiveMold.Tests
{
    public class MoldResultTests
    {
        [Test]
        public void New_result_is_empty_but_not_null()
        {
            var r = new MoldResult();

            Assert.That(r.PinHeights, Is.Not.Null.And.Empty);
            Assert.That(r.ClampFlags, Is.Not.Null.And.Empty);
            Assert.That(r.ExtensionFlags, Is.Not.Null.And.Empty);
            Assert.That(r.GridPts, Is.Not.Null.And.Empty);
            Assert.That(r.PinTops, Is.Not.Null.And.Empty);
            Assert.That(r.BranchTaken, Is.Not.Null.And.Empty);
            Assert.That(r.Messages, Is.Not.Null.And.Empty);
            Assert.That(r.Info, Is.EqualTo(string.Empty));
        }

        [Test]
        public void Messages_keep_level_and_order()
        {
            var r = new MoldResult();
            r.AddRemark("첫 번째");
            r.AddWarning("두 번째");
            r.AddError("세 번째");

            Assert.That(r.Messages.Count, Is.EqualTo(3));
            Assert.That(r.Messages[0].Level, Is.EqualTo(MoldMessageLevel.Remark));
            Assert.That(r.Messages[1].Level, Is.EqualTo(MoldMessageLevel.Warning));
            Assert.That(r.Messages[2].Level, Is.EqualTo(MoldMessageLevel.Error));
            Assert.That(r.Messages[2].Text, Is.EqualTo("세 번째"));
        }

        [Test]
        public void Level_names_match_the_python_fixture_strings()
        {
            // 픽스처의 messages 는 [level, text] 이고 level 은 파이썬 쪽
            // GH_RuntimeMessageLevel 을 str() 한 값이다. Task 12 의 메시지 대조가
            // MoldMessageLevel.ToString() 과 그 문자열을 직접 비교하므로
            // 이름이 갈리면 전 케이스가 깨진다.
            Assert.That(MoldMessageLevel.Remark.ToString(), Is.EqualTo("Remark"));
            Assert.That(MoldMessageLevel.Warning.ToString(), Is.EqualTo("Warning"));
            Assert.That(MoldMessageLevel.Error.ToString(), Is.EqualTo("Error"));
        }
    }
}
