"""The model providers clients offer: the three lo9i builds itself (Anthropic with prompt caching,
GitHub Copilot with its token exchange, OpenAI-compatible servers) and every provider LangChain's
`init_chat_model` supports, each with the fields it needs (core/llm/__init__.py builds them).

A provider's package is installed when it's first chosen (core/llm/packages.py), so only the ones
in use take space. Field keys are the chat model's own keyword arguments. Left out:
`huggingface`, which runs models on this computer, not through an API.
"""

from dataclasses import dataclass

# Prompt caching, token exchange or server URLs that lo9i handles itself (core/llm/__init__.py).
NATIVE = ("anthropic", "copilot", "openai")


@dataclass(frozen=True)
class ProviderField:
    # The chat model's keyword argument.
    key: str
    label: str
    secret: bool = False
    required: bool = True
    help: str = ""


@dataclass(frozen=True)
class ModelProvider:
    """A provider clients offer, with what it asks for and the models to suggest."""

    id: str
    name: str
    fields: list[ProviderField]
    model: str = ""
    worker_model: str = ""
    # How to get the values, or where models are listed.
    help: str = ""
    # The pip requirement installed on first use; "" when it ships with the assistant.
    package: str = ""
    # The module that shows the package is installed.
    module: str = ""
    # The keyword for the reply length limit; "" when the model takes none.
    max_tokens_key: str = "max_tokens"
    # Also passed the model id under this keyword (Azure OpenAI's deployment).
    model_key: str = ""
    # Set when the list is sent to clients: whether the package is installed (core/llm/packages.py).
    installed: bool = True


def _key(label: str = "API key", help: str = "") -> ProviderField:
    return ProviderField("api_key", label, secret=True, help=help)


def _url(key: str = "base_url", label: str = "Server URL", help: str = "") -> ProviderField:
    return ProviderField(key, label, required=False, help=help)


_AWS = [
    ProviderField("region_name", "AWS region", help="Like us-east-1."),
    ProviderField("aws_access_key_id", "Access key ID", secret=True),
    ProviderField("aws_secret_access_key", "Secret access key", secret=True),
]

_VERTEX = [
    ProviderField("project", "Google Cloud project ID"),
    ProviderField("location", "Region", help="Like us-central1."),
    ProviderField(
        "service_account_json",
        "Service account key (JSON)",
        secret=True,
        help="Paste the whole JSON key of a service account with the Vertex AI User role.",
    ),
]


def _lc(
    id: str,
    name: str,
    package: str,
    module: str,
    fields: list[ProviderField],
    help: str = "",
    max_tokens_key: str = "max_tokens",
    model_key: str = "",
) -> ModelProvider:
    return ModelProvider(
        id,
        name,
        fields,
        help=help,
        package=package,
        module=module,
        max_tokens_key=max_tokens_key,
        model_key=model_key,
    )


NATIVE_PROVIDERS = [
    ModelProvider(
        "anthropic",
        "Anthropic",
        [_key(help="Create one at https://console.anthropic.com/settings/keys.")],
        "claude-opus-5-5",
        "claude-sonnet-5-5",
    ),
    ModelProvider(
        "copilot",
        "GitHub Copilot",
        [_key("GitHub token", "A GitHub token of an account with a Copilot subscription.")],
        "claude-opus-5.5",
        "claude-sonnet-5.5",
        help="Copilot's model ids use dots.",
    ),
    ModelProvider(
        "openai",
        "OpenAI-compatible",
        [
            _key(help="For Ollama or another server without keys, any text."),
            _url(help="Empty for OpenAI. Ollama: http://localhost:11434/v1."),
        ],
    ),
]

