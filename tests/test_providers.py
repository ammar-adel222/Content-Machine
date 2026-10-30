import io
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from war_research.models import Selection
from war_research.providers import LanguageModel, ProviderError, Web, gemini_schema, load_env, request_json
from .helpers import candidate


class HttpTests(unittest.TestCase):
    def test_post_json_headers(self):
        opener = Mock(return_value=io.BytesIO(b'{"ok": true}'))
        self.assertTrue(request_json("https://example.org", {"query": "test"}, {"Authorization": "secret"}, opener=opener)["ok"])
        req = opener.call_args.args[0]
        self.assertEqual(json.loads(req.data), {"query": "test"})
        self.assertEqual(req.get_header("Authorization"), "secret")

    def test_get_has_no_body(self):
        opener = Mock(return_value=io.BytesIO(b'{}'))
        request_json("https://example.org", opener=opener)
        self.assertIsNone(opener.call_args.args[0].data)

    def test_rate_limit_retry(self):
        opener = Mock(side_effect=[HTTPError("https://example.org", 429, "secret", {"Retry-After": "2"}, None),
                                   io.BytesIO(b'{}')])
        sleep = Mock()
        request_json("https://example.org", opener=opener, sleep=sleep)
        sleep.assert_called_once_with(2)
        self.assertEqual(opener.call_count, 2)

    def test_long_rate_limit_does_not_block_fallback(self):
        opener = Mock(side_effect=HTTPError("https://example.org", 429, "secret", {"Retry-After": "60"}, None))
        sleep = Mock()
        with self.assertRaisesRegex(ProviderError, "HTTP 429"):
            request_json("https://example.org", opener=opener, sleep=sleep)
        sleep.assert_not_called()

    def test_content_waits_for_bounded_decimal_token_reset(self):
        opener=Mock(side_effect=[HTTPError('https://example.org',429,'secret',{'Retry-After':'12.5'},None),io.BytesIO(b'{}')])
        sleep=Mock()
        request_json('https://example.org',opener=opener,sleep=sleep,max_retry_wait=60)
        sleep.assert_called_once_with(12.5)
        for delay in ('-2','invalid'):
            opener=Mock(side_effect=[HTTPError('https://example.org',429,'secret',{'Retry-After':delay},None),io.BytesIO(b'{}')])
            sleep=Mock();request_json('https://example.org',opener=opener,sleep=sleep)
            sleep.assert_called_once_with(1)
        opener=Mock(side_effect=HTTPError('https://example.org',429,'secret',{'Retry-After':'100'},None))
        with self.assertRaises(ProviderError):request_json('https://example.org',opener=opener,sleep=Mock(),max_retry_wait=999)

    def test_auth_failure_not_retried_or_leaked(self):
        opener = Mock(side_effect=HTTPError("https://example.org?key=secret", 401, "SECRET BODY", {}, None))
        with self.assertRaises(ProviderError) as caught:
            request_json("https://example.org", opener=opener)
        self.assertEqual(str(caught.exception), "Provider HTTP 401.")
        self.assertEqual(opener.call_count, 1)

    def test_network_retry_is_bounded(self):
        for error in (URLError("secret"), TimeoutError("secret"), OSError("secret")):
            opener = Mock(side_effect=error)
            with self.subTest(error=type(error)), self.assertRaises(ProviderError):
                request_json("https://example.org", opener=opener, sleep=Mock())
            self.assertEqual(opener.call_count, 2)

    def test_malformed_json_and_nonobject_rejected(self):
        for body in (b"invalid", b"[]"):
            with self.subTest(body=body), self.assertRaises(ProviderError):
                request_json("https://example.org", opener=Mock(return_value=io.BytesIO(body)))


