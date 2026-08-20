#!/usr/bin/env bash
# 독립 검증 재현 — 임베딩 어댑터 슬라이스(0bb73ee·c3f75c0·e49d458).
# (docs/verifications/2026-08-20/embedding_adapter_slice.md §Reproduction)
#
# 전제: 트리 clean & 커밋됨. verification.md "clean-tree" 브랜치 — 복원은 git checkout --.
# 안전망: 매 뮤테이션 전 status 공백 확인 + 리터럴 count==1 단정 + 복원 후 status 공백 확인.
#
# ★ V1/V1c(별칭·이름재결합 우회)는 이 검증의 조건(B1)의 실증이다 — 폐쇄 커밋이 들어오면
# 두 블록의 기대값이 뒤집혀야 한다(16 passed → guard 실패). 그때 이 스크립트를 다시 돌린다.
#
# 실행: bash docs/verifications/2026-08-20/repro_embedding_assembly.sh
set -u
cd "$(git rev-parse --show-toplevel)" || exit 1

E=services/application/app/indexing/embedding.py
W=scripts/index_sync_worker.py
AS="tests/test_embedding_assembly.py"
AP="tests/test_embedding_provider.py"

chk() { [ -z "$(git status --short)" ] || { echo "PRE-FLIGHT FAIL(tree dirty)"; exit 1; }; }
mutfile() {  # mutfile <파일> <기존 리터럴> <뮤테이션 리터럴>
  local f="$1" old="$2" new="$3"
  chk
  python3 - "$f" "$old" "$new" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
assert s.count(sys.argv[2]) == 1, f"literal count={s.count(sys.argv[2])}"
p.write_text(s.replace(sys.argv[2], sys.argv[3]), encoding="utf-8")
PY
  python3 -m pytest -q "$AS" "$AP" 2>&1 | grep -E "FAILED|SUBFAILED|failed|passed" | tail -4
  git checkout -- "$f"; chk; echo "  [restored — tree clean]"
}

echo "═══ Part 0. 기준 ═══"
python3 -m pytest -q "$AS" "$AP" 2>&1 | tail -1   # 30 passed / 29 subtests
python3 scripts/calibrate_character_identity_threshold.py --help >/dev/null 2>&1; echo "calibrate --help rc=$? (종전 ModuleNotFoundError)"

echo; echo "═══ Part 1. compose 렌더(환경 통제 — guides/verification.md §Recording a measurement) ═══"
THREE="EMBEDDING_SERVICE_URL=https://ext-embed.example CHROMA_HOST=ext ELASTICSEARCH_URL=https://es LLAMA_BASE_URL=https://l"
echo "── 배포, 새 env 무설정 → native/빈둘(기존 배포 무영향, 축④)"
env $THREE docker compose --env-file /dev/null -f docker-compose.yml -f docker-compose.external.yml config 2>/dev/null | grep -m3 "EMBEDDING_API"; echo "rc=$?"
echo "── 배포, openai 명시 → 통과"
env $THREE EMBEDDING_API_FORMAT=openai EMBEDDING_API_MODEL=text-embedding-3-small EMBEDDING_API_KEY=sk-x docker compose --env-file /dev/null -f docker-compose.yml -f docker-compose.external.yml config >/dev/null 2>&1; echo "rc=$?"

echo; echo "═══ Part 2. 가드 맹점(이 검증의 조건 B1) — 이름 재결합 계열 ═══"
echo "── V1: 별칭 import 후 호출 → ★현재 침묵(16 passed)이 조건 B1의 실증"
mutfile $W 'def _build_embedding_provider():' 'def _build_embedding_provider():
    from services.application.app.indexing.embedding import RemoteEmbeddingProvider as REP
    REP(base_url="http://mutated:1")'
echo "── V1c: 할당 별칭(P = Remote…; P(…)) → ★같은 계열, 역시 침묵"
mutfile $W 'def _build_embedding_provider():' 'def _build_embedding_provider():
    from services.application.app.indexing.embedding import RemoteEmbeddingProvider
    P = RemoteEmbeddingProvider
    P(base_url="http://mutated:1")'
echo "── V1b: 모듈 속성 emb.RemoteEmbeddingProvider(…) → 잡는다(경계 확인)"
mutfile $W 'def _build_embedding_provider():' 'def _build_embedding_provider():
    import services.application.app.indexing.embedding as emb
    emb.RemoteEmbeddingProvider(base_url="http://mutated:1")'

echo; echo "═══ Part 3. 구현자 뮤테이션 E1~E6 같은 diff 로 재유도 ═══"
echo "── E1: 한 자리가 직접 호출로 회귀(import 문은 남김 → 가드 셀만)"
mutfile $W '    return build_embedding_provider_from_env()' '    from services.application.app.indexing.embedding import RemoteEmbeddingProvider
    return RemoteEmbeddingProvider(base_url=os.environ.get("EMBEDDING_SERVICE_URL"))'
echo "── E3: 형식을 키 유무로 추론"
mutfile $E '    wire_format = os.environ.get("EMBEDDING_API_FORMAT", NATIVE_FORMAT).strip().lower()' '    wire_format = OPENAI_FORMAT if os.environ.get("EMBEDDING_API_KEY") else NATIVE_FORMAT'
echo "── E5: 접미 /v1 벗기기 제거(축③ — /v1/proxy 서브테스트는 통과해야)"
mutfile $E '        base_url=_strip_version_suffix(resolved),' '        base_url=resolved,'
echo "── E6: 차원 가드를 openai 쪽만 빼먹음"
mutfile $E '        api_key=os.environ.get("EMBEDDING_API_KEY") or None,
        timeout_seconds=timeout_seconds,
        trust_env=trust_env,
        expected_dimensions=expected_dimensions,' '        api_key=os.environ.get("EMBEDDING_API_KEY") or None,
        timeout_seconds=timeout_seconds,
        trust_env=trust_env,
        expected_dimensions=None,'
echo "── E4: 모델 없으면 조용히 기본값"
mutfile $E '    model = os.environ.get("EMBEDDING_API_MODEL")' '    model = os.environ.get("EMBEDDING_API_MODEL") or "text-embedding-3-small"'
echo "── E2b(결합): 헬퍼가 provider 를 전혀 안 만듦(over-strict 셀 확인)"
chk; python3 - <<'PY'
import pathlib
p = pathlib.Path("services/application/app/indexing/embedding.py")
s = p.read_text(encoding="utf-8")
a = "    return RemoteEmbeddingProvider("; b = "    return OpenAIEmbeddingProvider("
assert s.count(a) == 1 and s.count(b) == 1
p.write_text(s.replace(a, "    raise RuntimeError(").replace(b, "    raise RuntimeError("), encoding="utf-8")
PY
python3 -m pytest -q "$AS" 2>&1 | grep -E "test_the_helper_itself|failed|passed" | tail -3
git checkout -- "$E"; chk; echo "  [restored — tree clean]"

echo; echo "═══ 완료 ═══"
