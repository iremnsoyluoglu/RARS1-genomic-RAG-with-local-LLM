# trick question dahil 3 test, eval_results.json'a yazar

import os
import re
import json
import requests
import chromadb
from chromadb.utils import embedding_functions
from chromadb.config import Settings
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# Ollama modeli - .env'de OLLAMA_MODEL varsa onu kullan, yoksa llama3
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# main.py ile aynı prompt — doğal, kaynak odaklı
SYSTEM_PROMPT = """You are a genomics research assistant with deep expertise 
in aminoacyl-tRNA synthetase disorders, particularly RARS1-related 
Hypomyelinating Leukodystrophy. You help clinicians and researchers 
navigate the published literature.

Your knowledge comes entirely from the research abstracts retrieved for 
each question. You reason carefully over them, distinguish phenotypes 
from molecular variants, and always ground your answers in what the 
studies actually report.

When you answer:
- Speak like a knowledgeable colleague, not a form-filling machine.
- Naturally weave citations into sentences: "Smith et al. found that... [PMID: 12345]"
- Separate clinical observations (phenotypes) from molecular findings (variants).
- If the retrieved abstracts don't contain enough information, say so 
  plainly: "The abstracts I have access to don't cover this — you may 
  want to search ClinVar or OMIM directly."
- Never invent a variant name or symptom. If it's not in the sources, 
  it doesn't belong in your answer.

Format naturally. Use short paragraphs. Only use bullet points when 
listing multiple discrete items (e.g., a variant table). Always end 
with a brief "Sources consulted:" line listing the PMIDs you drew from."""

TESTS = [
    {"query": "What variants in RARS1 cause leukodystrophy?", "type": "real"},
    {"query": "Is RARS1 associated with cystic fibrosis?", "type": "trick"},
    {"query": "What neurological symptoms are seen in RARS1 patients?", "type": "phenotype"},
]


def load_chromadb():
    if not os.path.exists("./chroma_db"):
        print("\n❌  Önce python ingest.py çalıştır.\n")
        exit(1)
    client = chromadb.PersistentClient(
        path="./chroma_db",
        settings=Settings(anonymized_telemetry=False),
    )
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    try:
        return client.get_collection("rars1_genomics", embedding_function=ef)
    except Exception:
        print("\n❌  Collection bulunamadı. python ingest.py çalıştır.\n")
        exit(1)


def retrieve_context(query, collection, n=3):
    count = collection.count()
    if count == 0:
        return []
    results = collection.query(query_texts=[query], n_results=min(n, count))
    docs = results.get("documents", [[]])[0] or []
    metas = results.get("metadatas", [[]])[0] or []
    chunks = []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        chunks.append({
            "text": (doc or "")[:900],
            "pmid": meta.get("pmid", ""),
            "doi": meta.get("doi", ""),
            "title": meta.get("title", ""),
        })
    return chunks


def format_context(chunks):
    parts = []
    for i, c in enumerate(chunks, 1):
        cite = f"PMID: {c['pmid']}" if c["pmid"] else f"DOI: {c['doi']}"
        parts.append(f"[{i}] {cite}\n    {c['title']}\n    {c['text']}")
    return "\n\n".join(parts)


def validate_response(response, chunks):
    pattern = r'\b[cp]\.\d+[A-Z]>[A-Z]\b|\b[cp]\.[A-Za-z]+\d+[A-Za-z]+\b'
    claimed = set(re.findall(pattern, response))
    sourced = " ".join(c["text"] for c in chunks)
    return [f"⚠️  Variant '{v}' was mentioned but not found in any retrieved source."
            for v in claimed if v not in sourced]


def call_llm(user_prompt: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    try:
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {
                    "num_predict": 400,
                    "temperature": 0.4,
                },
            },
            timeout=600,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("message") or {}).get("content", "") or ""
    except requests.RequestException as e:
        print(f"\n⚠️  Ollama API error: {e}\n")
        return ""


def run_test(test, collection):
    chunks = retrieve_context(test["query"], collection)
    if not chunks:
        return {
            "query": test["query"],
            "query_type": test["type"],
            "retrieved_chunks": 0,
            "response": "",
            "hallucination_warnings": [],
            "passed": False,
            "timestamp": datetime.now().isoformat(),
        }

    context_block = format_context(chunks)
    user_prompt = (
        f"Here are the most relevant research excerpts I retrieved "
        f"for your question:\n\n{context_block}\n\n---\nQuestion: {test['query']}"
    )

    response = call_llm(user_prompt)

    warnings = validate_response(response, chunks)
    resp_lower = response.lower()

    if test["type"] == "real":
        passed = "pmid" in resp_lower
    elif test["type"] == "trick":
        passed = "no evidence" in resp_lower or "not found" in resp_lower or "insufficient" in resp_lower or "don't cover" in resp_lower
    elif test["type"] == "phenotype":
        passed = ("phenotype" in resp_lower or "symptom" in resp_lower) and "pmid" in resp_lower
    else:
        passed = False

    return {
        "query": test["query"],
        "query_type": test["type"],
        "retrieved_chunks": len(chunks),
        "response": response,
        "hallucination_warnings": warnings,
        "passed": passed,
        "timestamp": datetime.now().isoformat(),
    }


def main():
    print("\nDeğerlendirme başlıyor...\n")
    collection = load_chromadb()
    results = []

    for test in TESTS:
        print(f"  {test['type']}: {test['query'][:50]}...")
        r = run_test(test, collection)
        results.append(r)

    with open("eval_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "─" * 50)
    for r in results:
        s = "✓" if r["passed"] else "✗"
        print(f"  {s}  {r['query_type']}")
    print("─" * 50)
    print("  eval_results.json kaydedildi\n")


if __name__ == "__main__":
    main()
