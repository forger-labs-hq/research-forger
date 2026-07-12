"""Persistence for approved experiment contracts.

Deliberately no update or delete functions: an approved contract is
immutable (spec §12). Changing the yaml requires re-approval, which inserts
the next contract_version.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from researchforge.domain.contract import ExperimentContract


def insert_contract(
    conn: sqlite3.Connection, project_id: str, contract: ExperimentContract
) -> None:
    with conn:
        conn.execute(
            """
            INSERT INTO contracts
                (contract_id, project_id, contract_version, source_sha256,
                 baseline_commit, approved_at, record, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contract.contract_id,
                project_id,
                contract.contract_version,
                contract.source_sha256,
                contract.baseline_commit,
                contract.approved_at.isoformat(),
                contract.model_dump_json(),
                datetime.now(UTC).isoformat(),
            ),
        )


def get_active_contract(conn: sqlite3.Connection) -> ExperimentContract | None:
    row = conn.execute(
        "SELECT record FROM contracts ORDER BY contract_version DESC LIMIT 1"
    ).fetchone()
    return ExperimentContract.model_validate_json(row["record"]) if row is not None else None


def list_contracts(conn: sqlite3.Connection) -> list[ExperimentContract]:
    rows = conn.execute("SELECT record FROM contracts ORDER BY contract_version").fetchall()
    return [ExperimentContract.model_validate_json(row["record"]) for row in rows]


def next_contract_version(conn: sqlite3.Connection, project_id: str) -> int:
    row = conn.execute(
        "SELECT MAX(contract_version) AS v FROM contracts WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    return int(row["v"] or 0) + 1
