import type { ReactNode } from "react";
import { Link } from "react-router";

/**
 * 법적 문서 전용 마크다운 부분집합 렌더러 (브리프 `landing-page-scope` D2=ⓐ).
 *
 * **왜 렌더러인가 — 본문을 옮겨 쓰지 않기 위해서다.** D2=ⓐ 는 약관·방침 본문을
 * 프런트에 싣기로 했고, 그 단점("본문이 두 곳이 된다")의 처방은 **대조 가드**다
 * (`legalSource.test.ts`). 가드가 성립하려면 프런트의 사본이 `docs/legal/*.md` 와
 * **바이트 단위로 같아야** 하므로, 본문을 TSX 로 옮겨 쓰는 길은 처음부터 닫혀 있다
 * — 사본을 그대로 싣고 **읽을 때** 변환한다.
 *
 * **부분집합이고, 그것이 의도다.** 여기서 지원하는 문법은 두 문서가 실제로 쓰는
 * 것뿐이다(h1·h2·문단·인용·표·번호 목록·중첩 불릿·수평선, 인라인은 강조·코드·링크).
 * 새 문법을 쓰기 전에 이 파일을 고치는 편이, 일반 마크다운 라이브러리를 들여
 * 번들을 키우고 위생 처리까지 떠안는 것보다 싸다. **지원하지 않는 문법은 조용히
 * 빠지지 않고 문단 텍스트로 그려진다** — 화면에 기호가 보이는 것이 신호다.
 *
 * **링크 둘만 앱 주소로 바꾼다.** 저장소 문서끼리의 상호 참조(`README.md`,
 * `../service-policy-contract.md`)는 읽는 사람이 따라갈 수 없는 주소라 **문자로만**
 * 남긴다 — 죽은 링크를 보여 주는 것보다 낫고, 공개 페이지가 개발 문서처럼 보이는
 * 것을 줄인다(브리프가 ⓑ 의 단점으로 적은 바로 그것이다).
 */
const IN_APP_LINKS: Record<string, string> = {
  "terms-of-service-draft.md": "/terms",
  "privacy-policy-draft.md": "/privacy",
};

/**
 * 머리말에서 걷어내는 줄. `근거:` 는 저장소 경로 둘을 가리키는 **편집용 메타**라
 * 읽는 사람에게는 뜻이 없다. `상태:`·`작성:`·`버전:` 은 남긴다 — 검토 전이라는
 * 사실과 판본이 독자에게 필요한 정보다.
 */
const EDITORIAL_PREFIX = "근거:";

/**
 * 남는 머리말 메타 세 줄. **한 줄씩 선다** — 마크다운의 기본 접합(연속한 줄은 한
 * 문단)을 그대로 따르면 셋이 *"상태: … 작성: … 버전: …"* 한 문장으로 붙어 판본
 * 정보를 읽기 어려워진다. 본문 문단에는 이 예외가 없다(문서의 문단은 한 줄씩이다).
 */
const METADATA_LINE = /^(상태|작성|버전):/;

const INLINE = /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)/g;

function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  let consumed = 0;
  let index = 0;
  for (const match of text.matchAll(INLINE)) {
    const at = match.index;
    if (at > consumed) {
      out.push(text.slice(consumed, at));
    }
    const [whole, bold, code, label, href] = match;
    const childKey = `${key}-${index++}`;
    if (bold !== undefined) {
      out.push(<strong key={childKey}>{inline(bold, childKey)}</strong>);
    } else if (code !== undefined) {
      out.push(<code key={childKey}>{code}</code>);
    } else {
      const to = IN_APP_LINKS[href];
      out.push(
        to === undefined
          ? <span key={childKey}>{inline(label, childKey)}</span>
          : <Link key={childKey} className="legal-link" to={to}>
              {inline(label, childKey)}
            </Link>,
      );
    }
    consumed = at + whole.length;
  }
  if (consumed < text.length) {
    out.push(text.slice(consumed));
  }
  return out;
}

const ORDERED_ITEM = /^(\d+)\. (.*)$/;
const NESTED_ITEM = /^ {3}- (.*)$/;

function startsBlock(line: string): boolean {
  return line.trim() === "" || line.startsWith("#") || line.startsWith(">") ||
    line.startsWith("|") || line.startsWith("---") || line.startsWith("- ") ||
    ORDERED_ITEM.test(line);
}

