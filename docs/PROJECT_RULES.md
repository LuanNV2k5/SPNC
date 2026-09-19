
PROJECT STRICT RULES

1. Không được tự ý thay đổi requirement.
2. Khi requirement chưa rõ:

   - ghi vào docs/OPEN_QUESTIONS.md
   - không tự suy đoán nghiệp vụ quan trọng.
3. Không được code module tiếp theo nếu module hiện tại chưa PASS kiểm tra.
4. Mọi thay đổi database phải đi qua migration.
5. Không sửa migration cũ đã được apply.
   Tạo migration mới.
6. Backend phải chia:
   router
   service
   repository
   model
   schema
7. Không viết business logic trong API controller/router.
8. Frontend không được truy cập database trực tiếp.
9. Authorization phải kiểm tra tại backend.
   Ẩn button frontend KHÔNG được coi là authorization.
10. Mọi API nhạy cảm phải xác minh user và role.
11. Role:
    ADMIN
    TEACHER
    STUDENT
12. TEACHER chỉ được truy cập:

    - lớp mình quản lý
    - học sinh thuộc lớp mình
    - kỳ thi thuộc phạm vi được phép.
13. STUDENT chỉ xem/chỉnh sửa dữ liệu của chính mình
    trừ dữ liệu được công khai.
14. Trace Event phải append-only.
    Không update lịch sử trace tùy tiện.
15. Timestamp database sử dụng UTC.
16. Trace phải có:
    client timestamp
    server timestamp
    session_id
    sequence number.
17. Không tin tuyệt đối client timestamp.
18. Code học sinh tuyệt đối không chạy trong API process.
19. Code runner phải giới hạn:
    CPU
    RAM
    execution time
    filesystem
    network.
20. Không gọi học sinh:
    "gian lận"
    "không hiểu bài"
    "yếu"
    chỉ dựa trên trace.
21. Hệ thống chỉ đưa ra:
    ATTENTION SIGNAL
    kèm bằng chứng.
22. Giáo viên là người diễn giải dấu vết.
23. Mỗi feature phải có test.
24. Không merge khi:
    lint fail
    typecheck fail
    unit test fail
    integration test fail.
25. Không log:
    password
    access token
    refresh token.
26. API phải có pagination với collection lớn.
27. API ingest trace phải hỗ trợ batch.
28. Phải chống duplicate trace bằng:
    session_id + sequence_number
    hoặc idempotency key.
29. Mọi lỗi phải có:
    error_code
    message
    request_id.
30. Khi hoàn thành task:
    không chỉ nói "done".
    Phải liệt kê:

    - file đã sửa
    - migration
    - API
    - test
    - lệnh test
    - kết quả.
