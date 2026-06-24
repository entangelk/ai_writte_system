import unittest

from services.llm_gateway.app.payload import (
    ChatCompletionRequest,
    ChatMessage,
    build_llama_payload,
)


class LlamaPayloadContractTests(unittest.TestCase):
    """Lock both thinking directions and the non-streaming gateway boundary."""

    def _request(self, **overrides):
        values = {
            "messages": (ChatMessage(role="user", content="안녕"),),
        }
        values.update(overrides)
        return ChatCompletionRequest(**values)

    def test_thinking_false_disables_reasoning(self):
        payload = build_llama_payload(
            self._request(thinking=False),
            default_model="gemma-test",
            default_thinking=True,
        )

        self.assertIs(payload["chat_template_kwargs"]["enable_thinking"], False)

    def test_thinking_true_enables_reasoning(self):
        payload = build_llama_payload(
            self._request(thinking=True),
            default_model="gemma-test",
            default_thinking=False,
        )

        self.assertIs(payload["chat_template_kwargs"]["enable_thinking"], True)

    def test_default_thinking_applies_when_request_omits_it(self):
        payload = build_llama_payload(
            self._request(),
            default_model="gemma-test",
            default_thinking=False,
        )

        self.assertIs(payload["chat_template_kwargs"]["enable_thinking"], False)

    def test_explicit_template_setting_overrides_thinking_flag(self):
        payload = build_llama_payload(
            self._request(
                thinking=True,
                chat_template_kwargs={"enable_thinking": False},
            ),
            default_model="gemma-test",
            default_thinking=True,
        )

        self.assertIs(payload["chat_template_kwargs"]["enable_thinking"], False)

    def test_legacy_think_token_is_not_injected(self):
        payload = build_llama_payload(
            self._request(thinking=True),
            default_model="gemma-test",
            default_thinking=True,
        )

        for message in payload["messages"]:
            self.assertNotIn("<|think|>", message.get("content", ""))

    def test_streaming_is_rejected_until_gateway_supports_it(self):
        with self.assertRaisesRegex(ValueError, "streaming is not supported"):
            self._request(stream=True)

    def test_generation_fields_are_forwarded_without_mutating_request(self):
        template_kwargs = {"custom": "value"}
        request = self._request(
            model="custom-model",
            temperature=0.2,
            top_p=0.8,
            max_tokens=128,
            chat_template_kwargs=template_kwargs,
        )

        payload = build_llama_payload(
            request,
            default_model="gemma-test",
            default_thinking=False,
        )

        self.assertEqual(payload["model"], "custom-model")
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["top_p"], 0.8)
        self.assertEqual(payload["max_tokens"], 128)
        self.assertEqual(template_kwargs, {"custom": "value"})


if __name__ == "__main__":
    unittest.main()
