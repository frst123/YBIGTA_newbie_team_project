from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _csv(name: str, default: str) -> tuple[str, ...]:
    value = os.getenv(name, default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    data_backend: str
    csv_data_glob: str
    database_url: str | None
    review_table: str
    max_analysis_rows: int
    mcp_auth_token: str | None
    mcp_host: str
    mcp_port: int
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        backend = os.getenv("DATA_BACKEND", "csv").strip().lower()
        if backend not in {"csv", "rds"}:
            raise ValueError("DATA_BACKEND must be either 'csv' or 'rds'")

        return cls(
            data_backend=backend,
            csv_data_glob=os.getenv(
                "CSV_DATA_GLOB", "data/preprocessed_reviews_*.csv"
            ),
            database_url=os.getenv("DATABASE_URL") or None,
            review_table=os.getenv("REVIEW_TABLE", "preprocessed_reviews"),
            max_analysis_rows=max(
                100, min(int(os.getenv("MAX_ANALYSIS_ROWS", "5000")), 20_000)
            ),
            mcp_auth_token=os.getenv("MCP_AUTH_TOKEN") or None,
            mcp_host=os.getenv("MCP_HOST", "127.0.0.1"),
            mcp_port=int(os.getenv("MCP_PORT", "8000")),
            allowed_hosts=_csv(
                "MCP_ALLOWED_HOSTS",
                "localhost:*,127.0.0.1:*,[::1]:*,testserver",
            ),
            allowed_origins=_csv(
                "MCP_ALLOWED_ORIGINS",
                "http://localhost:*,http://127.0.0.1:*",
            ),
        )

    def resolve_data_glob(self) -> str:
        path = Path(self.csv_data_glob)
        return str(path if path.is_absolute() else PROJECT_ROOT / path)
