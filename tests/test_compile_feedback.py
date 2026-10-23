from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from molt.application import MoltService
from molt.config import MoltConfig
from molt.core import MoltError, load_json


ROOT = Path(__file__).resolve().parents[1]
EXPENSE_RECIPE = load_json(ROOT / "examples" / "recipes" / "expense-v1.json")
ORDERS_RECIPE = load_json(ROOT / "examples" / "recipes" / "orders-v1.json")


class CompileFeedbackTests(unittest.TestCase):
    def service(self, directory: str, *, retries: int = 2) -> MoltService:
        return MoltService(
            MoltConfig(
                workspace=Path(directory),
                ollama_model="mock-model",
                ollama_max_retries=retries,
                sentry_dsn="",
            )
        )

    def expense_input(self, service: MoltService, *, secret: str | None = None) -> Path:
        path = service.config.input_dir / "expense.csv"
        if secret is None:
            shutil.copy2(ROOT / "examples" / "input" / "golden.csv", path)
        else:
            path.write_text(
                "transaction_id,date,merchant,amount,category,notes\n"
                f"t-secret,10/01/2026,{secret},1.00,books,ordinary note\n",
                encoding="utf-8",
            )
        return path

    def orders_input(self, service: MoltService) -> Path:
        path = service.config.input_dir / "orders.csv"
        shutil.copy2(ROOT / "examples" / "orders_input.csv", path)
        return path

    def wrong_expense_recipe(self) -> dict:
        recipe = copy.deepcopy(EXPENSE_RECIPE)
        recipe["operations"] = [operation for operation in recipe["operations"] if operation["type"] != "trim"]
        return recipe

    def provider(self, responses: list[object], calls: list[dict]) -> object:
        def generate(*args: object, **kwargs: object) -> tuple[dict, dict]:
            calls.append({"args": args, "kwargs": kwargs})
            response = responses.pop(0)
            if isinstance(response, BaseException):
                raise response
            recipe, prompt_tokens, response_tokens = response
            return recipe, {
                "provider": "ollama",
                "model": "mock-model",
                "llm_calls": 1,
                "prompt_tokens": prompt_tokens,
                "response_tokens": response_tokens,
            }

        return generate

    def assert_no_secret(self, value: object, secret: str) -> None:
        self.assertNotIn(secret, json.dumps(value, sort_keys=True))

    def test_wrong_then_good_candidate_is_verified_with_safe_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory, retries=2)
            source = self.expense_input(service)
            automation = service.create_automation("Expenses", "Normalize expense exports")
            profile = service.profile(source)
            wrong = self.wrong_expense_recipe()
            calls: list[dict] = []
            responses = [(wrong, 10, 4), (copy.deepcopy(EXPENSE_RECIPE), 20, 8)]

            with patch("molt.application.generate_recipe", side_effect=self.provider(responses, calls)):
                version = service.generate_candidate(automation["id"], "Normalize expenses", profile, model="mock-model")

            self.assertEqual(version["status"], "AWAITING_APPROVAL")
            self.assertEqual(version["verification"]["status"], "PASS")
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[1]["kwargs"]["previous_recipe"], wrong)
            feedback = calls[1]["kwargs"]["feedback"]
            self.assertEqual(feedback["kind"], "verification_feedback")
            self.assertTrue(feedback["failures"])
            self.assertTrue(all(item["code"] for item in feedback["failures"]))
            self.assert_no_secret(feedback, "Coffee Shop")
            self.assert_no_secret(feedback, str(source))
            self.assertEqual(version["provider_metadata"]["attempts"], 2)
            self.assertEqual(version["provider_metadata"]["llm_calls"], 2)
            self.assertEqual(version["provider_metadata"]["prompt_tokens"], 30)
            self.assertEqual(version["provider_metadata"]["response_tokens"], 12)

            automation_after = service.get_automation(automation["id"])
            self.assertEqual(len(automation_after["versions"]), 2)
            self.assertEqual(automation_after["versions"][1]["status"], "REJECTED")
            self.assertEqual(automation_after["versions"][0]["status"], "AWAITING_APPROVAL")
            self.assertEqual(automation_after["candidate"]["id"], version["id"])

    def test_generation_errors_and_rejected_candidates_share_one_global_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory, retries=2)
            source = self.expense_input(service)
            automation = service.create_automation("Expenses", "Normalize expense exports")
            profile = service.profile(source)
            wrong = self.wrong_expense_recipe()
            calls: list[dict] = []
            responses = [
                MoltError("FIRST_MODEL_ERROR", "first provider failure"),
                (wrong, 11, 3),
                (wrong, 13, 5),
                (copy.deepcopy(EXPENSE_RECIPE), 99, 99),
            ]

            with patch("molt.application.generate_recipe", side_effect=self.provider(responses, calls)):
                version = service.generate_candidate(automation["id"], "Normalize expenses", profile, model="mock-model")

            self.assertEqual(version["status"], "REJECTED")
            self.assertEqual(version["verification"]["status"], "FAIL")
            self.assertEqual(len(calls), 3)
            self.assertEqual(version["provider_metadata"]["attempts"], 3)
            self.assertEqual(version["provider_metadata"]["llm_calls"], 3)
            self.assertEqual(version["provider_metadata"]["prompt_tokens"], 24)
            self.assertEqual(version["provider_metadata"]["response_tokens"], 8)
            self.assertEqual(calls[1]["kwargs"]["feedback"]["kind"], "generation_error")
            self.assertEqual(calls[2]["kwargs"]["previous_recipe"], wrong)

            automation_after = service.get_automation(automation["id"])
            self.assertEqual(len(automation_after["versions"]), 2)
            self.assertTrue(all(item["status"] == "REJECTED" for item in automation_after["versions"]))

    def test_last_generation_error_returns_prior_rejected_version_with_cumulative_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory, retries=2)
            source = self.expense_input(service)
            automation = service.create_automation("Expenses", "Normalize expense exports")
            wrong = self.wrong_expense_recipe()
            calls: list[dict] = []
            responses = [
                (wrong, 9, 4),
                MoltError("MIDDLE_MODEL_ERROR", "middle provider failure"),
                MoltError("LAST_MODEL_ERROR", "last provider failure"),
            ]

            with patch("molt.application.generate_recipe", side_effect=self.provider(responses, calls)):
                final = service.generate_candidate(automation["id"], "Normalize expenses", service.profile(source), model="mock-model")

            self.assertEqual(final["status"], "REJECTED")
            self.assertEqual(final["verification"]["status"], "FAIL")
            self.assertEqual(final["provider_metadata"]["attempts"], 3)
            self.assertEqual(final["provider_metadata"]["llm_calls"], 3)
            self.assertEqual(final["provider_metadata"]["prompt_tokens"], 9)
            self.assertEqual(final["provider_metadata"]["response_tokens"], 4)
            self.assertEqual(len(service.get_automation(automation["id"])["versions"]), 1)

    def test_all_model_candidates_fail_and_active_version_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory, retries=1)
            source = self.expense_input(service)
            automation = service.create_automation("Expenses", "Normalize expense exports")
            initial = service.generate_candidate(
                automation["id"],
                "Normalize expenses",
                service.profile(source),
                recipe_file=str(ROOT / "examples" / "recipes" / "expense-v1.json"),
            )
            service.verify_version(initial["id"])
            active = service.approve_version(initial["id"])
            wrong = self.wrong_expense_recipe()
            calls: list[dict] = []
            responses = [(wrong, 2, 1), (wrong, 3, 1)]

            with patch("molt.application.generate_recipe", side_effect=self.provider(responses, calls)):
                final = service.generate_candidate(automation["id"], "Normalize expenses", service.profile(source), model="mock-model")

            self.assertEqual(final["status"], "REJECTED")
            self.assertEqual(final["verification"]["status"], "FAIL")
            self.assertEqual(final["provider_metadata"]["llm_calls"], 2)
            self.assertEqual(service.get_automation(automation["id"])["active_version"]["id"], active["id"])
            self.assertEqual(service.get_automation(automation["id"])["active_version"]["status"], "ACTIVE")
            self.assertEqual(len(service.get_automation(automation["id"])["versions"]), 3)

    def test_initial_model_errors_only_raise_last_error_after_budget(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory, retries=2)
            source = self.expense_input(service)
            automation = service.create_automation("Expenses", "Normalize expense exports")
            calls: list[dict] = []
            last_error = MoltError("LAST_MODEL_ERROR", "last provider failure")
            responses = [
                MoltError("FIRST_MODEL_ERROR", "first provider failure"),
                MoltError("SECOND_MODEL_ERROR", "second provider failure"),
                last_error,
            ]

            with patch("molt.application.generate_recipe", side_effect=self.provider(responses, calls)):
                with self.assertRaises(MoltError) as context:
                    service.generate_candidate(automation["id"], "Normalize expenses", service.profile(source), model="mock-model")

            self.assertIs(context.exception, last_error)
            self.assertEqual(len(calls), 3)
            self.assertEqual(service.get_automation(automation["id"])["versions"], [])

    def test_fixture_recipe_path_does_not_call_model_or_verify(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory)
            source = self.expense_input(service)
            automation = service.create_automation("Expenses", "Normalize expense exports")

            with patch("molt.application.generate_recipe") as generate:
                version = service.generate_candidate(
                    automation["id"],
                    "Normalize expenses",
                    service.profile(source),
                    recipe_file=str(ROOT / "examples" / "recipes" / "expense-v1.json"),
                )

            generate.assert_not_called()
            self.assertEqual(version["status"], "VERIFYING")
            self.assertNotIn("verification", version)
            self.assertEqual(version["provider_metadata"]["llm_calls"], 0)

    def test_verification_is_persisted_and_read_back_from_version_and_automation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory, retries=0)
            source = self.expense_input(service)
            automation = service.create_automation("Expenses", "Normalize expense exports")
            calls: list[dict] = []
            responses = [(copy.deepcopy(EXPENSE_RECIPE), 7, 6)]

            with patch("molt.application.generate_recipe", side_effect=self.provider(responses, calls)):
                returned = service.generate_candidate(automation["id"], "Normalize expenses", service.profile(source), model="mock-model")

            reread = service.get_version(returned["id"])
            automation_reread = service.get_automation(automation["id"])
            persisted = next(item for item in automation_reread["versions"] if item["id"] == returned["id"])
            self.assertEqual(returned["status"], "AWAITING_APPROVAL")
            self.assertEqual(returned["verification"]["verification_id"], reread["verification"]["verification_id"])
            self.assertEqual(reread["verification"]["status"], "PASS")
            self.assertEqual(persisted["verification"]["status"], "PASS")
            self.assertEqual(automation_reread["candidate"]["id"], returned["id"])
            self.assertIsNone(automation_reread["active_version"])

    def test_model_style_recipe_is_normalized_before_verification_and_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory, retries=0)
            source = self.expense_input(service)
            automation = service.create_automation("Expenses", "Normalize expense exports")
            recipe = copy.deepcopy(EXPENSE_RECIPE)
            mapping = recipe["operations"][3]["mapping"]
            for canonical in ("Food", "Transport", "Books"):
                mapping.pop(canonical)
            with patch("molt.application.generate_recipe", return_value=(recipe, {
                "provider": "ollama", "model": "mock-model", "llm_calls": 1,
                "prompt_tokens": 4, "response_tokens": 2,
            })):
                version = service.generate_candidate(automation["id"], "Normalize expenses", service.profile(source), model="mock-model")

            self.assertEqual(version["status"], "AWAITING_APPROVAL")
            stored = service.get_version(version["id"])
            self.assertTrue(stored["recipe"]["operations"][3]["keep_known"])
            self.assertEqual(stored["verification"]["status"], "PASS")

    def test_profile_family_pins_legacy_fixtures_before_model_recipe_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory, retries=1)
            source = self.expense_input(service)
            automation = service.create_automation("Expenses", "Normalize expense exports")
            calls: list[dict] = []
            responses = [(copy.deepcopy(ORDERS_RECIPE), 4, 2), (copy.deepcopy(EXPENSE_RECIPE), 5, 3)]

            with patch("molt.application.generate_recipe", side_effect=self.provider(responses, calls)):
                final = service.generate_candidate(automation["id"], "Normalize expenses", service.profile(source), model="mock-model")

            self.assertEqual(final["status"], "AWAITING_APPROVAL")
            self.assertEqual(final["verification"]["status"], "PASS")
            versions = service.get_automation(automation["id"])["versions"]
            self.assertEqual(len(versions), 2)
            self.assertEqual(versions[1]["status"], "REJECTED")
            self.assertTrue(any(item["check"] == "REQUIRED_COLUMN_MISSING" for item in calls[1]["kwargs"]["feedback"]["failures"]))

    def test_orders_profile_cannot_be_switched_to_expense_fixtures_by_model_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory, retries=1)
            source = self.orders_input(service)
            automation = service.create_automation("Orders", "Normalize order exports")
            calls: list[dict] = []
            responses = [(copy.deepcopy(EXPENSE_RECIPE), 4, 2), (copy.deepcopy(ORDERS_RECIPE), 5, 3)]

            with patch("molt.application.generate_recipe", side_effect=self.provider(responses, calls)):
                final = service.generate_candidate(automation["id"], "Normalize orders", service.profile(source), model="mock-model")

            self.assertEqual(final["status"], "AWAITING_APPROVAL")
            self.assertEqual(final["verification"]["status"], "PASS")
            versions = service.get_automation(automation["id"])["versions"]
            self.assertEqual(len(versions), 2)
            self.assertEqual(versions[1]["status"], "REJECTED")
            self.assertTrue(any(item["check"] == "REQUIRED_COLUMN_MISSING" for item in calls[1]["kwargs"]["feedback"]["failures"]))

    def test_user_fixture_override_is_used_for_model_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory, retries=0)
            source = self.expense_input(service)
            custom_expected = service.config.input_dir / "custom-expected.csv"
            custom_expected.write_text(
                (ROOT / "examples" / "expected" / "golden.csv").read_text(encoding="utf-8").replace(
                    "team breakfast", "user-authored expectation"
                ),
                encoding="utf-8",
            )
            automation = service.create_automation("Expenses", "Normalize expense exports")
            service.add_fixture(automation["id"], source, custom_expected, name="user override")
            calls: list[dict] = []
            responses = [(copy.deepcopy(EXPENSE_RECIPE), 7, 6)]

            with patch("molt.application.generate_recipe", side_effect=self.provider(responses, calls)):
                version = service.generate_candidate(automation["id"], "Normalize expenses", service.profile(source), model="mock-model")

            self.assertEqual(version["status"], "REJECTED")
            self.assertEqual(version["verification"]["status"], "FAIL")
            self.assertTrue(any(item["check"] == "golden_output" for item in version["verification"]["results"]))
            self.assert_no_secret(calls[0]["kwargs"].get("feedback"), "user-authored expectation")

    def test_model_repair_retries_regression_failure_and_preserves_active_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = self.service(directory, retries=1)
            source = self.orders_input(service)
            drift = service.config.input_dir / "orders-drift.csv"
            shutil.copy2(ROOT / "examples" / "orders_drift_unknown_status.csv", drift)
            automation = service.create_automation("Orders repair", "Normalize order exports")
            initial = service.generate_candidate(
                automation["id"],
                "Normalize orders",
                service.profile(source),
                recipe_file=str(ROOT / "examples" / "recipes" / "orders-v1.json"),
            )
            self.assertEqual(service.verify_version(initial["id"])["status"], "PASS")
            active = service.approve_version(initial["id"])
            blocked = service.run(automation["id"], drift)
            bad = load_json(ROOT / "examples" / "recipes" / "orders-bad-repair.json")
            good = load_json(ROOT / "examples" / "recipes" / "orders-good-repair.json")
            calls: list[dict] = []
            responses = [(bad, 10, 4), (good, 20, 8)]

            with patch("molt.application.generate_recipe", side_effect=self.provider(responses, calls)):
                proposal = service.propose_repair(automation["id"], blocked["id"], model="mock-model")

            self.assertEqual(proposal["candidate"]["status"], "AWAITING_APPROVAL")
            self.assertEqual(proposal["candidate"]["verification"]["status"], "PASS")
            self.assertEqual(proposal["candidate"]["provider_metadata"]["llm_calls"], 2)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]["kwargs"]["active_recipe"], active["recipe"])
            self.assertEqual(calls[1]["kwargs"]["previous_recipe"], bad)
            self.assertEqual(calls[1]["kwargs"]["feedback"]["kind"], "verification_feedback")
            self.assertEqual(service.get_automation(automation["id"])["active_version"]["id"], active["id"])
            versions = service.get_automation(automation["id"])["versions"]
            self.assertEqual([version["status"] for version in versions[:2]], ["AWAITING_APPROVAL", "REJECTED"])
