"""DocTune training notebook package.

Importing this package never imports torch / unsloth / transformers / trl; those are imported inside the
functions that need them (Unsloth must be imported before transformers, so import order matters).
"""

__version__ = "0.1.0"

from doctune_nb import api, env, ui  # noqa: E402  (light modules only)
from doctune_nb.api import DocTuneClient  # noqa: E402

__all__ = ["DocTuneClient", "__version__", "api", "env", "ui"]
