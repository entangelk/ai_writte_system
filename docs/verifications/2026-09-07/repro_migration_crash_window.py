"""H1 처방을 실 mongo 로 확인한다 — 크래시 창 복구와 code=86 (2026-09-07).

독립 검증(`account_withdrawal_d4_ledger_axis.md`) 하드닝 H1 의 폐쇄 근거다. 저장소 밖
(`/tmp`)에 두면 재부팅 한 번에 재현 불가가 되므로 기록 옆에 둔다.

    docker compose -f docker-compose.test.yml up -d   # 27020 rs-test
    python3 docs/verifications/2026-09-07/repro_migration_crash_window.py

실측(2026-09-07 알파):
  1) 같은 이름·다른 키 create_index → **code=86 IndexKeySpecsConflict** 로 거부
  2) 크래시 창(문서만 개명) 재현 → 옛 필드 0건인데 옛 인덱스 2개 잔존
  3) 재실행이 그 둘을 지운다 — **종전 구현은 `pending == 0` 조기 반환이라 못 지웠다**
  4) 그 뒤 어댑터의 새 키 인덱스 생성이 성공한다(기동 복구)
  5) 재실행 멱등 — 새 키 인덱스는 건드리지 않는다(dropped=[])
"""
import sys
from pymongo import ASCENDING, MongoClient
from pymongo.errors import OperationFailure

sys.path.insert(0, ".")
from scripts.migrate_ledger_user_axis import migrate, stale_index_names

URI = "mongodb://localhost:27020/?replicaSet=rs-test"
client = MongoClient(URI, serverSelectionTimeoutMS=8000)
db = client["h1_repro"]
db.drop_collection("ledger")
col = db["ledger"]

# 개명 전 상태 재현: 옛 키 인덱스 + 옛 필드 문서
col.create_index([("user_id", ASCENDING), ("action", ASCENDING)],
                 name="request_usage_ledger_dedupe_unique", unique=True)
col.create_index([("user_id", ASCENDING), ("daily_key", ASCENDING)],
                 name="request_usage_ledger_by_user_day")
col.insert_one({"_id": "e1", "user_id": "u1", "action": "a", "daily_key": "d"})

print("1) code=86 실증 — 같은 이름, 다른 키")
try:
    col.create_index([("target_user_id", ASCENDING), ("daily_key", ASCENDING)],
                     name="request_usage_ledger_by_user_day")
    print("   !! 거부되지 않았다")
except OperationFailure as exc:
    print(f"   거부됨 code={exc.code} ({'IndexKeySpecsConflict' if exc.code == 86 else exc.code})")

print("2) 크래시 창 재현 — 문서만 옮기고 인덱스는 남긴다")
col.update_many({"user_id": {"$exists": True}}, {"$rename": {"user_id": "target_user_id"}})
print(f"   옛 필드 문서 수 = {col.count_documents({'user_id': {'$exists': True}})}")
print(f"   남은 옛 인덱스 = {stale_index_names(col)}")

print("3) 그 상태에서 재실행")
report = migrate(col)
print(f"   renamed={report['renamed']} dropped={sorted(report['dropped_indexes'])}")
print(f"   남은 옛 인덱스 = {stale_index_names(col)}")

print("4) 이제 어댑터가 새 키 인덱스를 만들 수 있는가")
col.create_index([("target_user_id", ASCENDING), ("daily_key", ASCENDING)],
                 name="request_usage_ledger_by_user_day")
print("   생성 성공")

print("5) 재실행 멱등 — 새 키 인덱스를 건드리지 않는다")
again = migrate(col)
print(f"   renamed={again['renamed']} dropped={again['dropped_indexes']}")
print(f"   인덱스 = {sorted(i['name'] for i in col.list_indexes())}")

client.drop_database("h1_repro")
client.close()
