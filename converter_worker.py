"""Runs inside the conversion child processes; kept apart from main.py so the
forkserver only has to preload vtracer, not FastAPI and the app."""
import traceback

import vtracer


def convert_in_child(conn, image_bytes, vtracer_options):
    try:
        conn.send(("ok", vtracer.convert_raw_image_to_svg(image_bytes, **vtracer_options)))
    except BaseException as e:
        # vtracer's Rust panics (blank or fully transparent images, coordinate overflow)
        # surface as pyo3 PanicException, which derives from BaseException. Missing them
        # used to kill the child silently and the caller saw an empty "Conversion failed".
        if type(e).__name__ == "PanicException":
            conn.send(("unprocessable", str(e)))
        else:
            conn.send(("error", f"{e}\n{traceback.format_exc()}"))
    finally:
        conn.close()
