# Báo cáo cá nhân — Day 6

**Phạm Tuấn Cường · 2A202603584 · L3A.** Thời điểm chạy: 2026-11-13, khoảng 10:36–10:50 (UTC+7).

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang.**
  - Nguồn: OpenStax _Introduction to Computer Science_ (Rice University). PDF lấy từ `assets.openstax.org/.../Introduction_To_Computer_Science_-_WEB.pdf` ngày 2026-11-13T03:20:25Z; sha256 ghi trong manifest.
  - Giấy phép: **CC BY-NC-SA 4.0**, theo trường `license_name` của OpenStax CMS API. Bài lab là mục đích giáo dục, phi thương mại, có ghi nguồn.
  - PDF có 939 trang vật lý. Chỉ dùng phần thân bài của **chương 5** (tr. 204–239) và **chương 6** (tr. 250–294). Đã loại trang mở chương (203, 249: outline chương và hình bìa) và _Chapter Review_ (240–248, 295–306).
  - Quy tắc đếm: một trang được tính khi nằm trong các phạm vi trên **và** có ≥ 1.000 ký tự sau chuẩn hóa. Trang 239 (379 ký tự) và 265 (936 ký tự) bị loại và đã ghi vào `results/errors.log`.
  - Kết quả: **79 trang nội dung**, 231.219 ký tự. `page` luôn là số trang vật lý của PDF (1-based), không phải số trang in.
  - Chi tiết từng trang nằm trong [data/manifest.json](../../data/manifest.json). Text đã chuẩn hóa nằm trong [data/pages.jsonl](../../data/pages.jsonl), được phép chia sẻ theo CC BY-NC-SA, có ghi nguồn. PDF gốc không commit vì nặng 56 MB; xem manifest để tải lại.
- **Chuẩn hóa, lỗi và giới hạn.**
  - Thư viện đọc: PyMuPDF 2.1, đọc theo block. Không cần OCR vì PDF là bản số gốc.
  - Các bước chuẩn hóa:
    - Unicode NFC và thay ligature.
    - Bỏ soft hyphen và NBSP; nối từ bị gạch nối cuối dòng.
    - Gộp khoảng trắng trong dòng, giữ dòng trống làm ranh giới đoạn.
    - Bỏ header/footer theo vị trí và cỡ chữ 7.5pt.
    - Bỏ credit `(attribution: … license)` trong chú thích hình, kể cả phần credit bị tách qua trang (gặp ở các trang 257, 262/263, 275/276).
  - Không có trang nào trích xuất lỗi; có 2 trang bị loại vì ít chữ.
  - Giới hạn:
    - Bảng bị làm phẳng thành dòng text, ví dụ Table 5.1.
    - Hình không được mô tả, chỉ giữ chú thích.
    - Chunk không vượt qua ranh giới trang, nên câu bị ngắt ở chỗ sang trang bị tách đôi.
  - Đối chiếu độc lập: với 54/54 bản ghi top-3 của test, một đoạn 6 từ của chunk được tìm thấy trên đúng trang đó khi trích lại bằng **pypdf**, một extractor khác PyMuPDF.
