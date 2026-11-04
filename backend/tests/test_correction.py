"""
Jev vendor-name correction tests. MongoDB and the Jev API are replaced with fakes.

Run from backend/:  python -m unittest discover -s tests
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from pydantic import SecretStr  # noqa: E402
from typesafe_sdk import TypeSafeAPITimeoutError  # noqa: E402

import correction  # noqa: E402
import main  # noqa: E402

VENDORS = "OmOrgVendorDetails"
ORG_ID = "org-1"

VENDOR_DOCS = [
    {"vendorCode": "V001", "vendorDetails": {"basicDetails": {"companyName": "Acme Industries Pvt Ltd"}}},
    {"vendorCode": "V002", "vendorDetails": {"basicDetails": {"companyName": "Apex Steel Traders"}}},
]


def _settings(**overrides):
    values = {
        "typesafe_api_key": SecretStr("test-key"),
        "typesafe_model": "jev-latest",
        "correction_timeout_seconds": 5.0,
        "correction_min_confidence": 0.6,
        "search_result_limit": 50,
        "collection_name": VENDORS,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeCollection:
    """Substring match for normal queries; fuzzy queries return every document as a candidate."""

    def __init__(self, docs, error=None):
        self.docs = docs
        self.error = error
        self.pipelines = []

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        if self.error:
            raise self.error
        should = pipeline[0]["$search"]["compound"]["should"]
        if "fuzzy" in should[0]["autocomplete"]:
            return iter(self.docs)
        q = should[0]["autocomplete"]["query"].lower()
        paths = [s["autocomplete"]["path"].split(".") for s in should]
        return iter(
            d for d in self.docs
            if any(q in v.lower() for p in paths for v in main._get_nested_values(d, p))
        )

    def queries(self, *, fuzzy):
        out = []
        for p in self.pipelines:
            auto = p[0]["$search"]["compound"]["should"][0]["autocomplete"]
            if ("fuzzy" in auto) == fuzzy:
                out.append(auto["query"])
        return out


class FakeJev:
    def __init__(self, choice=None, confidence=0.9, error=None):
        self.choice = choice
        self.confidence = confidence
        self.error = error
        self.calls = []

    def system_one(self, state, questions, **kwargs):
        self.calls.append((state, questions))
        if self.error:
            raise self.error
        answer = SimpleNamespace(choice=self.choice, confidence=self.confidence)
        return SimpleNamespace(choices={"intended": answer})


class CorrectQueryTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(correction, "get_settings", return_value=_settings())
        patcher.start()
        self.addCleanup(patcher.stop)

    def _correct(self, jev, query="Acme Industreis", candidates=("Acme Industries Pvt Ltd", "Apex Steel Traders")):
        with patch.object(correction, "get_client", return_value=jev):
            return correction.correct_query(query, list(candidates), "Company Name")

    def test_misspelled_input_is_corrected(self):
        jev = FakeJev(choice="Acme Industries Pvt Ltd")
        self.assertEqual(self._correct(jev), "Acme Industries Pvt Ltd")
        self.assertEqual(len(jev.calls), 1)
        criteria = jev.calls[0][1]["intended"].criteria
        self.assertIn(correction.KEEP_ORIGINAL, criteria)
        self.assertIn("Apex Steel Traders", criteria)

    def test_text_already_matching_skips_jev(self):
        jev = FakeJev(choice="Acme Industries Pvt Ltd")
        self.assertIsNone(self._correct(jev, query="acme ind"))
        self.assertEqual(jev.calls, [])

    def test_short_or_candidate_free_input_skips_jev(self):
        jev = FakeJev(choice="Acme Industries Pvt Ltd")
        self.assertIsNone(self._correct(jev, query="ac"))
        self.assertIsNone(self._correct(jev, candidates=()))
        self.assertEqual(jev.calls, [])

    def test_keep_original_returns_none(self):
        self.assertIsNone(self._correct(FakeJev(choice=correction.KEEP_ORIGINAL)))

    def test_low_confidence_returns_none(self):
        self.assertIsNone(self._correct(FakeJev(choice="Acme Industries Pvt Ltd", confidence=0.3)))

    def test_invalid_choice_returns_none(self):
        self.assertIsNone(self._correct(FakeJev(choice="Something Else")))

    def test_api_timeout_returns_none(self):
        self.assertIsNone(self._correct(FakeJev(error=TypeSafeAPITimeoutError(5.0))))

    def test_unexpected_response_shape_returns_none(self):
        jev = FakeJev()
        jev.system_one = lambda *a, **k: SimpleNamespace(choices={})
        self.assertIsNone(self._correct(jev))

    def test_missing_api_key_disables_correction(self):
        with patch.object(correction, "get_settings", return_value=_settings(typesafe_api_key=SecretStr(""))):
            self.assertIsNone(correction.get_client())


class EndpointTests(unittest.TestCase):
    def setUp(self):
        for target, name, value in (
            (main, "get_settings", _settings()),
            (correction, "get_settings", _settings()),
        ):
            patcher = patch.object(target, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _run(self, endpoint, jev, coll, query="Acme Industreis", fields=(), collection=VENDORS, request=None):
        request = request or main.SuggestRequest
        body = request(query=query, fields=list(fields), orgId=ORG_ID, collectionName=collection)
        with patch.object(main, "get_collection", return_value=coll), \
                patch.object(correction, "get_client", return_value=jev):
            return endpoint(body)

    def test_suggest_returns_corrected_vendor_name(self):
        coll = FakeCollection(VENDOR_DOCS)
        jev = FakeJev(choice="Acme Industries Pvt Ltd")
        res = self._run(main.suggest, jev, coll)
        self.assertEqual(res.suggestions, ["Acme Industries Pvt Ltd"])
        self.assertEqual(coll.queries(fuzzy=False), ["Acme Industries Pvt Ltd"])

    def test_org_filter_kept_on_every_query(self):
        coll = FakeCollection(VENDOR_DOCS)
        self._run(main.suggest, FakeJev(choice="Acme Industries Pvt Ltd"), coll)
        self.assertGreaterEqual(len(coll.pipelines), 2)
        for p in coll.pipelines:
            filters = p[0]["$search"]["compound"]["filter"]
            self.assertIn({"text": {"query": ORG_ID, "path": "orgId"}}, filters)
            self.assertIn({"equals": {"path": "markAsDelete", "value": False}}, filters)
            self.assertEqual(p[0]["$search"]["index"], "vendor-master")

    def test_search_returns_corrected_documents(self):
        coll = FakeCollection(VENDOR_DOCS)
        res = self._run(
            main.search, FakeJev(choice="Acme Industries Pvt Ltd"), coll, request=main.SearchRequest
        )
        self.assertEqual(res.count, 1)
        self.assertEqual(res.documents[0]["vendorCode"], "V001")

    def test_jev_failure_falls_back_to_original_text(self):
        coll = FakeCollection(VENDOR_DOCS)
        res = self._run(main.suggest, FakeJev(error=TypeSafeAPITimeoutError(5.0)), coll)
        self.assertEqual(res.suggestions, [])
        self.assertEqual(coll.queries(fuzzy=False), ["Acme Industreis"])

    def test_corrected_text_without_matches_falls_back_to_original(self):
        coll = FakeCollection(VENDOR_DOCS)
        # A candidate the normal search can't find, so the original query must run as fallback.
        with patch.object(main, "_distinct_values", return_value=["Acme Industries Limited"]):
            res = self._run(main.suggest, FakeJev(choice="Acme Industries Limited"), coll)
        self.assertEqual(res.suggestions, [])
        self.assertEqual(coll.queries(fuzzy=False), ["Acme Industries Limited", "Acme Industreis"])

    def test_correct_prefix_is_searched_unchanged(self):
        coll = FakeCollection(VENDOR_DOCS)
        jev = FakeJev(choice="Apex Steel Traders")
        res = self._run(main.suggest, jev, coll, query="Ac")
        self.assertEqual(res.suggestions, ["Acme Industries Pvt Ltd"])
        self.assertEqual(jev.calls, [])
        self.assertEqual(coll.queries(fuzzy=True), [])

    def test_non_vendor_field_selection_skips_correction(self):
        coll = FakeCollection(VENDOR_DOCS)
        jev = FakeJev(choice="Acme Industries Pvt Ltd")
        self._run(main.suggest, jev, coll, fields=["vendorCode"])
        self.assertEqual(jev.calls, [])
        self.assertEqual(coll.queries(fuzzy=True), [])

    def test_other_collections_skip_correction(self):
        coll = FakeCollection([])
        jev = FakeJev(choice="anything")
        body = main.SuggestRequest(
            query="PR-1oo1", fields=[], orgId=ORG_ID, orgOpuId="opu-1", collectionName="PurRequisitions"
        )
        with patch.object(main, "get_collection", return_value=coll), \
                patch.object(correction, "get_client", return_value=jev):
            main.suggest(body)
        self.assertEqual(jev.calls, [])
        self.assertEqual(coll.queries(fuzzy=True), [])

    def test_mongo_error_returns_502(self):
        coll = FakeCollection(VENDOR_DOCS, error=RuntimeError("cluster down"))
        with self.assertRaises(HTTPException) as ctx:
            self._run(main.suggest, FakeJev(), coll)
        self.assertEqual(ctx.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
