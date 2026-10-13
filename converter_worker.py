"""Runs inside the conversion child processes; kept apart from main.py so the
forkserver only has to preload vtracer, not FastAPI and the app."""
import traceback

import vtracer


def convert_in_child(conn, image_bytes, vtracer_options):
    try:
        conn.send(("ok", vtracer.convert_raw_image_to_svg(image_bytes, **vtracer_options)))
    except Exception as e:
        conn.send(("error", f"{e}\n{traceback.format_exc()}"))
    finally:
        conn.close()
