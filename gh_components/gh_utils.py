"""GH 메시지 헬퍼."""

try:
    import Grasshopper as gh

    GH_WARNING = gh.Kernel.GH_RuntimeMessageLevel.Warning
    GH_ERROR = gh.Kernel.GH_RuntimeMessageLevel.Error
    GH_REMARK = gh.Kernel.GH_RuntimeMessageLevel.Remark
except ImportError:
    GH_WARNING = GH_ERROR = GH_REMARK = None


def add_message(component, level, message):
    if component is not None and level is not None:
        component.AddRuntimeMessage(level, message)


def add_warning(component, message):
    add_message(component, GH_WARNING, message)


def add_error(component, message):
    add_message(component, GH_ERROR, message)


def add_remark(component, message):
    add_message(component, GH_REMARK, message)
