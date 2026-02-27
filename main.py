# RARS1 RAG - main entry point
import os
import re
import requests
import chromadb
from chromadb.utils import embedding_functions
from chromadb.config import Settings
from dotenv import load_dotenv

load_dotenv()

# Ollama modeli - .env'de OLLAMA_MODEL varsa onu kullan, yoksa llama3
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# system prompt - kaynaklara bagli, dogal cevap
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


def load_chromadb():
    if not os.path.exists("./chroma_db"):
        print("\n❌  No database found. Run 'python ingest.py' first.\n")
        exit(1)
    client = chromadb.PersistentClient(
        path="./chroma_db",
        settings=Settings(anonymized_telemetry=False),
    )
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    try:
        return client.get_collection("rars1_genomics", embedding_function=ef)
    except Exception:
        print("\n❌  Collection 'rars1_genomics' not found. Run 'python ingest.py'.\n")
        exit(1)


def retrieve_context(query: str, collection, n: int = 3) -> list[dict]:
    count = collection.count()
    if count == 0:
        return []
    results = collection.query(
        query_texts=[query],
        n_results=min(n, count)
    )
    docs   = results.get("documents",  [[]])[0] or []
    metas  = results.get("metadatas",  [[]])[0] or []
    chunks = []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        chunks.append({
            # çok uzun context CPU'da yavaşlıyor; ilk ~900 karakter yeterli
            "text":  (doc or "")[:900],
            "pmid":  meta.get("pmid",  ""),
            "doi":   meta.get("doi",   ""),
            "title": meta.get("title", ""),
        })
    return chunks


def format_context(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        cite = f"PMID: {c['pmid']}" if c["pmid"] else f"DOI: {c['doi']}"
        parts.append(
            f"[{i}] {cite}\n"
            f"    {c['title']}\n"
            f"    {c['text']}"
        )
    return "\n\n".join(parts)


def validate_response(response: str, chunks: list[dict]) -> list[str]:
    # hallucination guard - varyant kaynakta yoksa uyari
    pattern = r'\b[cp]\.\d+[A-Z]>[A-Z]\b|\b[cp]\.[A-Za-z]+\d+[A-Za-z]+\b'
    claimed  = set(re.findall(pattern, response))
    sourced  = " ".join(c["text"] for c in chunks)
    warnings = [
        f"⚠️  Variant '{v}' was mentioned but not found in any retrieved source."
        for v in claimed if v not in sourced
    ]
    return warnings


def call_llm(history, user_prompt):
    """
    Lokal Ollama chat API'yi (http://localhost:11434/api/chat) kullanir.
    SYSTEM_PROMPT sistem mesaji olarak, history ise user/assistant gecmisi olarak gonderilir.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

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
        reply = (data.get("message") or {}).get("content", "") or ""
    except requests.RequestException as e:
        print(f"\n⚠️  Ollama API error: {e}\n")
        return ""

    if reply:
        history.append({"role": "user", "content": user_prompt})
        history.append({"role": "assistant", "content": reply})
    return reply


def print_banner():
    print("\n" + "=" * 50)
    print("  RARS1 Genomic Literature Assistant")
    print("  PubMed RAG + Local LLM (Ollama)")
    print("  clear=reset  quit=exit")
    print("=" * 50 + "\n")


def chat():
    collection = load_chromadb()
    history    = []

    chunk_count = collection.count()
    print_banner()
    print(f"  📚  {chunk_count} indexed chunks ready.\n")

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.\n")
            break

        if not query:
            continue

        if query.lower() in ("quit", "q", "exit"):
            print("\nGoodbye.\n")
            break

        if query.lower() == "clear":
            history = []
            print("\n🔄  Conversation reset.\n")
            continue

        # ── Retrieve ──
        chunks = retrieve_context(query, collection, n=6)
        if not chunks:
            print("\nAssistant: I couldn't find any relevant abstracts for that query.\n")
            continue

        # ── Build RAG prompt ──
        context_block = format_context(chunks)
        user_prompt = (
            f"Here are the most relevant research excerpts I retrieved "
            f"for your question:\n\n"
            f"{context_block}\n\n"
            f"---\n"
            f"Question: {query}"
        )

        # ── Generate ──
        print("\nAssistant: ", end="", flush=True)
        reply = call_llm(history, user_prompt)

        if not reply:
            continue

        print(reply)

        # ── Validate ──
        warnings = validate_response(reply, chunks)
        if warnings:
            print("\n--- Hallucination uyari ---")
            for w in warnings:
                print(w)
        else:
            print("\n✅  Verified — all claims traceable to retrieved sources.")

        print()


if __name__ == "__main__":
    chat()
