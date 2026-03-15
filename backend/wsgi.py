"""
Production WSGI entrypoint.
"""

from app import create_app
from app.config import Config


errors = Config.validate()
if errors:
    raise RuntimeError(
        "Invalid startup configuration:\n- " + "\n- ".join(errors)
    )


app = create_app()
