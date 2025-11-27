from __future__ import annotations

"""FastAPI wrapper around the troubleshooting retriever stack."""

from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import CrossEncoder, SentenceTransformer
import chromadb

MODEL_NAME = "all-MiniLM-L6-v2"
RERANKER_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "troubleshooting_steps"
TOP_K = 20
TOP_RESPONSE = 3


def _load_collection() -> chromadb.api.models.Collection.Collection:
    """Instantiate the persistent Chroma client and return the collection."""

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        return client.get_collection(COLLECTION_NAME)
    except chromadb.errors.NotFoundError as exc:  # pragma: no cover - safety guard
        raise RuntimeError(
            f"Collection '{COLLECTION_NAME}' not found. Run the indexing script before starting the API."
        ) from exc


# Heavy objects are created once at import time for reuse across requests.
encoder = SentenceTransformer(MODEL_NAME)
reranker = CrossEncoder(RERANKER_NAME)
collection = _load_collection()
app = FastAPI(title="Troubleshooting Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str
    category: Optional[str] = None


class Step(BaseModel):
    id: str
    text: str
    error_code: Optional[str] = None
    category: Optional[str] = None
    risk: Optional[str] = None
    source: Optional[str] = None
    parent_id: Optional[str] = None


class QueryResponse(BaseModel):
    prompt: str
    sources: List[str]
    steps: List[Step]


class ErrorResponse(BaseModel):
    detail: str


def retrieve_topk(query: str, k: int = TOP_K):
    """Return the top-k semantic matches from Chroma."""

    query_vector = encoder.encode(query).tolist()
    result = collection.query(query_embeddings=[query_vector], n_results=k)
    ids = result.get("ids", [[]])[0]
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    return [
        {"id": ids[i], "text": docs[i], "meta": metas[i]}
        for i in range(len(ids))
    ]


def answer_query(query: str, category: Optional[str] = None):
    """Retrieve, optionally filter, and rerank passages for the query."""

    candidates = retrieve_topk(query, k=TOP_K)
    if category:
        candidates = [c for c in candidates if c["meta"].get("category") == category]
    if not candidates:
        return []
    pairs = [(query, c["text"]) for c in candidates]
    scores = reranker.predict(pairs)
    return sorted(
        zip(candidates, scores), key=lambda item: item[1], reverse=True
    )[:TOP_RESPONSE]


def build_prompt(query: str, passages):
    """Construct the instruction prompt for downstream generators."""

    formatted = "\n\n".join(f"[{p['id']}] {p['text']}" for p in passages)
    return (
        f'User issue: "{query}"\n'
        "Use only the passages below to produce a numbered plan where each step\n"
        "includes: Instruction, Verification, Risk, and Sources (ids).\n\n"
        f"PASSAGES:\n{formatted}\n\nAnswer:"
    )


@app.get("/health", response_model=dict)
def health_check():
    """Basic health endpoint for uptime monitoring."""

    return {"status": "ok"}


@app.post(
    "/troubleshoot",
    response_model=QueryResponse,
    responses={404: {"model": ErrorResponse}},
)
def troubleshoot(payload: QueryRequest):
    ranked = answer_query(payload.query, payload.category)
    if not ranked:
        raise HTTPException(status_code=404, detail="No matching passages found")
    passages = [item[0] for item in ranked]
    prompt = build_prompt(payload.query, passages)
    steps = [
        Step(
            id=p["id"],
            text=p["text"],
            error_code=p["meta"].get("error_code"),
            category=p["meta"].get("category"),
            risk=p["meta"].get("risk"),
            source=p["meta"].get("source"),
            parent_id=p["meta"].get("parent_id"),
        )
        for p in passages
    ]
    return QueryResponse(
        prompt=prompt,
        sources=[p["id"] for p in passages],
        steps=steps,
    )
