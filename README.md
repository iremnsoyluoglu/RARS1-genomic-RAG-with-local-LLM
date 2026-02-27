## RARS1 Genomic-RAG
Bu projede RARS1 geni için PubMed + bioRxiv'den güncel literatürü çekip ChromaDB üzerinde vektör olarak saklayan ve lokal bir LLM (Ollama üzerinden, ör. `phi3:mini` / `gemma3:4b` / `llama3`) ile RAG tabanlı cevap üreten bir sistem kurdum.
PubMed tarafında retmax=50 kullanıyorum (en fazla 50 abstract), bioRxiv tarafında ise en fazla 20 pre-print özet alıyorum. Toplamda yaklaşık 70 (50 PubMed + 20 bioRxiv) abstract işleniyor (o anda bulunan sonuç sayısına göre biraz daha az olabilir).
Amaç, RARS1 ile ilişkili fenotipleri, hastalıkları ve spesifik varyantları kaynaklara (PMID / DOI) referans vererek özetlemek.Amaç, RARS1 ile ilişkili **fenotipleri**, **hastalıkları** ve **spesifik varyantları** kaynaklara (PMID / DOI) referans vererek özetlemek.

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
#  ENTREZ_EMAIL=
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
## Retrieval Ayarları
ChromaDB’den her soru için en fazla 3 doküman/chunk çekiyorum:
top_k = 3
Yani model yalnızca en ilgili 3 bilimsel snippet üzerinden cevap üretiyor.Eğer ChromaDB’den hiçbir sonuç dönmezse, LLM’e hiç gitmiyorum ve kullanıcıya:
I couldn't find any relevant abstracts for that query.
mesajı geliyor. Böylece “boş context + uydurma cevap” durumu oluşmuyor.

## 1. PubMed API rate limitlerini nasıl yönettim?
PubMed’e istek atarken Biopython’un Entrez arayüzünü kullanıyorum. Her esearch ve efetch çağrısından sonra küçük bir bekleme koyuyorum (time.sleep(0.4) gibi). Böylece saniyede yaklaşık 2–3 istek seviyesinde kalıyorum. NCBI API key tanımlandığında limit aslında daha yukarı çıkıyor (yaklaşık 10 req/sn), ama ben yine de aynı beklemeyi bırakıyorum. Böylece hem API key’siz hem de key’li kullanımda güvenli tarafta kalmış oluyorum ve rate limit’e takılma riskini minimize ediyorum.

## 2. Neden all-MiniLM-L6-v2 embedding modelini seçtim?
Burada amacım pratik, hızlı ve lokal çalışabilen bir çözüm kurmaktı. all-MiniLM-L6-v2 hafif bir model, CPU’da bile makul hızda çalışıyor ve ekstra API maliyeti gerektirmiyor. Biyomedikal özetler için semantik olarak yeterli performans veriyor. Daha domain-spesifik ve ağır modeller (örneğin BiomedBERT türevleri) bazı durumlarda daha iyi sonuç verebilir ama bu projede hız, sadelik ve kurulum kolaylığı benim için daha öncelikliydi. O yüzden bilinçli bir trade-off yaptım.

## 3. LLM’nin fenotip ile varyantı karıştırmamasını nasıl sağladım?
Burada iki katmanlı bir yaklaşım kullandım.
İlk olarak prompt seviyesinde, modelden fenotipleri (klinik gözlemler) ve varyantları (moleküler mutasyonlar) ayrı ayrı ve net biçimde ifade etmesini istiyorum. Yani ayrımı en baştan sistem mesajında tanımlıyorum.
İkinci olarak, modelin ürettiği cevabı otomatik olarak kontrol eden bir validate_response fonksiyonum var. Regex ile metindeki varyant ifadelerini (örneğin c.5A>G, p.Met1Thr gibi) çıkarıyorum ve bunların gerçekten retrieve edilen kaynak chunk’larda geçip geçmediğini kontrol ediyorum. Eğer model kaynakta olmayan bir varyant uydurmuşsa bunu işaretliyorum.
Yani sadece prompt’a güvenmiyorum; çıktı sonrası bir “hallucination guardrail” katmanı koyarak fenotip/varyant ayrımında modelin uydurma yapmasını teknik olarak da kontrol ediyorum.

## Çıktı Sonrası Guardrail
Modelin ürettiği cevabı validate_response fonksiyonu ile kontrol ediyorum:
Regex ile varyant ifadelerini (ör. c.5A>G, p.Met1Thr) çıkarıyorum
Bu varyantların gerçekten retrieve edilen chunk’larda geçip geçmediğini kontrol ediyorum
Kaynakta olmayan varyantlar için uyarı üretiyorum
Yani özellikle varyant iddiaları teknik olarak enforced ediliyor. Diğer cümleler için citation zorunluluğu prompt seviyesinde yönlendiriliyor ve cevap sonunda mutlaka şu formatta toplu kaynak listesi yer alıyor:
Sources consulted: PMID: 38618971, PMID: 37186453, ...
Cümle içinde ise doğal atıf formatı kullanılıyor:
... was associated with hypomyelinating leukodystrophy [PMID: 37186453].

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

## Hata Yönetimi
bioRxiv istekleri try/except ile sarılı; hata olursa boş liste dönüp ingest devam ediyor.
Ollama çağrıları requests.RequestException ile sarılı; hata olursa kullanıcıya "Ollama API error: ..." mesajı basılıyor ve chat tamamen çökmüyor.
PubMed Entrez çağrıları normal akışta; hata durumunda genişletilebilir.

## evaluate.py
**trick question** ve **eval_results.json** çıktısı için `evaluate.py` yazdım. Bu script, RAG pipeline'ını üç sabit soruyla (gerçek bilgi, “Is RARS1 associated with cystic fibrosis?” trick sorusu ve fenotip sorusu) çalıştırıp her cevabı kaynak ve pass/fail kriterine göre değerlendiriyor. Sonuçların tamamı `eval_results.json` dosyasına yazılıyor; konsolda da kısa bir ✓/✗ özeti görünüyor.

Bu proje, PubMed’den verileri dinamik olarak çekip anlamlı parçalara bölen, ChromaDB üzerinde vektör olarak indeksleyen ve RAG mimarisiyle cevap üreten bir Genomic-RAG uygulamasıdır. Üretilen cevaplar PMID/DOI referanslarıyla desteklenir ve halüsinasyonları azaltmak için güvenlik mekanizmaları içerir. Özellikle RARS1 geni üzerine odaklanarak doğruluk ve izlenebilirliği önceliklendiren bir yapı tasarlanmıştır.
#



