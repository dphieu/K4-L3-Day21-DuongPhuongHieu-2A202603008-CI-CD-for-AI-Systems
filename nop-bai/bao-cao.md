# Báo Cáo Lab Day 21 - CI/CD cho AI Systems

| | |
|---|---|
| Họ và tên | Dương Phương Hiểu |
| MSSV | 2A202603008 |
| Lớp / Khóa | K4 |
| Repo GitHub | <https://github.com/dphieu/K4-L3-Day21-DuongPhuongHieu-2A202603008-CI-CD-for-AI-Systems> |
| Ngày nộp | 07/10/2026 |

---

## 1. Bộ Siêu Tham Số Đã Chọn và Lý Do

| Lần chạy | n_estimators | learning_rate | max_depth | f1_score | accuracy |
|---|---|---|---|---|---|
| 1 | 100 | 0.1 | 3 | 0.7109 | 0.8780 |
| 2 | 50 | 0.05 | 2 | 0.6051 | 0.8460 |
| 3 | 200 | 0.1 | 5 | 0.7149 | 0.8740 |

**Bộ siêu tham số đã chọn:** `n_estimators=200`, `learning_rate=0.1`, `max_depth=5`.

**Lý do:** Lần 3 đạt F1 `0.7149`, cao nhất và vượt Quality Gate `0.65`. Accuracy cao nhất lại thuộc lần 1 (`0.8780`), chứng tỏ accuracy chưa phản ánh tốt lớp thu nhập cao thiểu số. Lần 2 chỉ đạt F1 `0.6051` vì ít cây, learning rate thấp và cây nông. Learning rate nhỏ làm đóng góp của mỗi cây giảm nên cần tăng `n_estimators`; với learning rate `0.1`, tăng số cây và độ sâu giúp F1 nhích lên.

---

## 2. Vì Sao Ngưỡng Chất Lượng Đặt Trên F1 Chứ Không Phải Accuracy

Lớp thu nhập cao (`target=1`) chỉ chiếm 24,8% nên dữ liệu mất cân bằng. Mô hình luôn trả lời “thu nhập thấp” vẫn đạt 75,2% accuracy nhưng recall lớp dương bằng 0; dùng accuracy làm cổng chất lượng vì thế gây hiểu nhầm. F1 là trung bình điều hòa của precision và recall, chỉ cao khi mô hình vừa hạn chế báo động giả vừa phát hiện đủ mẫu dương. Mã gọi trực tiếp `f1_score(y_eval, preds)`. Không dùng `average="weighted"` vì lớp đa số chi phối kết quả, cũng không dùng `average="macro"` vì mục tiêu là đánh giá riêng lớp dương thiểu số.

---

## 3. Khó Khăn Gặp Phải và Cách Giải Quyết

| Khó khăn | Nguyên nhân | Cách giải quyết |
|---|---|---|
| DVC không ghi được S3 | IAM user thiếu quyền S3 | Tạo user CI với quyền tối thiểu trên `dvc/*` và `artifacts/current/*`. |
| Push chưa tự chạy | Actions chưa bật cho repository fork | Bật workflow rồi kiểm chứng bằng push trên `main`. |
| API bị timeout | Mạng luân phiên ba IP egress | Chỉ mở cổng 8080 cho ba CIDR `/32` tương ứng. |

---

## 4. So Sánh Bước 2 và Bước 3 (bắt buộc, 2 - 3 câu)

| | f1_score | accuracy |
|---|---|---|
| Bước 2 (chỉ `train_batch1`) | 0.7149 | 0.8740 |
| Bước 3 (thêm `train_batch2`) | 0.7354 | 0.8820 |

**Nhận xét:** Sau khi thêm `train_batch2`, F1-score tăng từ 0.7149 lên 0.7354 (tăng 0.0205), còn accuracy tăng từ 0.8740 lên 0.8820. Mức cải thiện tương đối nhỏ vì hai batch được lấy từ cùng một phân phối; dữ liệu bổ sung chủ yếu giúp mô hình giảm biến thiên và ước lượng ổn định hơn, thay vì cung cấp một nhóm đặc trưng hoàn toàn mới.
