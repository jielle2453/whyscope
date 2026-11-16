"""Small HailoRT InferModel wrappers shared by vision_bench.py and share_bench.py (HailoRT venv only)."""
import time

import numpy as np

MODELS = r"C:\Users\Jie\Desktop\whyscope\whyscope\models\hailo"


def make_vdevice():
    from hailo_platform import VDevice
    p = VDevice.create_params()
    p.group_id = "SHARED"
    return VDevice(p)


class Infer:
    """One single-input HEF run through the InferModel API (outputs as FLOAT32)."""

    def __init__(self, vd, hef, timeout_ms=10000):
        from hailo_platform import FormatType
        self.timeout = timeout_ms
        t = time.perf_counter()
        self.m = vd.create_infer_model(hef)
        for o in self.m.outputs:
            o.set_format_type(FormatType.FLOAT32)
        self.inp = self.m.input()
        self.out_names = list(self.m.output_names)
        self.cm_ctx = self.m.configure()
        self.cm = self.cm_ctx.__enter__()
        self.load_sec = time.perf_counter() - t

    def info(self):
        return {"input": (self.inp.name, list(self.inp.shape)),
                "outputs": [(o.name, list(o.shape)) for o in self.m.outputs]}

    def run(self, arr_u8):
        arr = np.ascontiguousarray(arr_u8, dtype=np.uint8)
        outs = {}
        for o in self.m.outputs:
            if "nms" in o.name.lower() or len(o.shape) <= 1:
                outs[o.name] = np.empty(o.shape, dtype=np.float32)
            else:
                outs[o.name] = np.empty(o.shape, dtype=np.float32)
        b = self.cm.create_bindings(input_buffers={self.inp.name: arr}, output_buffers=outs)
        self.cm.run([b], self.timeout)
        res = {n: b.output(n).get_buffer() for n in self.out_names}
        return res

    def close(self):
        try:
            self.cm_ctx.__exit__(None, None, None)
        except Exception:
            pass
        self.cm = self.m = None
