"""Export Pydantic model JSON schemas to a single JSON file for the frontend.

Usage:
    cd backend && uv run python scripts/export_schemas.py

Outputs:
    frontend/src/schemas/api-contracts.json
"""

import inspect
import json
import sys
from pathlib import Path

# Ensure the backend package is importable when running from the backend directory
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from pydantic import BaseModel  # noqa: E402

from app.models import project as project_module  # noqa: E402
from app.models import responses as responses_module  # noqa: E402


def discover_models(module):
    """Return a dict of {ClassName: cls} for all BaseModel subclasses in a module."""
    models = {}
    for name, obj in inspect.getmembers(module):
        if (
            inspect.isclass(obj)
            and issubclass(obj, BaseModel)
            and obj is not BaseModel
            and obj.__module__ == module.__name__
        ):
            models[name] = obj
    return models


def main():
    # Discover models from both modules
    response_models = discover_models(responses_module)
    project_models = discover_models(project_module)

    all_models = {}
    all_models.update(response_models)
    all_models.update(project_models)

    # Build schema dict keyed by model name
    schemas = {}
    for name in sorted(all_models.keys()):
        cls = all_models[name]
        schemas[name] = cls.model_json_schema()

    # Write to frontend/src/schemas/api-contracts.json
    output_dir = backend_dir.parent / "frontend" / "src" / "schemas"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "api-contracts.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schemas, f, indent=2, sort_keys=True)
        f.write("\n")

    # Print summary
    print(f"Exported {len(schemas)} schemas to {output_path}")
    print(f"  - {len(response_models)} from responses.py")
    print(f"  - {len(project_models)} from project.py")
    print()
    print("Models:")
    for name in sorted(schemas.keys()):
        print(f"  {name}")


if __name__ == "__main__":
    main()
