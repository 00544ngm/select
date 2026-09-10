/**
 * 结果文本格式化工具
 *
 * 1. cleanLabel: 清除历史数据里的「中文标签 (english_key)」括号英文，
 *    只在括号紧跟中文/全角字符后时清除，避免误伤正文里的英文引用。
 * 2. parseFmtText: 把后端 _fmt 生成的「• 键: 值」文本解析成结构化字段，
 *    供字段网格渲染。
 */

const BRACKET_RE = /([\u4e00-\u9fff\uff08-\uff09）】》」0-9])\s*[（(]([A-Za-z][A-Za-z0-9_]*)[)）]/g;

export function cleanLabel(text: string | undefined | null): string {
  if (!text) return "";
  let prev = text;
  // 连续应用直到稳定，处理 "第一层 (first_layer)" 这类嵌套后残留
  for (let i = 0; i < 3; i++) {
    const next = prev.replace(BRACKET_RE, "$1");
    if (next === prev) break;
    prev = next;
  }
  return prev;
}

export interface ParsedField {
  /** 字段名，如「买家画像」；null 表示这一行是普通段落 */
  label: string | null;
  /** 字段值 / 段落文本 */
  value: string;
  /** 缩进列表项（原文本里的 "  - xxx" 行） */
  items: string[];
  /** 嵌套层级（• 前的缩进深度） */
  depth: number;
}

/**
 * 解析 _fmt 输出：
 *   • 键: 值
 *   • 键: • 子键: 子值   (嵌套 dict 会被 _fmt 展开成多行)
 *     - 列表项
 * 无法识别的行按段落处理。
 */
export function parseFmtText(raw: string | undefined | null): ParsedField[] {
  const text = cleanLabel(raw);
  if (!text.trim()) return [];

  const lines = text.split("\n");
  const fields: ParsedField[] = [];

  for (const line of lines) {
    if (!line.trim()) continue;

    const listMatch = line.match(/^\s+-\s+(.*)$/);
    if (listMatch && fields.length > 0) {
      fields[fields.length - 1].items.push(listMatch[1].trim());
      continue;
    }

    const bulletMatch = line.match(/^(\s*)•\s*(.*)$/);
    if (bulletMatch) {
      const depth = Math.floor(bulletMatch[1].length / 2);
      const body = bulletMatch[2];
      // 分离「键: 值」——取第一个冒号（中英文皆可）
      const sep = body.search(/[:：]/);
      if (sep > 0 && sep <= 24) {
        fields.push({
          label: body.slice(0, sep).trim(),
          value: body.slice(sep + 1).trim(),
          items: [],
          depth,
        });
      } else {
        fields.push({ label: null, value: body.trim(), items: [], depth });
      }
      continue;
    }

    // 普通段落行
    fields.push({ label: null, value: line.trim(), items: [], depth: 0 });
  }

  return fields;
}

/** 从解析结果中按标签名取值（用于抽屉头部提取 评分/类型 等） */
export function pickField(fields: ParsedField[], ...labels: string[]): string | undefined {
  for (const l of labels) {
    const hit = fields.find((f) => f.label === l);
    if (hit) return hit.value;
  }
  return undefined;
}

export function scoreTone(score: number | undefined | null): {
  text: string;
  bg: string;
  bar: string;
} {
  const s = score ?? 0;
  if (s >= 85)
    return { text: "text-emerald-700", bg: "bg-emerald-50", bar: "bg-emerald-500" };
  if (s >= 70)
    return { text: "text-amber-700", bg: "bg-amber-50", bar: "bg-amber-500" };
  return { text: "text-muted-foreground", bg: "bg-muted", bar: "bg-muted-foreground/40" };
}

/* ── 审判结果（模式B）B 品解析 ─────────────────────────────── */

export interface PerBSection {
  title: string;
  fields: ParsedField[];
}

export interface PerBProduct {
  name: string;
  productId?: string;
  productUrl?: string;
  productImage?: string;
  sections: PerBSection[];
  cTotal?: number;
  bTotal?: number;
  vetoed?: boolean;
  vetoReason?: string;
  legacyG3Validated?: boolean;
  vetoRisks?: {
    rhythm?: boolean;
    competition?: boolean;
    brandOvershadow?: boolean;
    logistics?: boolean;
    legal?: boolean;
    badReviews?: boolean;
  };
}

interface RawSection {
  title: string;
  content?: string;
  children?: RawSection[];
}

const TRUTHY_RE = /^(是|true|yes|y|1)$/i;
const FALSY_RE = /^(否|false|no|n|0)$/i;

function toBoolean(v: string | undefined): boolean | undefined {
  const value = v?.trim() ?? "";
  if (TRUTHY_RE.test(value)) return true;
  if (FALSY_RE.test(value)) return false;
  return undefined;
}

function toNumber(v: string | undefined): number | undefined {
  if (!v) return undefined;
  const m = v.match(/-?\d+(\.\d+)?/);
  return m ? Number(m[0]) : undefined;
}

