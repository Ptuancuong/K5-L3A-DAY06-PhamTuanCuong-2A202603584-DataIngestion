# Tiêu chí chọn chiến lược (chốt trước khi chạy truy xuất)

Ngày chốt: 2026-11-13, trước lần chạy `query` đầu tiên. Bằng chứng là commit git chứa file này có timestamp sớm hơn mọi file `results/traces_*`.

1. Chỉ **dev** được dùng để chọn chiến lược. Test chỉ chạy **một lần**, sau khi đã ghi lựa chọn vào file này (phần "Kết quả chọn trên dev" bên dưới) và commit.
2. Thứ tự ưu tiên khi so sánh trên dev:
   1. Evidence Hit@3 trên dev, cao hơn là tốt hơn.
   2. Nếu bằng nhau thì xét Hit@1 trên dev.
   3. Nếu vẫn bằng nhau thì xét tỷ lệ tuân thủ filter trên các câu có filter của dev.
   4. Nếu vẫn bằng nhau thì xét tài nguyên: ít chunk hơn và thời gian ingest ngắn hơn.
3. Không chỉnh tham số (chunk size, overlap, max_size, model) dựa trên kết quả. Ba cấu hình A/B/C được cố định trong `starter/src/config.py` từ trước khi chạy.
4. Nếu chênh lệch giữa các chiến lược ≤ 1 câu trên dev, kết luận là "không phân biệt được với mẫu nhỏ". Khi đó vẫn chọn theo thứ tự trên, nhưng ghi rõ giới hạn này.

## Kết quả chọn trên dev

_(điền sau khi chạy dev, trước khi chạy test)_
