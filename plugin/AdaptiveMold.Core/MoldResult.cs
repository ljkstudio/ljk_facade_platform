using System.Collections.Generic;
using Rhino.Geometry;

namespace AdaptiveMold.Core
{
    /// <summary>
    /// 이름이 파이썬 쪽 <c>GH_RuntimeMessageLevel</c> 을 <c>str()</c> 한 값과
    /// 같아야 한다 — 픽스처의 <c>messages</c> 대조가 <c>ToString()</c> 을 쓴다.
    /// </summary>
    public enum MoldMessageLevel { Remark, Warning, Error }

    public class MoldMessage
    {
        public MoldMessageLevel Level;
        public string Text;

        public MoldMessage(MoldMessageLevel level, string text)
        {
            Level = level;
            Text = text;
        }
    }

    /// <summary>
    /// Phase A~D 의 출력 묶음.
    ///
    /// 파이썬 <c>AdaptiveMoldResult</c> 와 **1:1이 아니다** — 후자는
    /// positioned_srf·extended_srf·housings·rods·tops 를 더 들고 있다.
    /// 여기서는 **중간 Brep 을 붙들지 않는다**(설계 §3.4). 필요 없는 것을
    /// 들고 있을 이유가 없고, GH 가 캔버스에 유지하는 것과 겹치면 낭비다.
    ///
    /// 메시지는 **던지지 않고 모아서 돌려준다**(설계 §3.1 규약 5).
    /// Core 가 GH 를 모르므로 어댑터가 이것을 런타임 메시지로 번역한다.
    /// </summary>
    public class MoldResult
    {
        public List<double> PinHeights = new List<double>();
        public List<bool> ClampFlags = new List<bool>();
        public List<bool> ExtensionFlags = new List<bool>();
        public List<Point3d> GridPts = new List<Point3d>();
        public List<Point3d> PinTops = new List<Point3d>();

        /// <summary>핀별로 탄 폴백 가지 (<see cref="Projection"/> 의 Branch* 상수).</summary>
        public List<string> BranchTaken = new List<string>();

        /// <summary>Phase B·C 가 탄 가지. 파이썬 opt_branch/ext_branch 와 문자열까지 같다.</summary>
        public string OptBranch = string.Empty;
        public string ExtBranch = string.Empty;

        public int Nx;
        public int Ny;

        public string Info = string.Empty;

        public List<MoldMessage> Messages = new List<MoldMessage>();

        public void AddRemark(string text) => Messages.Add(new MoldMessage(MoldMessageLevel.Remark, text));
        public void AddWarning(string text) => Messages.Add(new MoldMessage(MoldMessageLevel.Warning, text));
        public void AddError(string text) => Messages.Add(new MoldMessage(MoldMessageLevel.Error, text));
    }
}
