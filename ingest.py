# RARS1 literatürünü PubMed + bioRxiv'den çekip ChromaDB'ye yükler

from Bio import Entrez, Medline
import chromadb
from chromadb.utils import embedding_functions
from chromadb.config import Settings
import requests
import time
import re
import os
import json
from dotenv import load_dotenv

load_dotenv()
if not os.getenv("ENTREZ_EMAIL"):
    raise ValueError("ENTREZ_EMAIL not found in .env file!")
Entrez.email = os.getenv("ENTREZ_EMAIL")
Entrez.api_key = os.getenv("NCBI_API_KEY")


def fetch_pubmed_abstracts():
    search = Entrez.esearch(
        db="pubmed",
        term="RARS1[Gene Name] OR RARS1 leukodystrophy OR RARS1 aminoacyl tRNA synthetase",
        retmax=50,  # PDF: 20-50 abstracts
        sort="pub date"
    )
    ids = Entrez.read(search).get("IdList", [])
    search.close()
    time.sleep(0.4)

    if not ids:
        return []

    fetch = Entrez.efetch(db="pubmed", id=ids, rettype="medline", retmode="text")
    records = list(Medline.parse(fetch))
    fetch.close()
    time.sleep(0.4)

    results = []
    for r in records:
        if r.get("AB"):
            results.append({
                "pmid": str(r.get("PMID", "") or ""),
                "title": r.get("TI", ""),
                "abstract": r.get("AB", ""),
                "pub_date": r.get("DP", ""),
                "source": "pubmed",
                "doi": ""
            })
    return results


def fetch_biorxiv_abstracts():
    url = "https://api.biorxiv.org/details/biorxiv/RARS1/0/20"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    results = []
    for item in data.get("collection", []):
        if item.get("abstract"):
            results.append({
                "pmid": "",
                "title": item.get("title", ""),
                "abstract": item.get("abstract", ""),
                "pub_date": item.get("date", ""),
                "source": "biorxiv",
                "doi": item.get("doi", "")
            })
    return results


def chunk_abstract(text, metadata):
    variant_pattern = r'[cp]\.\d+[A-Z]>[A-Z]|[cp]\.[A-Za-z]+\d+[A-Za-z]+|\([Pp]\.[A-Za-z]+\d+[A-Za-z]+\)'
    variants_found = re.findall(variant_pattern, text)
    protected = text
    placeholder_map = {}
    for i, v in enumerate(variants_found):
        placeholder = f"__VAR_{i}__"
        placeholder_map[placeholder] = v
        protected = protected.replace(v, placeholder, 1)

    sentences = [s.strip() for s in protected.split(". ") if len(s.strip()) > 20]
    if not sentences:
        return []

    chunks = []
    for i in range(0, len(sentences), 2):
        chunk_text = ". ".join(sentences[i:i+2])
        if not chunk_text.endswith("."):
            chunk_text += "."
        for placeholder, original in placeholder_map.items():
            chunk_text = chunk_text.replace(placeholder, original)
        chunks.append({
            "text": chunk_text,
            "metadata": {
                "pmid": metadata.get("pmid", ""),
                "doi": metadata.get("doi", ""),
                "title": metadata.get("title", ""),
                "source": metadata.get("source", ""),
                "chunk_index": i // 2
            }
        })
    return chunks


def store_in_chromadb(all_chunks):
    client = chromadb.PersistentClient(
        path="./chroma_db",
        settings=Settings(anonymized_telemetry=False, allow_reset=True),
    )
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    try:
        client.delete_collection("rars1_genomics")
    except Exception:
        pass

    collection = client.create_collection("rars1_genomics", embedding_function=ef)

    texts, metadatas, ids = [], [], []
    for i, chunk in enumerate(all_chunks):
        raw_id = f"chunk_{chunk['metadata']['source']}_{chunk['metadata']['pmid'] or chunk['metadata']['doi']}_{chunk['metadata']['chunk_index']}_{i}"
        clean_id = re.sub(r'[^a-zA-Z0-9_-]', '_', raw_id)
        texts.append(chunk["text"])
        metadatas.append(chunk["metadata"])
        ids.append(clean_id)

    batch_size = 50
    for i in range(0, len(texts), batch_size):
        collection.add(
            documents=texts[i:i+batch_size],
            metadatas=metadatas[i:i+batch_size],
            ids=ids[i:i+batch_size]
        )
    print(f"  → {len(texts)} chunk ChromaDB'ye yazıldı")


def main():
    pubmed = fetch_pubmed_abstracts()
    print(f"  PubMed: {len(pubmed)} özet")

    biorxiv = fetch_biorxiv_abstracts()
    print(f"  bioRxiv: {len(biorxiv)} özet")

    all_records = pubmed + biorxiv
    all_chunks = []
    for record in all_records:
        chunks = chunk_abstract(record["abstract"], record)
        all_chunks.extend(chunks)

    print(f"  Toplam {len(all_chunks)} chunk")
    if all_chunks:
        store_in_chromadb(all_chunks)

    with open("raw_abstracts.json", "w", encoding="utf-8") as f:
        json.dump(all_records, f, indent=2, ensure_ascii=False)
    print("  raw_abstracts.json kaydedildi")


if __name__ == "__main__":
    print("\nRARS1 veri çekme başlıyor...\n")
    main()
    print("\nBitti.\n")
