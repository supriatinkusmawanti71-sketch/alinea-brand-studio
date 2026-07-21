import type { StructuredFields } from "@/lib/api/types";

export type BrandSpecField = {
  key: keyof StructuredFields;
  label: string;
  placeholder: string;
  type: "text" | "list";
};

export const BRAND_SPEC_FIELDS: BrandSpecField[] = [
  {
    key: "industry",
    label: "行业 / 品类",
    placeholder: "例如：精品茶饮",
    type: "text",
  },
  {
    key: "brand_background",
    label: "品牌背景",
    placeholder: "例如：城市东方茶饮品牌，主打轻负担茶饮",
    type: "text",
  },
  {
    key: "target_audiences",
    label: "目标用户",
    placeholder: "每行一个，例如：年轻城市消费者",
    type: "list",
  },
  {
    key: "price_positioning",
    label: "价格定位",
    placeholder: "例如：中高端、亲民、轻奢",
    type: "text",
  },
  {
    key: "brand_personality",
    label: "品牌人格",
    placeholder: "每行一个，例如：清爽、可信、亲切",
    type: "list",
  },
  {
    key: "style_keywords",
    label: "风格关键词",
    placeholder: "每行一个，例如：当代、东方、清爽",
    type: "list",
  },
  {
    key: "required_elements",
    label: "必须出现的元素",
    placeholder: "每行一个，例如：茶叶、山水线条",
    type: "list",
  },
  {
    key: "prohibited_elements",
    label: "禁止出现的元素",
    placeholder: "每行一个，例如：卡通熊、复杂渐变",
    type: "list",
  },
  {
    key: "competitor_notes",
    label: "竞品备注",
    placeholder: "例如：避免与某某品牌过于相似",
    type: "text",
  },
  {
    key: "slogan",
    label: "口号",
    placeholder: "例如：一杯清醒的东方茶",
    type: "text",
  },
  {
    key: "language",
    label: "语言",
    placeholder: "例如：zh-CN",
    type: "text",
  },
];

export function splitListField(value: string) {
  return value
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}
