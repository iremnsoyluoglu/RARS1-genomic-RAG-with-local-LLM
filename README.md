# RARS1 Genomic-RAG

Bu projede, RARS1 geni için PubMed + bioRxiv'den güncel literatürü çekip ChromaDB üzerinde vektör olarak saklayan ve lokal bir LLM (Ollama üzerinden, ör. `phi3:mini` / `gemma3:4b` / `llama3`) ile RAG tabanlı cevap üreten bir sistem kurdum. Amaç, RARS1 ile ilişkili **fenotipleri**, **hastalıkları** ve **spesifik varyantları** kaynaklara (PMID / DOI) referans vererek özetlemek.

## Deliverables

- `main.py` – Sorgu motorunu çalıştıran giriş noktası
- `ingest.py` – PubMed API çağrılarını yapan script
- `requirements.txt` – Tüm bağımlılıklar
- `evaluate.py` – RAG pipeline'ını otomatik test eden script (trick question dahil 3 soru, sonuçlar `eval_results.json` dosyasına yazılır)
- `.gitignore` – `.env`, `chroma_db/`, geçici dosyalar vb. hariç tutulur

## Kurulum

```bash
pip install -r requirements.txt
copy .env.example .env
# .env içinde:
#  ENTREZ_EMAIL=senin@email
#  NCBI_API_KEY=...          (opsiyonel ama önerilir)
#  OLLAMA_MODEL=phi3:mini    # veya gemma3:4b / llama3
```

Ayrıca Ollama kurulu olmalı ve seçtiğim modelin lokal makinede indirilmiş olması gerekiyor:

```bash
ollama run phi3:mini   # model indir + test et, sonra Ctrl+C ile çık
```

## Çalıştırma

```bash
python ingest.py    # PubMed + bioRxiv -> chunk'lar -> ChromaDB
python main.py      # RAG chat (lokal LLM ile)
python evaluate.py  # eval_results.json üretir, trick question dahil
```

## PubMed API rate limit'i nasıl yönettim?

Ingestion sırasında her Entrez çağrısından sonra `time.sleep(0.4)` kullanıyorum.  
NCBI'nin varsayılan limiti ~3 req/sn, `NCBI_API_KEY` sağlandığında bu ~10 req/sn'ye çıkıyor.  
Böylece script hem anonim hem de API key'li kullanımda limitleri makul bir tamponla koruyor.

## Neden all-MiniLM-L6-v2 embedding?

- Lokal çalışıyor, ekstra API maliyeti yok.
- Biomedikal metinler için yeterli performans veriyor.
- Production ortamında daha spesifik bir biomedikal model (`BiomedNLP-BiomedBERT-base` vb.) tercih edilebilir; fakat bu görev için hız / maliyet dengesi açısından `all-MiniLM-L6-v2` daha mantıklıydı.

## Phenotype vs variant ayrımını nasıl sağladım?

- System prompt içinde modelden açıkça **phenotypes (klinik gözlemler)** ve **variants (moleküler mutasyonlar)** için ayrı satırlar/ifadeler kullanmasını istiyorum.
- Cevap üretildikten sonra `validate_response` fonksiyonu:
  - Regex ile tüm varyant adaylarını çekiyor (ör. `c.5A>G`, `p.Met1Thr` vb.).
  - Bu varyantların gerçekten retrieve edilen kaynak chunk'larda geçip geçmediğini kontrol ediyor.
  - Kaynakta olmayan her varyant için uyarı mesajı üretiyor (hallucination guardrail). Böylece modelin ürettiği iddia ikinci bir katmanla doğrulanmış oluyor.

## Mimari

```
PubMed (Entrez) + bioRxiv  -->  ingest.py  -->  ChromaDB (rars1_genomics)
                                        |
                                        v
                                   main.py (RAG)
                                        |
                            local LLM via Ollama API
                                        |
                               validate_response (guardrail)
```

## Chunking stratejim

- Varyant isimlerinin (`c.5A>G`, `p.Met1Thr` vb.) chunk sınırında bölünmemesi için önce regex ile tespit edip her birini `__VAR_i__` placeholder'ına çeviriyorum.
- Abstract'ı cümlelere ayırıp 2 cümlelik bloklar halinde chunk'luyorum.
- Chunk'lar oluşturulduktan sonra placeholder'ları orijinal varyant isimleri ile geri değiştiriyorum.
- Her chunk'ı, ilgili makaleye ait `pmid`, `doi`, `title`, `source`, `chunk_index` metadataları ile birlikte ChromaDB'ye yazıyorum.

## evaluate.py

Görevde istenen **trick question** ve **eval_results.json** çıktısı için `evaluate.py` yazdım. Bu script, RAG pipeline'ını üç sabit soruyla (gerçek bilgi, “Is RARS1 associated with cystic fibrosis?” trick sorusu ve fenotip sorusu) çalıştırıp her cevabı kaynak ve pass/fail kriterine göre değerlendiriyor. Sonuçların tamamı `eval_results.json` dosyasına yazılıyor; konsolda da kısa bir ✓/✗ özeti görünüyor.

Bu proje, görev dokümanındaki teknik gereksinimleri (dinamik PubMed ingest, chunking, vektör veritabanı, RAG cevabı, PMID/DOI citation, hallucination guardrail ve trick question değerlendirmesi) lokal ve ücretsiz bir LLM ile yerine getirecek şekilde tasarladığım RARS1 odaklı bir Genomic-RAG sistemidir.