LANGCHAIN_PROVIDERS = [
    _lc(
        "google_genai",
        "Google Gemini",
        "langchain-google-genai>=4.4,<5",
        "langchain_google_genai",
        [_key(help="Create one at https://aistudio.google.com/apikey.")],
        max_tokens_key="max_output_tokens",
    ),
    _lc(
        "google_vertexai",
        "Google Vertex AI",
        "langchain-google-vertexai>=3.2,<4",
        "langchain_google_vertexai",
        _VERTEX,
        max_tokens_key="max_output_tokens",
    ),
    _lc(
        "google_anthropic_vertex",
        "Claude on Google Vertex AI",
        "langchain-google-vertexai>=3.2,<4",
        "langchain_google_vertexai",
        _VERTEX,
        max_tokens_key="max_output_tokens",
    ),
    _lc(
        "azure_openai",
        "Azure OpenAI",
        "",
        "langchain_openai",
        [
            ProviderField("azure_endpoint", "Endpoint", help="Like https://my-resource.openai.azure.com/."),
            _key(),
            ProviderField("api_version", "API version", help="Like 2024-10-21."),
        ],
        help="The model is the deployment's name.",
        model_key="azure_deployment",
        max_tokens_key="max_completion_tokens",
    ),
    _lc(
        "azure_ai",
        "Azure AI Foundry",
        "langchain-azure-ai>=1.2,<2",
        "langchain_azure_ai",
        [ProviderField("endpoint", "Endpoint"), ProviderField("credential", "API key", secret=True)],
    ),
    _lc("bedrock_converse", "Amazon Bedrock", "langchain-aws>=1.8,<2", "langchain_aws", _AWS),
    _lc("bedrock", "Amazon Bedrock (InvokeModel)", "langchain-aws>=1.8,<2", "langchain_aws", _AWS),
    _lc("anthropic_bedrock", "Claude on Amazon Bedrock", "langchain-aws>=1.8,<2", "langchain_aws", _AWS),
    _lc("bedrock_mantle_anthropic", "Claude on Amazon Bedrock Mantle", "langchain-aws>=1.8,<2", "langchain_aws", _AWS),
    _lc(
        "bedrock_mantle_openai",
        "OpenAI models on Amazon Bedrock Mantle",
        "langchain-aws>=1.8,<2",
        "langchain_aws",
        _AWS,
    ),
    _lc("mistralai", "Mistral AI", "langchain-mistralai>=1.1,<2", "langchain_mistralai", [_key()]),
    _lc("groq", "Groq", "langchain-groq>=1.1,<2", "langchain_groq", [_key()]),
    _lc("deepseek", "DeepSeek", "langchain-deepseek>=1.1,<2", "langchain_deepseek", [_key()]),
    _lc("xai", "xAI (Grok)", "langchain-xai>=1.3,<2", "langchain_xai", [_key()]),
    _lc("openrouter", "OpenRouter", "langchain-openrouter>=0.2.9,<1", "langchain_openrouter", [_key()]),
    _lc("together", "Together AI", "langchain-together>=0.4,<1", "langchain_together", [_key()]),
    _lc("fireworks", "Fireworks AI", "langchain-fireworks>=1.7,<2", "langchain_fireworks", [_key()]),
    _lc("perplexity", "Perplexity", "langchain-perplexity>=1.4,<2", "langchain_perplexity", [_key()]),
    _lc(
        "cohere",
        "Cohere",
        "langchain-cohere>=0.6,<1",
        "langchain_cohere",
        [ProviderField("cohere_api_key", "API key", secret=True)],
        max_tokens_key="",
    ),
    _lc(
        "nvidia",
        "NVIDIA",
        "langchain-nvidia-ai-endpoints>=1.4,<2",
        "langchain_nvidia_ai_endpoints",
        [_key(), _url(help="Empty for NVIDIA's hosted API; a self-hosted NIM's URL otherwise.")],
        max_tokens_key="max_completion_tokens",
    ),
    _lc("upstage", "Upstage", "langchain-upstage>=0.7,<1", "langchain_upstage", [_key()]),
    _lc("baseten", "Baseten", "langchain-baseten>=0.2.4,<1", "langchain_baseten", [_key()]),
    _lc("meta", "Meta Llama API", "langchain-meta>=0.5,<1", "langchain_meta", [_key()]),
    _lc(
        "ibm",
        "IBM watsonx.ai",
        "langchain-ibm>=1.1,<2",
        "langchain_ibm",
        [
            ProviderField("url", "Service URL", help="Like https://us-south.ml.cloud.ibm.com."),
            ProviderField("apikey", "API key", secret=True),
            ProviderField("project_id", "Project ID"),
        ],
    ),
    _lc(
        "ollama",
        "Ollama",
        "langchain-ollama>=1.1,<2",
        "langchain_ollama",
        [_url(help="Empty for Ollama on this computer (http://localhost:11434).")],
        max_tokens_key="num_predict",
    ),
    _lc(
        "litellm",
        "LiteLLM",
        "langchain-litellm>=0.6.4,<1",
        "langchain_litellm",
        [ProviderField("api_key", "API key", secret=True, required=False), _url("api_base", "Proxy URL")],
        help="Model ids name their provider, like openai/gpt-4o.",
    ),
    _lc(
        "langsmith",
        "LangSmith gateway",
        "",
        "langchain_openai",
        [_key("LangSmith API key")],
        max_tokens_key="max_completion_tokens",
    ),
]

PROVIDERS = NATIVE_PROVIDERS + LANGCHAIN_PROVIDERS


def provider(provider_id: str) -> ModelProvider | None:
    return next((p for p in PROVIDERS if p.id == provider_id), None)
