using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;

namespace AdaptiveMold.GH
{
    /// <summary>
    /// 임베드된 <c>docs/params.ko.json</c> 에서 <c>AMv1 Pins</c> 의 툴팁을 읽는다.
    ///
    /// 없는 이름에 예외를 던지지 않는다. 던지면 정적 생성자나 파라미터
    /// 등록에서 터지고, Grasshopper 는 그런 컴포넌트를 아무 진단 없이
    /// 팔레트에서 뺀다 — J-015 TRAP-03 에서 이미 한 번 당한 실패 방식이다.
    /// 대신 눈에 띄는 문자열을 돌려주고, 그것을 자동검사 1·2 가 잡는다.
    /// 사라지는 것보다 이상한 툴팁이 낫다.
    /// </summary>
    public static class ParamDocs
    {
        public const string Component = "AMv1 Pins";
        public const string MissingPrefix = "[설명 없음]";

        const string ResourceName = "AdaptiveMold.GH.params.ko.json";

        static readonly Dictionary<string, string> _inputs = new Dictionary<string, string>();
        static readonly Dictionary<string, string> _outputs = new Dictionary<string, string>();
        static readonly string _loadError;

        static ParamDocs()
        {
            try
            {
                var asm = typeof(ParamDocs).Assembly;
                using (var s = asm.GetManifestResourceStream(ResourceName))
                {
                    if (s == null)
                    {
                        _loadError = $"임베드 리소스 {ResourceName} 이 없다";
                        return;
                    }
                    using (var doc = JsonDocument.Parse(s))
                    {
                        if (!doc.RootElement.TryGetProperty(Component, out var comp))
                        {
                            _loadError = $"params.ko.json 에 \"{Component}\" 절이 없다";
                            return;
                        }
                        Fill(comp, "inputs", _inputs);
                        Fill(comp, "outputs", _outputs);
                    }
                }
            }
            catch (Exception e)
            {
                _loadError = e.Message;
            }
        }

        static void Fill(JsonElement comp, string key, Dictionary<string, string> into)
        {
            if (!comp.TryGetProperty(key, out var section)) return;
            foreach (var p in section.EnumerateObject())
                into[p.Name] = p.Value.GetString();
        }

        public static IReadOnlyDictionary<string, string> Inputs => _inputs;
        public static IReadOnlyDictionary<string, string> Outputs => _outputs;

        public static string In(string name) => Lookup(_inputs, "inputs", name);
        public static string Out(string name) => Lookup(_outputs, "outputs", name);

        static string Lookup(Dictionary<string, string> d, string kind, string name)
        {
            if (d.TryGetValue(name, out var v) && !string.IsNullOrWhiteSpace(v))
                return v;

            return $"{MissingPrefix} params.ko.json 의 \"{Component}\".{kind} 에 "
                 + $"\"{name}\" 이 없다."
                 + (_loadError == null ? "" : $" (로드 오류: {_loadError})");
        }
    }
}