/**
 * 从审判结果的 sections 里按 B 品聚合各审查环节的字段。
 * 后端 _fmt 对嵌套 dict 不缩进，而是链式串在一行：
 *   • 各B品详情: • B品名: • 字段: 值
 *   • 字段2: 值2          ← 属于上一个 B 品
 *   • B品名2: • 字段: 值   ← 值以「• 」开头 ⇒ 新的 B 品
 * 解析失败的章节静默跳过（完整内容仍在「结果详情」Tab）。
 */
export function extractBProducts(
  sections: RawSection[] | undefined
): PerBProduct[] {
  if (!sections || sections.length === 0) return [];

  const order: string[] = [];
  const map = new Map<string, PerBProduct>();

  const ensure = (name: string): PerBProduct => {
    let p = map.get(name);
    if (!p) {
      p = { name, sections: [] };
      map.set(name, p);
      order.push(name);
    }
    return p;
  };

  for (const section of sections) {
    const content = cleanLabel(section.content);
    if (!content.includes("各B品详情")) continue;

    let currentB: { name: string; fields: ParsedField[] } | null = null;
    const flush = () => {
      if (currentB && currentB.fields.length > 0) {
        ensure(currentB.name).sections.push({
          title: cleanLabel(section.title),
          fields: currentB.fields,
        });
      }
      currentB = null;
    };

    for (const rawLine of content.split("\n")) {
      const line = rawLine.trim();
      if (!line) continue;

      // 列表项归属上一个字段
      const listMatch = rawLine.match(/^\s+-\s+(.*)$/);
      if (listMatch && currentB && currentB.fields.length > 0) {
        currentB.fields[currentB.fields.length - 1].items.push(
          listMatch[1].trim()
        );
        continue;
      }
      if (!line.startsWith("•")) continue;

      // 按「: • 」把链式嵌套拆成段
      const chain = line.split(/[:：]\s*(?=•\s)/).map((s) =>
        s.replace(/^•\s*/, "").trim()
      );
      // chain: [key, key, ..., "key: value"] —— 前面的都是嵌套开启段

      let idx = 0;
      if (chain[0].includes("各B品详情")) {
        idx = 1; // 跳过容器段
      }
      if (idx >= chain.length) continue;

      // 开启了新层级（链长>剩1段）⇒ 第一段是 B 品名
      if (chain.length - idx >= 2) {
        flush();
        currentB = { name: chain[idx], fields: [] };
        idx += 1;
      }
      if (!currentB) continue;

      // 中间的额外开启段作为子分组标签
      let depth = 0;
      while (idx < chain.length - 1) {
        currentB.fields.push({
          label: chain[idx],
          value: "",
          items: [],
          depth,
        });
        depth += 1;
        idx += 1;
      }

      // 最后一段是「key: value」叶子（或纯文本）
      const leaf = chain[chain.length - 1];
      const sep = leaf.search(/[:：]/);
      if (sep > 0 && sep <= 24) {
        let value = leaf.slice(sep + 1).trim();
        const items: string[] = [];
        // _fmt 把列表首项拼在同一行：「• 键:   - 首项」
        if (value.startsWith("- ")) {
          items.push(value.slice(2).trim());
          value = "";
        }
        currentB.fields.push({
          label: leaf.slice(0, sep).trim(),
          value,
          items,
          depth,
        });
      } else if (leaf) {
        currentB.fields.push({ label: null, value: leaf, items: [], depth });
      }
    }
    flush();
  }

  // 提取总分 / 否决状态
  for (const p of map.values()) {
    for (const sec of p.sections) {
      const isC = sec.title.includes("C组合");
      const isB = sec.title.includes("B跨境");
      const isVeto = sec.title.includes("否决");
      for (const f of sec.fields) {
        if (!f.label) continue;
        if ((isC || isB) && f.label.includes("总分")) {
          const n = toNumber(f.value);
          if (n !== undefined) {
            if (isC) p.cTotal = n;
            else p.bTotal = n;
          }
        }
        if (isVeto) {
          if (f.label.includes("原因") && f.value && f.value !== "-") {
            p.vetoReason = f.value;
          } else if (f.label.includes("被否决")) {
            p.vetoed = toBoolean(f.value);
          }
          const value = toBoolean(f.value);
          if (f.label.includes("已验证需求")) p.legacyG3Validated = value;
          p.vetoRisks ??= {};
          if (f.label.includes("节奏不匹配")) p.vetoRisks.rhythm = value;
          if (f.label.includes("竞品冲突")) p.vetoRisks.competition = value;
          if (f.label.includes("品牌压制")) p.vetoRisks.brandOvershadow = value;
          if (f.label.includes("物流问题")) p.vetoRisks.logistics = value;
          if (f.label.includes("法律风险")) p.vetoRisks.legal = value;
          if (f.label.includes("差评超标")) p.vetoRisks.badReviews = value;
        }
      }
    }
  }

  return order.map((n) => map.get(n)!);
}