- **Embedding, vector store, lệnh chạy và chi phí.**
  - Model: `intfloat/multilingual-e5-small`, chạy local qua sentence-transformers 6.3.0, transformers 5.22.2, torch 2.15.0+cpu. Vector **384 chiều**, L2-normalize; document có prefix `passage: `, query có prefix `query: `.
  - Chạy trên **CPU** vì ổ C chỉ còn khoảng 2 GB, không đủ chỗ cho torch bản CUDA.
  - Vector store: PostgreSQL 16.16 + **pgvector 0.8.7**, dựng bằng Docker theo starter. Một bảng `chunks` với cột `strategy`, metric cosine (`<=>`), **exact search** (không tạo index HNSW/IVF, vì chỉ có vài trăm dòng mỗi chiến lược).
  - Chi phí: **0 USD**. Thời gian ingest lần đầu: A 13,6 s, B 12,9 s, chủ yếu là thời gian embed. Truy vấn 15 câu mất khoảng 0,6 s cho mỗi chiến lược.
  - Lệnh chạy: xem [README.md](../../README.md#bài-làm).
- **Metadata.**
  - Bắt buộc: `document_id`, `source`, `page`.
  - Bổ sung:
    - `chapter` (int): trường filter.
    - `section` (text, ví dụ `"6.3"`) và `section_title`.
    - `char_start` và `char_end`: vị trí của chunk trong text trang.
  - Nguồn giá trị: `chapter` và `section` lấy từ outline/bookmark của PDF cộng với heading section phát hiện trong trang (font RobotoCondensed-Bold khoảng 15,6pt). Không có giá trị nào được đoán.
  - Lý do chọn `chapter`: nhiều khái niệm được định nghĩa ở **cả hai chương**, ví dụ virtual memory và scheduling (tr. 214, chương 5, và chương 6), hay SSD (tr. 233–234 và 288). Ngữ cảnh "đang học chương X" là một phạm vi tự nhiên và có giá trị phân biệt được.

## Cấu hình và benchmark

- **A / B / C.** Tham số cố định trong [starter/src/config.py](../../starter/src/config.py) trước khi chạy.
  - **A:** chunk cố định 500 ký tự, overlap 50, trong phạm vi một trang. Không filter.
  - **B:** chunk theo đoạn và heading. Gộp các đoạn liền kề đến tối đa 1.000 ký tự; đoạn quá dài thì tách theo câu. Không filter.
  - **C:** dùng **lại đúng index và vector của B**, chỉ khác là áp dụng filter `chapter` cho 4/21 câu có filter. 17 câu còn lại chạy y như B.
  - A–B chỉ khác chunking. B–C chỉ khác filter.
- **Benchmark.**
  - 21 câu, nằm trong [benchmark/questions.jsonl](../../benchmark/questions.jsonl): **15 dev / 6 test**.
  - Loại câu: 7 direct, 6 paraphrase, 4 condition và 4 metadata_filter (d14 và d15 ở dev; t05 và t06 ở test).
  - Test lấy chủ yếu từ section 5.6 và 6.6, không có câu dev nào thuộc hai section này. t05 và t06 nằm gần chủ đề của dev (6.3), đây là nguy cơ rò rỉ đã ghi trong [benchmark/README.md](../../benchmark/README.md).
  - Câu hỏi do AI soạn nháp từ text đã chuẩn hóa. Evidence được kiểm chứng bằng `python -m src.benchmark_check`: mỗi quote phải là chuỗi con của trang gold, giá trị filter phải tồn tại và trang gold phải thuộc đúng chương của filter.
  - Benchmark được commit `4c5ab6d` lúc 10:39, **trước** lần chạy truy xuất đầu tiên.
- **Tiêu chí chọn chiến lược** ([benchmark/selection_criteria.md](../../benchmark/selection_criteria.md)), commit cùng benchmark:
  - Thứ tự xét: Hit@3 dev, rồi Hit@1 dev, rồi tuân thủ filter trên dev, cuối cùng là tài nguyên.
  - Kết quả chọn **C** được commit `8f09c53` lúc 10:43, **trước** khi chạy test. Test chỉ chạy một lần và không có gì bị chỉnh sau đó.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count   | Thời gian                   | Chi phí |
| -------- | ----- | ----------- | -------------------- | ------------- | --------------------------- | ------- |
| A        | dev   | 12/15       | 14/15                | 538           | ingest 13,6 s; query 0,62 s | 0       |
| A        | test  | 6/6         | 6/6                  | 538           | query 0,26 s                | 0       |
| B        | dev   | 13/15       | 14/15                | 323           | ingest 12,9 s; query 0,66 s | 0       |
| B        | test  | 5/6         | 6/6                  | 323           | query 0,24 s                | 0       |
| C        | dev   | 13/15       | 14/15                | 323 (index B) | query 0,66 s                | 0       |
| C        | test  | 5/6         | 6/6                  | 323 (index B) | query 0,25 s                | 0       |

Phân bố độ dài chunk (ký tự):

- A: min 52, median 500, mean 472, max 500; tổng 253.992 ký tự, lớn hơn corpus vì có overlap.
- B: min 59, median 768, mean 714, max 998; tổng 230.758 ký tự.

| Strategy | Coherence trung bình /2 (n)           | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A)                       | Grounding 0/1/2 (số câu) và trung bình /2 |
| -------- | ------------------------------------- | ------------------------- | ---------------------------------------------------- | ----------------------------------------- |
| A        | 1,30 (10): 7 câu điểm 1, 3 câu điểm 2 | 18/18                     | test 2/2 (A không lọc, tuân thủ do tình cờ); dev 0/2 | 0/0/6, 2,00                               |
| B        | 1,90 (10): 1 câu điểm 1, 9 câu điểm 2 | 18/18                     | test 1/2 (t05 có chunk chương 5 ở hạng 3); dev 1/2   | 0/0/6, 2,00                               |
| C        | 1,90 (10), cùng chunk với B           | 18/18                     | **test 2/2; dev 2/2**                                | 0/0/6, 2,00                               |