/** 마크다운 본문을 엘리먼트 목록으로 바꾼다. 블록 단위로 한 번만 훑는다. */
export function renderLegalDocument(source: string): ReactNode[] {
  const lines = source.split("\n")
    .filter((line) => !line.startsWith(EDITORIAL_PREFIX));
  const blocks: ReactNode[] = [];
  let cursor = 0;

  while (cursor < lines.length) {
    const line = lines[cursor];
    const key = `block-${blocks.length}`;

    if (line.trim() === "") {
      cursor += 1;
      continue;
    }

    if (line.startsWith("## ")) {
      blocks.push(<h2 key={key}>{inline(line.slice(3), key)}</h2>);
      cursor += 1;
      continue;
    }

    if (line.startsWith("# ")) {
      blocks.push(<h1 key={key}>{inline(line.slice(2), key)}</h1>);
      cursor += 1;
      continue;
    }

    if (line.startsWith("---")) {
      blocks.push(<hr key={key} />);
      cursor += 1;
      continue;
    }

    if (line.startsWith(">")) {
      const paragraphs: string[] = [];
      while (cursor < lines.length && lines[cursor].startsWith(">")) {
        const content = lines[cursor].replace(/^>\s?/, "");
        // `>` 한 줄은 인용 안의 문단 경계다. 이것을 무시하면 인용 전체가
        // 한 덩어리로 붙어 세 문단이 한 문장처럼 읽힌다.
        if (content.trim() === "") {
          paragraphs.push("");
        } else if (paragraphs.length === 0 || paragraphs[paragraphs.length - 1] === "") {
          paragraphs.push(content);
        } else {
          paragraphs[paragraphs.length - 1] += ` ${content}`;
        }
        cursor += 1;
      }
      blocks.push(
        <blockquote key={key} className="legal-notice">
          {paragraphs.filter((text) => text !== "").map((text, at) => (
            <p key={`${key}-p${at}`}>{inline(text, `${key}-p${at}`)}</p>
          ))}
        </blockquote>,
      );
      continue;
    }

    if (line.startsWith("|")) {
      const rows: string[][] = [];
      while (cursor < lines.length && lines[cursor].startsWith("|")) {
        const cells = lines[cursor].split("|").slice(1, -1).map((cell) => cell.trim());
        // `|---|---|` 구분줄은 데이터가 아니다.
        if (!cells.every((cell) => /^-+$/.test(cell))) {
          rows.push(cells);
        }
        cursor += 1;
      }
      const [header, ...body] = rows;
      blocks.push(
        <div key={key} className="legal-table-scroll">
          <table className="legal-table">
            <thead>
              <tr>
                {header.map((cell, at) => (
                  <th key={`${key}-h${at}`} scope="col">{inline(cell, `${key}-h${at}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {body.map((cells, row) => (
                <tr key={`${key}-r${row}`}>
                  {cells.map((cell, at) => (
                    <td key={`${key}-r${row}c${at}`}>
                      {inline(cell, `${key}-r${row}c${at}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (ORDERED_ITEM.test(line)) {
      const items: Array<{ text: string; nested: string[] }> = [];
      while (cursor < lines.length) {
        const ordered = ORDERED_ITEM.exec(lines[cursor]);
        const nested = NESTED_ITEM.exec(lines[cursor]);
        if (ordered !== null) {
          items.push({ text: ordered[2], nested: [] });
        } else if (nested !== null && items.length > 0) {
          items[items.length - 1].nested.push(nested[1]);
        } else {
          break;
        }
        cursor += 1;
      }
      blocks.push(
        <ol key={key}>
          {items.map((item, at) => (
            <li key={`${key}-i${at}`}>
              {inline(item.text, `${key}-i${at}`)}
              {item.nested.length > 0 && (
                <ul>
                  {item.nested.map((text, nestedAt) => (
                    <li key={`${key}-i${at}n${nestedAt}`}>
                      {inline(text, `${key}-i${at}n${nestedAt}`)}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>,
      );
      continue;
    }

    if (line.startsWith("- ")) {
      const items: string[] = [];
      while (cursor < lines.length && lines[cursor].startsWith("- ")) {
        items.push(lines[cursor].slice(2));
        cursor += 1;
      }
      blocks.push(
        <ul key={key}>
          {items.map((text, at) => (
            <li key={`${key}-i${at}`}>{inline(text, `${key}-i${at}`)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    if (METADATA_LINE.test(line)) {
      blocks.push(
        <p key={key} className="legal-meta">{inline(line, key)}</p>,
      );
      cursor += 1;
      continue;
    }

    const paragraph: string[] = [];
    while (
      cursor < lines.length && !startsBlock(lines[cursor]) &&
      !METADATA_LINE.test(lines[cursor])
    ) {
      paragraph.push(lines[cursor]);
      cursor += 1;
    }
    blocks.push(
      <p key={key}>{inline(paragraph.join(" "), key)}</p>,
    );
  }

  return blocks;
}
