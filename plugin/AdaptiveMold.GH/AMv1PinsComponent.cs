using System;
using System.Drawing;
using Grasshopper.Kernel;

namespace AdaptiveMold.GH
{
    /// <summary>
    /// 목표 곡면 → 핀 높이 역산 (Phase A~D).
    ///
    /// M2a 현재는 **껍데기**다 — 로드·툴팁·중단점을 확인하기 위한 최소 형태이고,
    /// 입력 8 / 출력 8 과 실제 계산은 M3 에서 채운다.
    ///
    /// 이름이 `AdaptiveMold Pins` 가 아니라 `AMv1 Pins` 인 이유: 기존 컴포넌트
    /// 7개가 전부 `AMv1 *` 이고 툴팁 레지스트리(param_docs)의 키도 그 형식이다.
    /// </summary>
    public class AMv1PinsComponent : GH_Component
    {
        public AMv1PinsComponent()
            : base("AMv1 Pins", "AMv1Pins",
                   "목표 곡면을 재현하는 핀 몰드의 액추에이터 높이를 역산한다.\n"
                 + "곡면을 행정 범위 안으로 정렬(B) -> 몰드 전체로 확장(C) -> "
                 + "격자점마다 레이캐스트(D).\n"
                 + "단위 mm. 핀 순서는 idx = j * nx + i (X 가 먼저 변한다).\n"
                 + "clamp_flags / extension_flags 가 켜진 핀은 "
                 + "\"계산은 됐지만 믿을 수 없다\"는 뜻이다.",
                   "LJKS", "AMv1")
        {
        }

        public override Guid ComponentGuid =>
            new Guid("b4e07d92-1f38-4c6a-8e51-3a9c6d2b7f40");

        protected override Bitmap Icon => null;   // M3

        public override GH_Exposure Exposure => GH_Exposure.primary;

        protected override void RegisterInputParams(GH_Component.GH_InputParamManager pManager)
        {
            // M3 에서 8개로 채운다. 지금은 로드 확인용 하나.
            pManager.AddBooleanParameter("compute", "compute",
                "계산 실행 여부. 기본 false.\n"
                + "무거운 계산이 슬라이더를 만질 때마다 돌지 않게 한다.\n"
                + "Boolean Toggle 을 물려 True 로 바꿀 것.",
                GH_ParamAccess.item, false);
        }

        protected override void RegisterOutputParams(GH_Component.GH_OutputParamManager pManager)
        {
            pManager.AddTextParameter("info", "info",
                "통계 리포트. Panel 에 물릴 것.\n"
                + "먼저 볼 줄은 Coverage 다 — 곡면 위 핀이 0 이면 "
                + "나머지 숫자는 의미가 없다.",
                GH_ParamAccess.item);
        }

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            bool compute = false;
            if (!DA.GetData(0, ref compute)) return;

            // 이 세 줄이 로드 확인 · 런타임 경로 확인 · 중단점 대상을 한꺼번에
            // 해결한다 (J-001 PROCEDURE-01). ".NET 8.x" 로 보고하면 netcore,
            // ".NET Framework 4.8.x" 면 netfx 로 로드된 것이다.
            var runtime = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription;
            var rhino = Rhino.RhinoApp.Version.ToString();
            var core = AdaptiveMold.Core.CoreInfo.Name;

            DA.SetData(0, $"OK | {runtime} | Rhino {rhino} | {core} | compute={compute}");
        }
    }
}
