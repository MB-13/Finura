"""Print the OpenAPI schema without running a server: `uv run python -m doctune.openapi`."""

import json

from doctune.main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), indent=2))
