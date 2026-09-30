from assistant.core.observability import mask


def test_mask_hides_keys_tokens_and_emails():
    masked = mask(data={"a": "key sk-ant-abcdefghijklmnopqrstuvwxyz and me@x.com", "b": ["API_KEY=abc123"]})
    assert masked == {"a": "key [API_KEY] and [EMAIL]", "b": ["API_KEY=[SECRET]"]}
