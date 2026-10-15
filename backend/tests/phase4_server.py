"""Explicit test-only provider for disposable Docker verification, never production startup."""

import os

from app.config import Settings
from app.main import create_app


class FixtureProvider:
    async def dashboard(self, question, datasets):
        d = datasets[0]
        return {
            "cards": [
                {
                    "title": "TEST FIXTURE: Revenue",
                    "plan": {
                        "action": "query",
                        "dataset_ids": [d["id"]],
                        "sql": f"SELECT SUM(c8) AS revenue FROM {d['table']}",
                    },
                },
                {
                    "title": "TEST FIXTURE: Regional revenue",
                    "plan": {
                        "action": "query",
                        "dataset_ids": [d["id"]],
                        "sql": f"SELECT c5 AS region, SUM(c8) AS revenue FROM {d['table']} GROUP BY c5 ORDER BY c5",
                        "chart": {
                            "type": "bar",
                            "x": "region",
                            "y": "revenue",
                            "title": "Regional revenue",
                            "x_label": "Region",
                            "y_label": "USD",
                        },
                    },
                },
            ]
        }


def fixture_app():
    if os.environ.get("DBO_ENVIRONMENT") != "test":
        raise RuntimeError("Fixture requires explicit test environment")
    return create_app(Settings(), FixtureProvider())