_Cách có nhãn: AI đề xuất nhãn nháp, sau đó tác giả duyệt toàn bộ 92 dòng (20 coherence, 18 grounding, 54 metadata), giữ nguyên tất cả, không sửa dòng nào. Các file ghi `labeled_by = author-reviewed`. Bảng được tổng hợp bằng `python -m src.audit_summary`._

**Đường dẫn trace, nhãn thủ công và cách chọn mẫu.**

- Trace đầy đủ nằm ở `results/traces_{A,B,C}_{dev,test}.jsonl`. Mỗi dòng gồm câu hỏi, filter đã áp dụng, top-3 với chunk_id, text, score, metadata, cờ hit cho từng kết quả, và gold.
- Số liệu tổng hợp nằm ở `results/summary.json` và `results/ingest_stats.json`.
- Kiểm tra nạp lại và tài liệu đổi:
  - `results/reingest_check.json`: lần nạp thứ hai ghi 0 dòng, số dòng giữ nguyên 538/323.
  - `results/change_check.json`: trên bảng tạm, khi tài liệu đổi thì 5 chunk cũ bị xóa và 2 chunk thay đổi được ghi lại.
- Nhãn thủ công: `results/audit/coherence.csv`, `metadata_audit.csv`, `grounding.csv`; tổng hợp ở `audit_summary.json`.
- Cách chọn mẫu coherence: **10 page ID đầu tiên đã sắp xếp** (tr. 204–213). Trên mỗi trang, vị trí mẫu là điểm giữa của đoạn đầu tiên dài ≥ 200 ký tự. Mẫu được cố định trong code trước khi chấm.
- Cách chấm metadata:
  - `page`: đối chiếu bằng pypdf.
  - `chapter` và `section`: đối chiếu với phạm vi trang trong outline. 11 bản ghi nằm trên trang chuyển section được kiểm thêm theo vị trí heading.
- Grounding: chấm 6 câu test × 3 chiến lược.

## Phân tích và kết luận

- **A–B (chỉ đổi chunking).**
  - Retrieval: gần như hòa. Hit@1 tổng cộng 18/21 cho cả A và B: A thua 1 câu ở dev nhưng thắng 1 câu ở test. Hit@3 là 20/21 cho cả hai.
  - Khác biệt rõ nhất là **coherence**: 1,9 so với 1,3. 7/10 chunk của A cắt giữa câu hoặc giữa từ, ví dụ pos05 cắt ở "with a fa", pos10 cắt ở "this instru".
  - B dùng ít hơn **40% chunk** (323 so với 538) với thời gian embed tương đương.
  - Đổi lại, chunk B dài hơn nên dễ bị loãng nghĩa với câu hỏi hẹp. Xem ví dụ t03 bên dưới.
- **B–C (chỉ đổi filter).**
  - Hit@1 và Hit@3 **không đổi** ở cả dev lẫn test: trong 4 câu filter, không câu nào đổi trạng thái hit.
  - Filter chỉ thay các chunk ngoài phạm vi ở hạng 2–3. Ví dụ ở t05, B có chunk tr. 233 (chương 5) ở hạng 3, còn C thay bằng tr. 289 (chương 6).
  - Tuân thủ filter tăng từ 1/2 lên 2/2 ở cả dev và test. Lợi ích thực tế của filter ở đây là **giữ đúng phạm vi** cho ngữ cảnh truyền vào LLM, không phải tăng Hit.
- **Ví dụ lỗi 1: d15 trượt ở cả A, B và C.**
  - Câu hỏi: "What does scheduling mean?", filter chương 6. Gold là tr. 272: "Choosing which process to run next is called scheduling."
  - Top-3 của B/C đều là tr. 274, gồm Figure 6.21 về context switching, round-robin và "A good scheduling algorithm…". Score 0,865/0,860/0,859, bám rất sát nhau.
  - Câu hỏi ngắn, chung chung, nên khớp với đoạn về _thuật toán_ scheduling nhiều hơn câu định nghĩa. Filter không giúp được vì mọi ứng viên đều đã thuộc chương 6.
  - Cách cải thiện có thể là hybrid BM25 hoặc reranker; chưa thử.
