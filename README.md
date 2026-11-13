# Day 06 · Data Ingestion Engineering

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.

---

## Bài làm

**Phạm Tuấn Cường · 2A202603584 · L3A**. Báo cáo: [report/individual/2A202603584_PhamTuanCuong.md](report/individual/2A202603584_PhamTuanCuong.md).

- Corpus: OpenStax *Introduction to Computer Science*, chương 5–6, gồm 79 trang nội dung, giấy phép CC BY-NC-SA 4.0. Xem [data/manifest.json](data/manifest.json).
- Embedding: `intfloat/multilingual-e5-small` (384 chiều), chạy local trên CPU.
- Vector store: PostgreSQL 16 + pgvector 0.8.7, metric cosine, exact search.
- Ba chiến lược: A là chunk cố định 500/50; B là chunk theo đoạn, tối đa 1000; C là B cộng filter `chapter`.

### Tái lập (Windows PowerShell, chạy từ `starter/`)

```powershell
cd starter
py -3.11 -m venv .venv; .venv\Scripts\Activate.ps1
pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
Copy-Item .env.example .env        # rồi đặt EMBEDDING_MODEL=intfloat/multilingual-e5-small
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py      # Setup OK

# PDF gốc (56 MB, không commit):
mkdir data/raw; curl -o data/raw/intro_cs.pdf https://assets.openstax.org/oscms-prodcms/media/documents/Introduction_To_Computer_Science_-_WEB.pdf

python -m src.run prepare          # data/pages.jsonl + data/manifest.json (79 trang)
python -m src.benchmark_check      # kiểm chứng evidence của 21 câu
python -m src.run ingest           # index A và B
python -m src.run reingest-check   # nạp lại không nhân đôi
python -m src.run change-check     # xử lý tài liệu đổi (bảng tạm)
python -m src.run query --split dev
python -m src.run query --split test
python -m src.run evaluate         # results/summary.json
python -m src.audit_samples        # sinh mẫu audit (xóa nhãn cũ)
python -m src.audit_labels_draft   # nhãn nháp (AI), cần tác giả duyệt
python -m src.audit_summary        # results/audit/audit_summary.json
```

### Cấu trúc bài làm

| Đường dẫn | Nội dung |
|---|---|
| `starter/src/` | ingestion (PyMuPDF), chunking, embeddings, store (pgvector), evaluation, run, benchmark_check, audit_* |
| `starter/src/config.py` | đường dẫn, định nghĩa corpus, tham số A/B/C |
| `data/` | `manifest.json`, `pages.jsonl` (text đã chuẩn hóa của các trang được tính) |
| `benchmark/` | `questions.jsonl` (15 dev / 6 test), `README.md`, `selection_criteria.md` |
| `artifacts/experiment_log.csv` | cấu hình, giả thuyết và kết quả A/B/C |
| `results/` | trace top-3, `summary.json`, `ingest_stats.json`, `reingest_check.json`, `change_check.json`, `errors.log`, `audit/` |
