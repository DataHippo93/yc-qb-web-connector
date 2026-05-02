"""
Company-identity verification — defense against cross-schema contamination.

Problem this solves
-------------------
QBWC routes by USERNAME from the .qwc file. The username determines the
target schema (YCConnector_ADK -> adk_fragrance, YCConnector_NS -> natures_storehouse,
etc.). It does NOT verify which QB Desktop company file is actually open
when the .qwc app fires.

If the wrong file is open, QB happily returns that file's data, the connector
upserts it into the schema dictated by the username, and the wrong company's
records are silently merged into another company's schema.

Defense in this module
----------------------
1) Every QBWC session starts with a CompanyQueryRq probe BEFORE any data
   queries run.
2) The response is parsed for <CompanyName> and compared against the
   `expected_company_name` configured in companies.yaml for this company_id.
3) On mismatch:
     - if expected_company_name IS configured -> session is ABORTED, every
       data task is skipped, the mismatch is logged to qb_meta.company_identity_log
       with action_taken='abort', and the connector returns "" so QBWC closes
       the connection. NO DATA IS UPSERTED.
     - if expected_company_name is NULL -> 'observe_only' mode; the observation
       is recorded but the session continues. Use this for first-time setup,
       then promote the observed value to the YAML config.
4) The observation (whether it matched or not) is also written to
   qb_meta.companies.observed_company_name so operators can see at a glance
   what each .qwc app last connected to.
"""
from __future__ import annotations

from datetime import datetime, timezone

from supabase import Client

from src.qbxml.parsers import CompanyIdentity
from src.supabase.client import META_SCHEMA
from src.utils.logging import get_logger

logger = get_logger(__name__)


class CompanyIdentityChecker:
    """Compares QB-reported identity against expected configuration."""

    def __init__(self, client: Client) -> None:
        self._client = client

    # ---------------------------------------------------------------- file path

    @staticmethod
    def file_path_matches(observed_path: str | None, expected_substr: str | None) -> bool:
        """Case-insensitive substring match. None on either side -> True (skip)."""
        if not expected_substr:
            return True
        if not observed_path:
            return False
        return expected_substr.strip().lower() in observed_path.lower()

    # ------------------------------------------------------------- name match

    @staticmethod
    def name_matches(observed: str | None, expected: str | None) -> bool:
        """Case-insensitive trimmed equality. None expected -> True (observe-only)."""
        if not expected:
            return True
        if not observed:
            return False
        return observed.strip().lower() == expected.strip().lower()

    # ----------------------------------------------------- read expected vals
    # The database is the runtime source of truth. The YAML config is just
    # the bootstrap value — once you call /identity/{company_id}/lock-in,
    # the DB column wins. This means an operator can flip strict mode on
    # for a company WITHOUT a redeploy.

    def get_expected_name(self, company_id: str) -> str | None:
        try:
            rows = (
                self._client.schema(META_SCHEMA).table("companies")
                .select("expected_company_name")
                .eq("company_id", company_id).execute()
            ).data
            if rows and rows[0].get("expected_company_name"):
                return rows[0]["expected_company_name"]
        except Exception as e:
            logger.warning("identity_db_read_failed", company=company_id, error=str(e))
        return None

    def get_expected_file(self, company_id: str) -> str | None:
        try:
            rows = (
                self._client.schema(META_SCHEMA).table("companies")
                .select("expected_company_file")
                .eq("company_id", company_id).execute()
            ).data
            if rows and rows[0].get("expected_company_file"):
                return rows[0]["expected_company_file"]
        except Exception as e:
            logger.warning("identity_db_read_failed", company=company_id, error=str(e))
        return None

    # ------------------------------------------------------------- persistence

    def record_observation(
        self,
        company_id: str,
        observed_name: str | None,
        observed_file: str | None,
    ) -> None:
        """Stamp qb_meta.companies with the most recent observation."""
        try:
            self._client.schema(META_SCHEMA).table("companies").update({
                "observed_company_name": observed_name,
                "observed_company_file": observed_file,
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("company_id", company_id).execute()
        except Exception as e:
            logger.warning("identity_observation_save_failed", company=company_id, error=str(e))

    def log_check(
        self,
        company_id: str,
        ticket: str | None,
        expected_name: str | None,
        observed_name: str | None,
        observed_file: str | None,
        matched: bool,
        action_taken: str,
    ) -> None:
        """Append-only audit row in qb_meta.company_identity_log."""
        try:
            self._client.schema(META_SCHEMA).table("company_identity_log").insert({
                "company_id": company_id,
                "ticket": ticket,
                "expected_name": expected_name,
                "observed_name": observed_name,
                "observed_file": observed_file,
                "matched": matched,
                "action_taken": action_taken,
            }).execute()
        except Exception as e:
            logger.warning("identity_log_failed", company=company_id, error=str(e))

    # --------------------------------------------------------------- evaluate

    def evaluate(
        self,
        company_id: str,
        ticket: str | None,
        identity: CompanyIdentity,
        expected_company_name: str | None,
        observed_file_path: str | None = None,
        expected_file_substr: str | None = None,
    ) -> tuple[bool, str]:
        """
        Evaluate whether the session is allowed to proceed.

        Returns (allowed, action_taken):
            allowed=True  + 'allow'         -> identity matched (or strict mode off and observed)
            allowed=True  + 'observe_only'  -> no expected_company_name configured; logged for review
            allowed=False + 'abort'         -> mismatch with strict mode on; session must be killed
            allowed=False + 'qb_error'      -> CompanyQueryRq itself failed; abort defensively
        """
        observed_name = identity.company_name if identity.success else None

        # Persist the observation regardless of outcome so operators can see it.
        self.record_observation(company_id, observed_name, observed_file_path)

        if not identity.success:
            self.log_check(
                company_id, ticket, expected_company_name,
                observed_name, observed_file_path,
                matched=False, action_taken="abort",
            )
            logger.error(
                "company_identity_query_failed",
                company=company_id,
                ticket=ticket,
                status_code=identity.status_code,
                message=identity.status_message,
            )
            return False, "qb_error"

        name_ok = self.name_matches(observed_name, expected_company_name)
        file_ok = self.file_path_matches(observed_file_path, expected_file_substr)
        matched = name_ok and file_ok

        if expected_company_name is None:
            # Observe-only: nothing to fail against. Log as informational.
            self.log_check(
                company_id, ticket, expected_company_name,
                observed_name, observed_file_path,
                matched=matched, action_taken="observe_only",
            )
            logger.warning(
                "company_identity_observe_only",
                company=company_id,
                ticket=ticket,
                observed_name=observed_name,
                observed_file=observed_file_path,
                msg="No expected_company_name configured -- set qb_company_name in companies.yaml or call /identity/{cid}/lock-in to enable strict mode",
            )
            return True, "observe_only"

        if matched:
            self.log_check(
                company_id, ticket, expected_company_name,
                observed_name, observed_file_path,
                matched=True, action_taken="allow",
            )
            logger.info(
                "company_identity_ok",
                company=company_id,
                ticket=ticket,
                observed_name=observed_name,
            )
            return True, "allow"

        # MISMATCH with strict mode on -- fail closed.
        self.log_check(
            company_id, ticket, expected_company_name,
            observed_name, observed_file_path,
            matched=False, action_taken="abort",
        )
        logger.error(
            "company_identity_mismatch",
            company=company_id,
            ticket=ticket,
            expected_name=expected_company_name,
            observed_name=observed_name,
            expected_file=expected_file_substr,
            observed_file=observed_file_path,
            msg="ABORTING session to prevent cross-schema contamination",
        )
        return False, "abort"
