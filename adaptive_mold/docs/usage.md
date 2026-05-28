# 사용법

## 기본 사용 방법

### 1. Grasshopper 정의 설정

1. Grasshopper에서 새 캔버스를 엽니다.
2. **GhPython Script** 컴포넌트를 배치합니다.
3. 컴포넌트를 더블클릭하여 코드 편집기를 열고 아래 코드를 입력합니다:

```python
import sys
sys.path.insert(0, r"C:\path\to\adaptive_mold\src")
from adaptive_mold_v1 import ghpython_run

(positioned_srf, extended_srf, housings, rods, tops,
 pin_heights, pin_tops, grid_pts, clamp_flags,
 extension_flags, info) = ghpython_run(
    target_srf, base_plane, width, length, spacing,
    max_height, min_height, housing_model, rod_model,
    top_model, rod_base_length, compute, ghenv.Component)
```

### 2. 입력 파라미터 연결

- **target_srf**: Surface/Brep 파라미터에 목표 곡면 연결
- **base_plane**: Plane 파라미터 (기본 WorldXY)
- **width / length**: Number Slider (mm 단위, 기본 1000)
- **spacing**: Number Slider (mm, 기본 200)
- **max_height / min_height**: stroke 제약 (기본 400 / 0)
- **housing_model / rod_model / top_model**: Brep 파라미터에 3D 모델 연결
- **rod_base_length**: rod 모델의 원본 길이 (mm)
- **compute**: Boolean Toggle

### 3. 3D 모델 준비

세 모델 모두 다음 규약을 따라야 합니다:
- **원점(0,0,0)**에 배치
- **+Z 방향**으로 모델링
- housing 높이는 bounding box에서 자동 계산됨
- rod는 `rod_base_length` 기준으로 Z 스케일 적용

### 4. 출력 사용

- **positioned_srf**: 최적화된 곡면 (시각 확인)
- **extended_srf**: 확장된 곡면 (확장 영역 확인)
- **housings / rods / tops**: 3D 모델 배열 시각화
- **info**: Panel에 연결하여 통계 확인

## 팁

- **compute 토글**: 파라미터 조정 중에는 False로 두어 재계산을 방지하세요.
- **Surface Optimization**: 기울어진 곡면은 자동으로 최적 각도로 회전·이동됩니다.
- **확장 fallback**: Surface.Extend 실패 시 tangent plane으로 자동 외삽합니다.
- **clamp_flags**: True인 핀은 stroke 한계에 도달했음을 의미합니다.
- **extension_flags**: True인 핀은 원본 곡면 외부(확장 영역)에 있음을 의미합니다.
