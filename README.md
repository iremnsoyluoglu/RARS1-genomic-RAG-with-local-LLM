# RARS1 Genomic-RAG System

Bu projede RARS1 geni için PubMed + bioRxiv'den güncel literatürü çekip ChromaDB üzerinde vektör olarak saklayan ve **lokal bir LLM** (Ollama üzerinden, ör. `phi3:mini` / `gemma3:4b` / `llama3`) ile RAG tabanlı cevap üreten bir sistem kurdum.

PubMed tarafında `retmax=50` kullanıyorum (en fazla 50 abstract), bioRxiv tarafında ise en fazla 20 pre-print özet alıyorum. Toplamda yaklaşık 70 abstract işleniyor (o anda bulunan sonuç sayısına göre biraz daha az olabilir).

Amaç, RARS1 ile ilişkili **fenotipleri**, **hastalıkları** ve **spesifik varyantları** kaynaklara (PMID / DOI) referans vererek özetlemek.

---

## Deliverables

| Dosya | Görev |
|-------|-------|
| `main.py` | Sorgu motorunu çalıştıran giriş noktası |
| `ingest.py` | PubMed + bioRxiv API çağrılarını yapan script |
| `requirements.txt` | Tüm bağımlılıklar |
| `evaluate.py` | RAG pipeline'ını otomatik test eden script (trick question dahil 3 soru, sonuçlar `eval_results.json`'a yazılır) |
| `.env.example` | API key şablonu |
| `.gitignore` | `.env`, `chroma_db/`, geçici dosyalar hariç tutulur |

---

## Gereksinimler

