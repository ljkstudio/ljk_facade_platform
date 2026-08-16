using System;
using System.Diagnostics;
using System.Drawing;
using Grasshopper.Kernel;
using Rhino.Geometry;
using AdaptiveMold.Core;

namespace AdaptiveMold.GH
{
    /// <summary>
    /// 목표 곡면 → 핀 높이 역산 (Phase A~D).
    ///
    /// 이 클래스는 어댑터일 뿐이다 — 계산은 전부
    /// <see cref="MoldSolver"/> 안에 있고 여기서는 GH 타입으로 펴기만 한다.
    /// 계약(입력 정규화·min>=max 에러·compute=false 빈 결과·pin_tops 산식)을
    /// 여기로 끌어오면 골든 픽스처 대조가 닿지 않는 곳이 생긴다(설계 §3.2).
    ///
    /// 이름이 `AdaptiveMold Pins` 가 아니라 `AMv1 Pins` 인 이유: 기존 컴포넌트
    /// 7개가 전부 `AMv1 *` 이고 툴팁 레지스트리의 키도 그 형식이다.
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

        static Bitmap _icon;

        protected override Bitmap Icon
        {
            get
            {
                if (_icon != null) return _icon;
                using (var s = typeof(AMv1PinsComponent).Assembly
                           .GetManifestResourceStream("AdaptiveMold.GH.icon24.png"))
                {
                    // 없으면 null 을 돌려준다 — 아이콘 때문에 컴포넌트가
                    // 사라지게 두지 않는다. 빈 사각형이 낫다.
                    if (s == null) return null;
                    _icon = new Bitmap(s);
                }
                return _icon;
            }
        }

        public override GH_Exposure Exposure => GH_Exposure.primary;

        protected override void RegisterInputParams(GH_Component.GH_InputParamManager pManager)
        {
            pManager.AddBrepParameter("target_srf", "target_srf",
                ParamDocs.In("target_srf"), GH_ParamAccess.item);
            pManager.AddPlaneParameter("base_plane", "base_plane",
                ParamDocs.In("base_plane"), GH_ParamAccess.item, Plane.WorldXY);
            pManager.AddNumberParameter("width", "width",
                ParamDocs.In("width"), GH_ParamAccess.item, 1000.0);
            pManager.AddNumberParameter("length", "length",
                ParamDocs.In("length"), GH_ParamAccess.item, 1000.0);
            pManager.AddNumberParameter("spacing", "spacing",
                ParamDocs.In("spacing"), GH_ParamAccess.item, 200.0);
            pManager.AddNumberParameter("max_height", "max_height",
                ParamDocs.In("max_height"), GH_ParamAccess.item, 400.0);
            pManager.AddNumberParameter("min_height", "min_height",
                ParamDocs.In("min_height"), GH_ParamAccess.item, 0.0);
            pManager.AddBooleanParameter("compute", "compute",
                ParamDocs.In("compute"), GH_ParamAccess.item, false);

            // target_srf 를 선택으로 둔다. 필수로 두면 비었을 때 GH 가 자기
            // 영어 경고를 내고 SolveInstance 를 아예 안 부르는데, 그러면
            // MoldSolver 가 설계한 한국어 Error 도 compute=false Remark 도
            // 화면에 못 간다. 검증은 Core 가 한다.
            pManager[0].Optional = true;

            // GH 기본값을 utils.py 와 같은 수치로 둔다. 다르게 두면 GH 에서
            // 비운 경우와 파이썬에서 비운 경우가 갈린다(설계 §3.5).
        }

        protected override void RegisterOutputParams(GH_Component.GH_OutputParamManager pManager)
        {
            pManager.AddNumberParameter("pin_heights", "pin_heights",
                ParamDocs.Out("pin_heights"), GH_ParamAccess.list);
            pManager.AddPointParameter("pin_tops", "pin_tops",
                ParamDocs.Out("pin_tops"), GH_ParamAccess.list);
            pManager.AddPointParameter("grid_pts", "grid_pts",
                ParamDocs.Out("grid_pts"), GH_ParamAccess.list);
            pManager.AddBooleanParameter("clamp_flags", "clamp_flags",
                ParamDocs.Out("clamp_flags"), GH_ParamAccess.list);
            pManager.AddBooleanParameter("extension_flags", "extension_flags",
                ParamDocs.Out("extension_flags"), GH_ParamAccess.list);
            pManager.AddTextParameter("info", "info",
                ParamDocs.Out("info"), GH_ParamAccess.item);
            pManager.AddIntegerParameter("nx", "nx",
                ParamDocs.Out("nx"), GH_ParamAccess.item);
            pManager.AddIntegerParameter("ny", "ny",
                ParamDocs.Out("ny"), GH_ParamAccess.item);
        }

        protected override void SolveInstance(IGH_DataAccess DA)
        {
            Brep target = null;
            var basePlane = Plane.WorldXY;
            double width = 1000.0, length = 1000.0, spacing = 200.0;
            double maxHeight = 400.0, minHeight = 0.0;
            bool compute = false;

            // 반환값을 보지 않는다 — 선택 입력이 비면 false 를 돌려주는데
            // 그때 위의 기본값이 그대로 남아야 한다.
            DA.GetData(0, ref target);
            DA.GetData(1, ref basePlane);
            DA.GetData(2, ref width);
            DA.GetData(3, ref length);
            DA.GetData(4, ref spacing);
            DA.GetData(5, ref maxHeight);
            DA.GetData(6, ref minHeight);
            DA.GetData(7, ref compute);

            var sw = Stopwatch.StartNew();
            var r = MoldSolver.Run(target, basePlane, width, length, spacing,
                                   maxHeight, minHeight, compute);
            sw.Stop();

            // Core 는 메시지를 던지지 않고 모아서 돌려준다(설계 §3.1 규약 5).
            // 여기가 그 유일한 번역 지점이다.
            foreach (var m in r.Messages)
                AddRuntimeMessage(ToLevel(m.Level), m.Text);

            DA.SetDataList(0, r.PinHeights);
            DA.SetDataList(1, r.PinTops);
            DA.SetDataList(2, r.GridPts);
            DA.SetDataList(3, r.ClampFlags);
            DA.SetDataList(4, r.ExtensionFlags);
            DA.SetData(5, WithElapsed(r, sw.Elapsed.TotalMilliseconds));
            DA.SetData(6, r.Nx);
            DA.SetData(7, r.Ny);
        }

        static GH_RuntimeMessageLevel ToLevel(MoldMessageLevel level)
        {
            switch (level)
            {
                case MoldMessageLevel.Error: return GH_RuntimeMessageLevel.Error;
                case MoldMessageLevel.Warning: return GH_RuntimeMessageLevel.Warning;
                default: return GH_RuntimeMessageLevel.Remark;
            }
        }

        /// <summary>
        /// 완료조건 5의 뒷부분 — <c>info</c> 가 경과 ms 를 보고한다.
        ///
        /// 어댑터에서 붙인다. Core 에 넣으면 리포트 문자열이 실행마다
        /// 달라져 픽스처 대조에 쓸 수 없게 된다(지금도 info 는 대조 대상이
        /// 아니지만, 비결정 값을 Core 에 들이지 않는다는 선은 지킨다).
        /// 계산이 안 돈 경로(compute=false·검증 실패)에는 붙이지 않는다.
        /// </summary>
        static string WithElapsed(MoldResult r, double ms)
        {
            if (r.PinHeights.Count == 0) return r.Info;
            return r.Info + $"\nElapsed:     {ms:F0} ms";
        }
    }
}
