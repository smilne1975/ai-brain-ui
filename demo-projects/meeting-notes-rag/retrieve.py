"""Search helper. Chroma is still only a comment in requirements.txt."""

import chromadb  # noqa: F401


def search(question: str) -> list[str]:
    # TODO: use the JSON index until chromadb is actually installed
    raise NotImplementedError(question)