| Gereksinim | Zorunlu | Notlar |
|------------|---------|--------|
| Python 3.10+ | ✅ | `python --version` ile kontrol et |
| Ollama | ✅ | [ollama.com/download](https://ollama.com/download) |
| `ENTREZ_EMAIL` | ✅ | Herhangi bir geçerli e-posta |
| `NCBI_API_KEY` | ⚡ Opsiyonel | Rate limit'i 3 → 10 req/sn'ye çıkarır |
| GPU | ❌ | CPU'da da çalışır |

---

## Kurulum

```bash
# 1. Bağımlılıkları kur
pip install -r requirements.txt

# 2. .env dosyasını oluştur
copy .env.example .env
```

`.env` dosyanı aç ve şu değerleri doldur:

```
ENTREZ_EMAIL=your@email.com
NCBI_API_KEY=optional_but_recommended
OLLAMA_MODEL=phi3:mini
```

```bash
# 3. Ollama'yı kur (henüz kurulu değilse): https://ollama.com/download

# 4. Modeli indir ve test et
ollama pull phi3:mini

# (opsiyonel alternatifler)
ollama pull gemma3:4b
ollama pull llama3
```

---

## Çalıştırma

```bash
# Adım 1 — Veri tabanını hazırla (bir kez çalıştır)
python ingest.py

# Adım 2 — RAG chat'i başlat
python main.py

# Adım 3 — Otomatik değerlendirme (opsiyonel)
python evaluate.py
```

---

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

---

## Veri Akışı

### 1. Ingestion (`ingest.py`)
- **PubMed**: `RARS1[Gene Name] OR RARS1 leukodystrophy OR RARS1 aminoacyl tRNA synthetase` sorgusuyla en fazla 50 abstract çekilir
- **bioRxiv**: RARS1 endpoint'inden en fazla 20 pre-print özet alınır
- **Chunking**: Varyant isimleri korunarak 2 cümlelik parçalara bölünür (detay aşağıda)
- **Embedding**: `all-MiniLM-L6-v2` ile vektörleştirilip ChromaDB'ye yazılır
- Ham veriler `raw_abstracts.json` olarak da kaydedilir

### 2. Chat (`main.py`)
- Kullanıcı sorusu → ChromaDB'den en yakın **6 chunk** (top_k = 6)
- Chunk'lar + soru → Ollama üzerinden lokal LLM'e gönderilir
- Konuşma geçmişi saklanır; `clear` komutuyla sıfırlanır
- ChromaDB'den hiç sonuç dönmezse LLM'e gidilmez, kullanıcıya doğrudan şu mesaj verilir:

  ```
  I couldn't find any relevant abstracts for that query.
  ```

### 3. Evaluation (`evaluate.py`)
Üç sabit soru çalıştırılır, sonuçlar `eval_results.json`'a yazılır:

| # | Soru | Tür | Geçme Kriteri |
|---|------|-----|---------------|
| 1 | "What variants in RARS1 cause leukodystrophy?" | Gerçek | Cevap PMID içermeli |
| 2 | "Is RARS1 associated with cystic fibrosis?" | **Trick** | "no evidence" / "not found" içermeli |
| 3 | "What neurological symptoms are seen in RARS1 patients?" | Fenotip | Fenotip bölümü + PMID içermeli |

---

## Retrieval Ayarları

ChromaDB'den her soru için en fazla **6 chunk** çekiyorum (`top_k = 6`). Bu, PDF'teki "5–6 chunk" önerisiyle uyumludur ve lokal LLM'nin context window'unu aşmadan yeterli bağlam sağlar.

---

## Tasarım Kararları

### 1. PubMed API Rate Limitlerini Nasıl Yönettim?

Biopython'un Entrez arayüzünü kullanıyorum. Her `esearch` ve `efetch` çağrısından sonra `time.sleep(0.4)` koyuyorum — bu, saniyede ~2–3 istek seviyesinde tutuyor. `NCBI_API_KEY` tanımlandığında limit 10 req/sn'ye çıkıyor, ama güvenli tarafta kalmak için beklemeyi her durumda bırakıyorum.

### 2. Neden `all-MiniLM-L6-v2` Embedding Modeli?

Amacım pratik, hızlı ve lokal çalışabilen bir çözüm kurmaktı. Bu model hafif, CPU'da bile makul hızda çalışıyor ve ekstra API maliyeti gerektirmiyor. Biyomedikal özetler için semantik olarak yeterli performans veriyor. Domain-spesifik modeller (örn. BiomedBERT) bazı durumlarda daha iyi sonuç verebilir, ancak bu projede **hız, sadelik ve kurulum kolaylığı** daha öncelikliydi — bilinçli bir trade-off.

### 3. LLM Fenotip ile Varyantı Nasıl Ayırt Ediyor?

İki katmanlı yaklaşım kullandım:

**Prompt seviyesinde:** Sistem mesajında modelden fenotipleri (klinik gözlemler) ve varyantları (moleküler mutasyonlar) ayrı bölümler halinde ifade etmesi isteniyor.

**Çıktı sonrası guardrail:** `validate_response` fonksiyonu regex ile cevaptaki varyant ifadelerini (`c.5A>G`, `p.Met1Thr` vb.) çıkarıp bunların gerçekten retrieve edilen chunk'larda geçip geçmediğini kontrol ediyor. Kaynakta olmayan varyantlar işaretleniyor.

Yani sadece prompt'a güvenmiyorum, teknik bir doğrulama katmanı da var.

---

## Chunking Stratejisi

1. Varyant isimleri (`c.5A>G`, `p.Met1Thr` vb.) regex ile tespit edilip `__VAR_i__` placeholder'ına çevrilir
2. Abstract cümlelere ayrılıp 2 cümlelik bloklar halinde chunk'lanır
3. Placeholder'lar orijinal varyant isimleriyle geri değiştirilir
4. Her chunk `pmid`, `doi`, `title`, `source`, `chunk_index` metadata'larıyla ChromaDB'ye yazılır

Bu sayede hiçbir varyant ismi chunk sınırında bölünmez.

---

## Hata Yönetimi

- **bioRxiv**: `try/except` ile sarılı — hata olursa boş liste dönüp ingest devam eder
- **Ollama**: `requests.RequestException` ile sarılı — hata olursa `"Ollama API error: ..."` mesajı basılır, sistem çökmez
- **Boş context**: ChromaDB'den sonuç dönmezse LLM'e hiç gidilmez, uydurma cevap riski sıfırlanır

---

## Çıktı Formatı

Cümle içinde doğal atıf:
```
... was associated with hypomyelinating leukodystrophy [PMID: 37186453].
```

Cevap sonunda toplu kaynak listesi:
```
Sources consulted: PMID: 38618971, PMID: 37186453, DOI: 10.1101/...
```

---






