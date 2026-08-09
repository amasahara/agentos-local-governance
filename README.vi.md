# AgentOS Local Governance v0.22.7

**Data Subject Rights & Privacy Lifecycle — schema 43**

Node này bổ sung vòng đời quyền chủ thể dữ liệu theo chuỗi: yêu cầu xóa bất biến → kế hoạch bất biến → human review → human approval → local execution → tombstone canonical entity → bằng chứng/audit ký số.

Bất biến quan trọng:
- SOURCE vẫn SELECT-only.
- TARGET vẫn chỉ ghi qua Controlled Target Insert; v0.22.7 không thêm UPDATE/DELETE/UPSERT/MERGE.
- Nếu record đã có lineage tới TARGET ngoài authority, kết quả là `external_target_erasure_required=true`; AgentOS chỉ hoàn tất xóa local.
- Binding/candidate/lineage có khả năng tái liên kết bị xóa; canonical entity trở thành tombstone với marker ngẫu nhiên không dùng để lookup HMAC.
- Staging/cache/memory/index liên quan được purge theo policy; audit chỉ giữ hash/count/status tối thiểu.
- Kế hoạch bị chặn nếu identity/extraction/TARGET/reconciliation/recovery liên quan đang active hoặc `in_doubt`.
- MCP chỉ expose API đọc trạng thái, không expose request/review/approve/execute mutation.

Xem [`DATA_SUBJECT_RIGHTS.md`](DATA_SUBJECT_RIGHTS.md) và [`.agents/docs/PRIVACY_BOUNDARY_V0227.md`](.agents/docs/PRIVACY_BOUNDARY_V0227.md).
