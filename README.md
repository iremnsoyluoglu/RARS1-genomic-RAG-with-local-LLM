# RARS1 Genomic-RAG

RARS1 geni üzerine yayımlanan literatürü dinamik olarak çekip, lokal bir LLM ile soru-cevap yapabilen bir RAG sistemi. Statik bir PDF'e ya da önceden hazırlanmış bir veri setine dayanmıyor — her çalıştırmada PubMed ve bioRxiv'den güncel verileri alıyor.

Odak noktası: fenotip, hastalık ve genetik varyantları birbirine karıştırmadan, her iddiayı bir PMID ya da DOI'ye bağlayarak sunmak.

---

## Dosyalar

| Dosya | Ne yapıyor |
|-------|-----------|
| `main.py` | Soru alıp ChromaDB'den ilgili chunk'ları çeken, sonra Ollama'ya gönderen ana döngü |
| `ingest.py` | PubMed + bioRxiv'den veri çekip ChromaDB'ye yazan script |
| `requirements.txt` | Bağımlılıklar |
| `evaluate.py` | 3 test sorusu çalıştırıp `eval_results.json` üreten script |
| `.env.example` | Hangi değişkenlerin gerektiğini gösteren şablon |
| `.gitignore` | `.env`, `chroma_db/` ve geçici dosyalar hariç |

---

## Kurulum

```bash
pip install -r requirements.txt
copy .env.example .env
```

`.env` dosyasını aç, şunları doldur:

```
ENTREZ_EMAIL=your@email.com
NCBI_API_KEY=          # opsiyonel ama rate limit için önerilir
OLLAMA_MODEL=phi3:mini
```

Ollama kurulu değilse → [ollama.com/download](https://ollama.com/download)

```bash
ollama pull phi3:mini   # ya da gemma3:4b / llama3
```

---

## Çalıştırma

```bash
python ingest.py     # önce bunu — veri tabanını hazırlar
python main.py       # sonra bunu — chat başlar
python evaluate.py   # opsiyonel — eval_results.json üretir
```

---

## Mimari

```
PubMed (Entrez) + bioRxiv  →  ingest.py  →  ChromaDB
                                                 ↓
                                            main.py (RAG)
                                                 ↓
                                       Ollama (lokal LLM)
                                                 ↓
                                      validate_response()
```

---

## Teknik Kararlar

**PubMed rate limitlerini nasıl yönettim?**

Her API çağrısının ardına `time.sleep(0.4)` koydum. Yani saniyede 2–3 istek civarında kalıyorum. NCBI API key varsa limit zaten 10 req/sn'ye çıkıyor ama beklemeyi kaldırmadım — key olmadan da sorunsuz çalışsın istedim. Gereksiz bir risk almak anlamsız geldi.

**Neden `all-MiniLM-L6-v2`?**

Açıkçası bu seçimde benim için en kritik şey lokalde, ekstra maliyet olmadan çalışmasıydı. Model hafif, CPU'da bile yavaşlamıyor ve biyomedikal özetlerde semantik olarak yeterince iyi iş çıkarıyor. BiomedBERT gibi domain-spesifik bir model daha doğru sonuçlar verebilir — bunu biliyorum — ama kurulum karmaşıklığı ve ağırlığı bu proje için fazlaydı. Bilinçli bir trade-off.

**LLM fenotip ile varyantı nasıl ayırt ediyor?**

İki ayrı katman var. İlki prompt: modelden fenotipleri ve varyantları ayrı başlıklar altında, ayrı mantıkla yazması isteniyor. İkincisi kod tarafında: `validate_response` fonksiyonu cevaptaki varyant ifadelerini (`c.5A>G`, `p.Met1Thr` gibi) regex ile çıkarıp bunların gerçekten kaynak chunk'larda geçip geçmediğini kontrol ediyor. Sadece prompt'a güvenmek yetmez — bu yüzden çıktı sonrası doğrulama da var.

---

## Retrieval

Her soruda ChromaDB'den en fazla **6 chunk** çekiyorum. Lokal LLM'nin context window'unu zorlamadan anlamlı bağlam sağlamak için bu sayı makul bir denge noktası.

ChromaDB'den hiç sonuç gelmezse LLM'e istek atmıyorum bile:

```
I couldn't find any relevant abstracts for that query.
```

Boş context üzerinden cevap üretmek en kötü senaryo olurdu.

---

## Evaluate

`evaluate.py` şu üç soruyu otomatik çalıştırır:

| Soru | Tür | Beklenen |
|------|-----|----------|
| "What variants in RARS1 cause leukodystrophy?" | Gerçek | PMID içeren cevap |
| "Is RARS1 associated with cystic fibrosis?" | **Trick** | "no evidence" demeli |
| "What neurological symptoms are seen in RARS1 patients?" | Fenotip | Fenotip bölümü + PMID |

Sonuçlar `eval_results.json`'a yazılır, konsolda ✓/✗ özeti görünür.

---

## Çıktı Formatı

Cümle içinde:
```
...associated with hypomyelinating leukodystrophy [PMID: 37186453].
```

Cevap sonunda:
```
Sources consulted: PMID: 38618971, PMID: 37186453, DOI: 10.1101/...
```

---

> Tıp alanında "bilmiyorum" her zaman uydurulmuş bir varyanttan daha iyi bir cevaptır. Sistem bu anlayış üzerine kuruldu.




