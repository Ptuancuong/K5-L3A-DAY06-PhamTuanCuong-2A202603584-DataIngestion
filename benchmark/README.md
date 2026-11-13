# Benchmark

`questions.jsonl` — 21 câu (15 dev / 6 test), được viết và chia **trước khi chạy bất kỳ truy xuất nào**.

Mỗi câu có các trường `id, split, type, question, expected_answer, gold_source_id, gold_page, evidence_quote, filter`. Câu có filter có thêm `filter_context`.

- `gold_page` là **số trang vật lý của PDF** (1-based), trùng với `page` trong `data/pages.jsonl`. Đây không phải số trang in trên sách.
- `gold_page` và `evidence_quote` là list. Một kết quả được tính là hit khi chunk nằm ở **một** trang gold và chứa **trọn ít nhất một** evidence quote. Với `t06` có hai định nghĩa hợp lệ, ở trang 254 và 271.

## Phân bố

| Loại                 | Dev                              | Test                             |
| -------------------- | -------------------------------- | -------------------------------- |
| direct               | d05, d07, d08, d09, d13          | t01, t03                         |
| paraphrase           | d01, d02, d06, d10, d11          | t02                              |
| condition / ngoại lệ | d03, d04, d12                    | t04                              |
| metadata_filter      | d14 (chapter 5), d15 (chapter 6) | t05 (chapter 6), t06 (chapter 6) |

## Cách chia và nguy cơ rò rỉ

- Có 4 câu filter, trong đó 2 câu ở test. Các câu này được chọn vì khái niệm xuất hiện ở **cả hai chương**:
  - _virtual memory_ và _scheduling_ được định nghĩa ở cả trang 214 (chương 5) và chương 6.
  - _SSD_ được giải thích ở cả trang 233–234 (chương 5) và trang 288 (chương 6).
  - _thread_ có mặt ở trang 238 (chương 5) và chương 6.
- Giá trị filter là **input giả định của người dùng, cho trước khi truy xuất** ("đang học chương X"). Giá trị này lấy từ metadata `chapter`, mà `chapter` được suy từ outline và heading của PDF. Filter không được suy từ đáp án.
- Test lấy chủ yếu từ section **5.6 và 6.6**: t01–t04 nằm ở hai section này và không có câu dev nào thuộc đây. t05 (6.5) và t06 (6.1/6.3) nằm ở section có câu dev khác (6.3: d10, d15), nên vẫn còn chút nguy cơ chủ đề lân cận.
- Câu hỏi được Claude (AI) soạn nháp từ text đã chuẩn hóa. Sau đó từng evidence được kiểm chứng tự động bằng `python -m src.benchmark_check`, và tác giả duyệt lại. Không có câu nào thiếu đáp án trong nguồn.
- Bộ câu hỏi và nhãn được giữ nguyên cho cả ba chiến lược. **Không sửa test sau khi xem kết quả**; nếu buộc phải sửa thì ghi rõ trong báo cáo.

Kiểm chứng: `cd starter; python -m src.benchmark_check`. Lệnh này phải in `Benchmark check passed.`