class EnvironmentTests(unittest.TestCase):
    def test_quoted_values_comments_export_and_precedence(self):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"EXISTING": "keep"}, clear=True):
            path = Path(tmp) / ".env"
            path.write_text('# Comment\nexport A="a # b"\nB=token # comment\nEXISTING=replace\nEMPTY=\n', encoding="utf-8")
            load_env(path)
            self.assertEqual(os.environ["A"], "a # b")
            self.assertEqual(os.environ["B"], "token")
            self.assertEqual(os.environ["EXISTING"], "keep")
            self.assertEqual(os.environ["EMPTY"], "")

    def test_bad_quotes_report_name_not_value(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text('KEY="secret', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "KEY") as caught:
                load_env(path)
            self.assertNotIn("secret", str(caught.exception))


class WebTests(unittest.TestCase):
    def test_missing_key(self):
        with self.assertRaises(ValueError):
            Web("")

    def test_search_uses_basic_and_no_answer(self):
        transport = Mock(return_value={"results": [{"url": "https://example.org"}]})
        self.assertEqual(len(Web("secret", transport).search("battle")), 1)
        _, payload, headers = transport.call_args.args
        self.assertEqual(payload["search_depth"], "basic")
        self.assertFalse(payload["include_answer"])
        self.assertNotIn("secret", json.dumps(payload))
        self.assertEqual(headers["Authorization"], "Bearer secret")

    def test_extract_returns_raw_text(self):
        transport = Mock(return_value={"results": [{"url": "https://example.org", "raw_content": "page"}]})
        self.assertEqual(Web("key", transport).extract(["https://example.org"]), {"https://example.org": "page"})

    def test_empty_extract_makes_no_call(self):
        transport = Mock()
        self.assertEqual(Web("key", transport).extract([]), {})
        transport.assert_not_called()

    def test_wikipedia_page_and_fallback_url(self):
        for fullurl in (None, "https://en.wikipedia.org/wiki/Battle"):
            row = {"title": "Example Battle", "extract": "text"}
            if fullurl:
                row["fullurl"] = fullurl
            transport = Mock(return_value={"query": {"pages": {"1": row}}})
            result = Web("key", transport).wikipedia("Example")
            self.assertTrue(result[0]["url"].startswith("https://en.wikipedia.org/wiki/"))
            self.assertTrue(result[0]["full_text"])

    def test_wikipedia_no_results(self):
        self.assertEqual(Web("key", Mock(return_value={})).wikipedia("unknown"), [])


class LanguageModelTests(unittest.TestCase):
    def setUp(self):
        self.content = Selection(candidates=[candidate()]).model_dump_json()
        self.consume = Mock()

    def test_gemini_response_and_key_in_header(self):
        transport = Mock(return_value={"candidates": [{"content": {"parts": [
            {"thought": True, "text": "Not JSON thinking"}, {"text": self.content}]}}]})
        model = LanguageModel([("gemini", "test-model", "secret")], transport)
        result = model.generate("Evidence", Selection, self.consume)
        self.assertEqual(result.candidates[0].topic, "Example Battle")
        self.assertEqual(model.used, ["gemini:test-model"])
        url, payload, headers = transport.call_args.args
        self.assertNotIn("secret", url)
        self.assertEqual(headers["x-goog-api-key"], "secret")
        self.assertIn("untrusted", payload["systemInstruction"]["parts"][0]["text"])
        self.assertEqual(payload["generationConfig"]["responseJsonSchema"], gemini_schema(Selection.model_json_schema()))
        self.consume.assert_called_once()

    def test_gemini_schema_keeps_title_field_and_local_constraints(self):
        from war_writer.models import Draft
        original = Draft.model_json_schema()
        simplified = gemini_schema(original)
        self.assertIn("title", simplified["properties"])
        self.assertNotIn("maxLength", simplified["properties"]["title"])
        self.assertIn("maxLength", original["properties"]["title"])
        self.assertNotIn("pattern", simplified["$defs"]["Scene"]["properties"]["id"])
    def test_groq_json_mode(self):
        transport = Mock(return_value={"choices": [{"message": {"content": self.content}}]})
        model = LanguageModel([("groq", "test-model", "secret")], transport)
        model.generate("Evidence", Selection, self.consume)
        self.assertEqual(transport.call_args.args[1]["response_format"], {"type": "json_object"})

    def test_openrouter_fenced_json_and_free_routing(self):
        transport = Mock(return_value={"choices": [{"message": {"content": "```json\n" + self.content + "\n```"}}]})
        model = LanguageModel([("openrouter", "model:free", "secret")], transport)
        result = model.generate("Evidence", Selection, self.consume)
        self.assertEqual(result.candidates[0].topic, "Example Battle")
        url, payload, headers = transport.call_args.args
        self.assertEqual(url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(payload["provider"]["max_price"], {"prompt": 0, "completion": 0})
        self.assertNotIn("response_format", payload)
        self.assertEqual(transport.call_args.kwargs["timeout"], 180)
        self.assertEqual(headers["Authorization"], "Bearer secret")

    def test_openrouter_invalid_response_is_rejected(self):
        model = LanguageModel([("openrouter", "model:free", "key")], Mock(return_value={"error": {"message": "private"}}))
        with self.assertRaises(ProviderError) as caught:
            model.generate("Evidence", Selection, self.consume)
        self.assertNotIn("private", str(caught.exception))

    def test_openrouter_super_vl_uses_native_schema(self):
        transport = Mock(return_value={"choices": [{"message": {"content": self.content}, "finish_reason": "stop"}]})
        model = LanguageModel([("openrouter", "nvidia/nemotron-3.5-super-vl:free", "key")], transport)
        model.generate("Evidence", Selection, self.consume)
        payload = transport.call_args.args[1]
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertEqual(payload["response_format"]["json_schema"]["schema"], Selection.model_json_schema())
        self.assertFalse(payload["reasoning"]["enabled"])

    def test_openrouter_ultra_has_explicit_reasoning_budget(self):
        transport = Mock(return_value={"choices": [{"message": {"content": self.content}}]})
        model = LanguageModel([("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", "key")], transport)
        model.generate("Evidence", Selection, self.consume)
        self.assertEqual(transport.call_args.args[1]["reasoning"]["max_tokens"], 1024)

    def test_free_router_records_actual_selected_model(self):
        transport = Mock(return_value={"model": "selected/model:free",
            "choices": [{"message": {"content": self.content}}]})
        model = LanguageModel([("openrouter", "openrouter/free", "key")], transport)
        model.generate("Evidence", Selection, self.consume)
        self.assertEqual(model.used, ["openrouter:selected/model:free"])
        self.assertEqual(transport.call_args.args[1]["response_format"]["type"], "json_schema")

    def test_native_schema_constrains_available_passages(self):
        from war_research.models import Findings
        from .helpers import findings
        transport = Mock(return_value={"candidates": [{"content": {"parts": [{"text": findings().model_dump_json()}]}}]})
        model = LanguageModel([("gemini", "test", "key")], transport)
        model.generate("Evidence", Findings, self.consume, passage_ids=["S1:P1", "S2:P1"])
        schema = transport.call_args.args[1]["generationConfig"]["responseJsonSchema"]
        self.assertEqual(schema["$defs"]["Evidence"]["properties"]["passage_id"]["enum"], ["S1:P1", "S2:P1"])

    def test_fallback_after_provider_or_schema_failure(self):
        for first in (ProviderError("quota"), {"candidates": []},
                      {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}):
            transport = Mock(side_effect=[first, {"choices": [{"message": {"content": self.content}}]}])
            model = LanguageModel([("gemini", "one", "a"), ("groq", "two", "b")], transport)
            with self.subTest(first=first):
                model.generate("Evidence", Selection, self.consume)
                self.assertEqual(model.used, ["groq:two"])

    def test_all_models_fail_cleanly(self):
        model = LanguageModel([("gemini", "test", "key")], Mock(return_value={}))
        with self.assertRaisesRegex(ProviderError, "All configured"):
            model.generate("Evidence", Selection, self.consume)

    def test_missing_or_unknown_configuration(self):
        for config in ([], [("groq", "test", "")], [("unknown", "test", "key")]):
            with self.subTest(config=config), self.assertRaises(ValueError):
                LanguageModel(config)

    def test_budget_failure_does_not_call_transport(self):
        transport = Mock()
        model = LanguageModel([("gemini", "test", "key")], transport)
        with self.assertRaises(RuntimeError):
            model.generate("Evidence", Selection, Mock(side_effect=RuntimeError("budget")))
        transport.assert_not_called()
