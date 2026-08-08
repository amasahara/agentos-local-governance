[🇻🇳 Tiếng Việt](huong_dan.vi.md) | [🇬🇧 English](huong_dan.en.md)

# Hướng dẫn developer — v0.22.2

## Thứ tự vận hành

1. Hoàn tất extraction, identity resolution và Controlled Target Insert theo v0.21.2–v0.22.1.
2. Với run `committed`, tạo reconciliation để chứng minh TARGET chứa đúng row set đã cam kết.
3. Với run `committing/in_doubt`, chạy `db-recovery-scan`, tạo reconciliation và chỉ đọc TARGET.
4. Nếu outcome `matched`, human có thể xác nhận `committed_verified`.
5. Nếu outcome `observed_none`, human có thể xác nhận `not_committed_verified`; sau đó manual retry của cùng approved insert plan mới được phép.
6. Nếu outcome `observed_partial/mismatch`, giữ `manual_intervention`; không dùng AgentOS để UPDATE/DELETE/UPSERT/MERGE sửa TARGET.
7. Nếu external commit đã chắc chắn nhưng `lineage_status=pending`, dùng lineage recovery; đây là local-only, idempotent và không retry INSERT.
8. Review `db-reconciliation-summary`, recovery cases và checkpoint hashes trước khi đóng sự cố.

## Không được làm

- Không suy luận commit outcome chỉ từ exception của driver.
- Không auto retry `committing/in_doubt`.
- Không lưu raw TARGET rows hoặc business-key parameters vào state/audit.
- Không sửa SOURCE.
- Không dùng recovery để mở arbitrary SQL hoặc TARGET UPDATE/DELETE.
- Không đánh dấu `committed_verified` khi reconciliation chưa `matched`.
- Không đánh dấu `not_committed_verified` khi TARGET còn bất kỳ expected row nào.

## Validation

```bash
.agents/bin/agentos db-reconciliation-recovery-db-sync
.agents/bin/agentos docs-check
python3 -m pytest -q .agents/tests
```
