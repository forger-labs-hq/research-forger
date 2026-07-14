"""A deliberately small keyword sentiment classifier.

Deterministic on purpose: the example exists to demonstrate the
ResearchForge experiment funnel, so the benchmark must produce the same
numbers on every machine. The classifier has two real weaknesses that
experiments can address by patching `src/config.py`:

- without NORMALIZE it misses capitalized/punctuated keywords;
- without NGRAM_EXPANSION it misreads negations like "not bad".
"""

from src import config

KEYWORDS = {
    "great": 2,
    "good": 1,
    "excellent": 2,
    "love": 2,
    "nice": 1,
    "bad": -2,
    "poor": -1,
    "terrible": -2,
    "hate": -2,
    "awful": -2,
}

BIGRAMS = {
    "not bad": 3,
    "not good": -3,
}


def tokenize(text: str) -> list[str]:
    parts = text.split()
    if config.NORMALIZE:
        parts = [part.strip(".,!?").lower() for part in parts]
    return parts


def score(text: str) -> int:
    tokens = tokenize(text)
    total = sum(KEYWORDS.get(token, 0) for token in tokens)
    if config.NGRAM_EXPANSION:
        for first, second in zip(tokens, tokens[1:], strict=False):
            total += BIGRAMS.get(f"{first} {second}", 0)
    return total


def predict(text: str) -> str:
    return "pos" if score(text) > 0 else "neg"


def cost_units(text: str) -> int:
    """Deterministic work estimate used as the latency proxy.

    Real wall-clock latency would make the benchmark flaky across machines;
    the demo instead counts feature lookups, which is what the n-gram
    expansion genuinely multiplies.
    """
    tokens = text.split()
    units = len(tokens)
    if config.NGRAM_EXPANSION:
        units += 2 * max(len(tokens) - 1, 0) * len(BIGRAMS)
    return units