- **Ví dụ lỗi 2: t03 ở B/C, hit ở hạng 3, trong khi A hit ở hạng 1.**
  - Câu hỏi: "What does a journaling file system do?" Gold là tr. 292.
  - Chunk B chứa định nghĩa dài khoảng 1.000 ký tự, mở đầu bằng đoạn về fsck và pointer validation. Định nghĩa journaling nằm ở cuối chunk, nên embedding bị loãng.
  - Hai chunk chung chung về file system ở tr. 284–285 xếp trên nó. Chunk 500 ký tự của A tập trung hơn nên lên hạng 1.
  - Một lỗi tương tự trên dev: d01 ở A hit ở hạng 3, vì hạng 1 cùng trang gold nhưng chỉ chứa nửa evidence.
- **Chiến lược chọn: C (= B + filter `chapter`).**
  - Lý do: theo tiêu chí đã chốt, Hit@3 hòa, Hit@1 dev thì B = C > A, và tuân thủ filter thì C > B. Thêm vào đó C có coherence cao nhất và ít chunk hơn A.
  - Kết quả test **không xác nhận** C tốt hơn A về Hit@1: A đạt 6/6, C đạt 5/6. Chênh lệch 1 câu nằm trong sai số của mẫu nhỏ.
  - Kết luận chỉ nên hiểu là: với corpus này, chunk theo đoạn cho chunk mạch lạc hơn với chi phí thấp hơn, còn filter chương giữ đúng phạm vi khi người dùng cung cấp ngữ cảnh. Nên áp dụng khi corpus có heading rõ và câu hỏi đi kèm phạm vi đáng tin.
- **Hạn chế.**
  - Test chỉ có 6 câu và dev 15 câu, nên mỗi câu chiếm khoảng 7–17 điểm phần trăm. Không thể tuyên bố chiến lược nào tốt hơn một cách tổng quát.
  - Benchmark do AI soạn từ chính text đã chuẩn hóa. Câu hỏi thường dùng lại từ ngữ của nguồn, nên dễ hơn câu hỏi thật; grounding đạt 2,0 ở cả ba chiến lược cho thấy test chưa đủ khó để phân biệt.
  - Định nghĩa hit dùng so khớp chuỗi trên một trang gold, nên một trang khác có nội dung tương đương sẽ không được tính. Ví dụ tr. 214 chương 5 cũng định nghĩa scheduling, nhưng câu d15 đã giới hạn phạm vi ở chương 6.
  - Nhãn thủ công là nháp AI do tác giả duyệt lại, không phải chấm độc lập từ đầu. Tác giả không sửa nhãn nào, nên có nguy cơ bị neo theo nháp. Ngoài ra, người chấm cũng chính là tác giả.
  - Mẫu coherence lấy theo đoạn văn, nên tự nhiên có lợi cho B.
  - Thời gian đo trên một lần chạy, trên laptop dùng CPU, không lặp lại.
- **Nếu làm lại hoặc mở rộng.**
  - Cho chunk B lặp lại heading ở đầu và không để heading treo ở cuối chunk.
  - Cho phép nối câu bị ngắt ở ranh giới trang, và ghi `page_end`.
  - Thêm câu hỏi khó hơn: diễn đạt xa nguồn, câu cần nhiều chunk.
  - Thử hybrid BM25 + dense và chỉnh trên dev.
  - Chạy lại trên GPU để so sánh thời gian.

## Sử dụng AI

- Đã dùng Claude Code (Claude Opus 5.5) để viết code pipeline, soạn nháp 21 câu hỏi kèm evidence, đề xuất nhãn audit nháp và viết báo cáo này.
- Cách kiểm tra:
  - Evidence được kiểm bằng script.
  - Metadata được kiểm bằng một extractor độc lập (pypdf) và outline của PDF.
  - Mọi số liệu trong báo cáo lấy từ file trong `results/`, sinh ra từ các lệnh đã chạy.
  - Tác giả đã duyệt toàn bộ 92 dòng nhãn audit và giữ nguyên các nhãn nháp.
