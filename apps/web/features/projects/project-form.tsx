"use client";

import { FormEvent, useState } from "react";

import { Button, Field, TextArea, TextInput } from "@/components/ui";
import type { ProjectCreateRequest, StructuredFields } from "@/lib/api/types";

import { BRAND_SPEC_FIELDS, splitListField } from "./fields";

type ProjectFormProps = {
  isSubmitting: boolean;
  onSubmit: (payload: ProjectCreateRequest) => Promise<void>;
};

type FormState = Record<string, string>;

const initialState: FormState = {
  name: "",
  requirement_text: "",
  industry: "",
  brand_background: "",
  target_audiences: "",
  price_positioning: "",
  brand_personality: "",
  style_keywords: "",
  required_elements: "",
  prohibited_elements: "",
  competitor_notes: "",
  slogan: "",
  language: "",
};

export function ProjectForm({ isSubmitting, onSubmit }: ProjectFormProps) {
  const [form, setForm] = useState<FormState>(initialState);

  function updateField(key: string, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const structuredFields: Record<string, string | string[]> = {};
    for (const field of BRAND_SPEC_FIELDS) {
      const value = form[field.key]?.trim() ?? "";
      if (!value) {
        continue;
      }
      structuredFields[field.key] =
        field.type === "list" ? splitListField(value) : value;
    }

    await onSubmit({
      name: form.name.trim(),
      requirement_text: form.requirement_text.trim() || null,
      structured_fields: structuredFields as StructuredFields,
      reference_artifact_ids: [],
    });

    setForm(initialState);
  }

  return (
    <form className="project-form" onSubmit={handleSubmit}>
      <Field hint="必填，创建后会生成 Intake Run。" label="项目名称">
        <TextInput
          maxLength={100}
          onChange={(event) => updateField("name", event.target.value)}
          placeholder="例如：Alinea 茶饮品牌"
          required
          value={form.name}
        />
      </Field>

      <Field hint="可先写自然语言需求，AI 会根据缺口补问。" label="原始需求">
        <TextArea
          maxLength={10000}
          onChange={(event) => updateField("requirement_text", event.target.value)}
          placeholder="希望做一个现代、清爽的茶饮品牌。"
          rows={5}
          value={form.requirement_text}
        />
      </Field>

      <div className="form-grid">
        {BRAND_SPEC_FIELDS.map((field) => (
          <Field
            hint={field.type === "list" ? "列表字段，一行写一个。" : undefined}
            key={field.key}
            label={field.label}
          >
            {field.type === "list" ? (
              <TextArea
                onChange={(event) => updateField(field.key, event.target.value)}
                placeholder={field.placeholder}
                rows={3}
                value={form[field.key] ?? ""}
              />
            ) : (
              <TextInput
                onChange={(event) => updateField(field.key, event.target.value)}
                placeholder={field.placeholder}
                value={form[field.key] ?? ""}
              />
            )}
          </Field>
        ))}
      </div>

      <footer className="form-actions">
        <Button disabled={isSubmitting || !form.name.trim()} type="submit">
          {isSubmitting ? "创建中…" : "创建项目"}
        </Button>
      </footer>
    </form>
  );
}
