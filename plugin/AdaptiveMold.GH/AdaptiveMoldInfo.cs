using System;
using System.Drawing;
using Grasshopper.Kernel;

namespace AdaptiveMold.GH
{
    public class AdaptiveMoldInfo : GH_AssemblyInfo
    {
        /// <summary>
        /// GH 플러그인 목록에 보이는 이름.
        ///
        /// 주의: yak spec 이 **패키지 이름을 이 값에서 유도하고 공백을 하이픈으로
        /// 바꾼다** (J-015 TRAP-01). 그대로 두면 `LJKS-AdaptiveMold` 가 나오는데
        /// 설계가 정한 패키지 id 는 `ljks-adaptive-mold` 다.
        /// → 매니페스트의 name 은 손으로 고친다. 최초 업로드의 대소문자가
        ///   영구 고정되므로 한 번 틀리면 되돌릴 수 없다.
        /// </summary>
        public override string Name => "LJKS AdaptiveMold";

        public override Bitmap Icon
        {
            get
            {
                using (var s = typeof(AdaptiveMoldInfo).Assembly
                           .GetManifestResourceStream("AdaptiveMold.GH.icon24.png"))
                {
                    return s == null ? null : new Bitmap(s);
                }
            }
        }

        public override string Description =>
            "곡면 패널용 가변형 핀 몰드(다점프레스)의 액추에이터 높이 역산기.";

        public override Guid Id => new Guid("6f2a1c40-8d51-4a7e-9b3c-2e5f7a90d114");

        public override string AuthorName => "LJK STUDIO";

        public override string AuthorContact => "ljk@ljkstudio.com";
    }
}
