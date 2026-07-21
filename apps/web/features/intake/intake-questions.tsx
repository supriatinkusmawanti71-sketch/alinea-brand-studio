"use client";

import { FormEvent, useState } from "react";

import { Button, Field, TextArea, TextInput } from "@/components/ui";
import type { IntakeAnswer, IntakeQuestion, IntakeResult, JsonValue } from "@/lib/api/types";

type IntakeQuestionsProps = {
  intakeRunId: string;
  isSubmitting: boolean;
  onSubmit: (intakeRunId: string, answers: IntakeAnswer[]) => Promise<void>;
  result: IntakeResult;
};

type AnswerDraft = Record<string, string | string[]>;

function initialDraft(questions: IntakeQuestion[]) {
  return questions.reduce<AnswerDraft>((draft, question) => {
    draft[question.id] = question.answer_type === "MULTI_CHOICE" ? [] : "";
    return draft;
  }, {});
}

function splitListAnswer(value: string) {
  return value
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toAnswerValue(question: IntakeQuestion, value: string | string[]): JsonValue {
  if (question.answer_type === "TEXT_LIST") {
    return splitListAnswer(String(value));
  }
  if (question.answer_type === "MULTI_CHOICE") {
    return Array.isArray(value) ? value : [];
  }
  return String(value).trim();
}

function hasAnswer(question: IntakeQuestion, value: string | string[]) {
  if (!question.required) {
    return true;
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (question.answer_type === "TEXT_LIST") {
    return splitListAnswer(value).length > 0;
  }
  return value.trim().length > 0;
}

export function IntakeQuestions({
  intakeRunId,
  isSubmitting,
  onSubmit,
  result,
}: IntakeQuestionsProps) {
  const [draft, setDraft] = useState<AnswerDraft>(() => initialDraft(result.questions));
  const [validationMessage, setValidationMessage] = useState<string | null>(null);

  function updateText(questionId: string, value: string) {
    setDraft((current) => ({ ...current, [questionId]: value }));
  }

  function updateMultiChoice(questionId: string, option: string, checked: boolean) {
    setDraft((current) => {
      const existing = current[questionId];
      const values = Array.isArray(existing) ? existing : [];
      return {
        ...current,
        [questionId]: checked
          ? [...values, option]
          : values.filter((value) => value !== option),
      };
    });
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const missing = result.questions.find(
      (question) => !hasAnswer(question, draft[question.id] ?? ""),
    );
    if (missing) {
      setValidationMessage(`请先回答：${missing.prompt}`);
      return;
    }

    setValidationMessage(null);
    const answers = result.questions.map((question) => ({
      field_path: question.field_path,
      value: toAnswerValue(question, draft[question.id] ?? ""),
    }));
    await onSubmit(intakeRunId, answers);
  }

  return (
    <section className="intake-panel">
      <header className="section-header">
        <span className="step-pill">Intake 补问</span>
        <h2>补齐品牌信息</h2>
        <p>补充这些信息后，系统会继续生成品牌方向。</p>
      </header>

      {result.conflicts.length > 0 ? (
        <div className="notice notice--warning">
          {result.conflicts.map((conflict) => (
            <p key={conflict.code}>{conflict.message}</p>
          ))}
        </div>
      ) : null}

      <form className="question-form" onSubmit={handleSubmit}>
        {result.questions.map((question) => {
          const value = draft[question.id] ?? "";
          return (
            <fieldset className="question-card" key={question.id}>
              <legend>{question.prompt}</legend>
              <p>{question.reason}</p>
              <code>{question.field_path}</code>

              {question.answer_type === "TEXT" ? (
                <Field label="回答">
                  <TextInput
                    onChange={(event) => updateText(question.id, event.target.value)}
                    required={question.required}
                    value={String(value)}
                  />
                </Field>
              ) : null}

              {question.answer_type === "TEXT_LIST" ? (
                <Field hint="一行一个，也可以用逗号分隔。" label="回答列表">
                  <TextArea
                    onChange={(event) => updateText(question.id, event.target.value)}
                    required={question.required}
                    rows={3}
                    value={String(value)}
                  />
                </Field>
              ) : null}

              {question.answer_type === "SINGLE_CHOICE" ? (
                <div className="choice-stack">
                  {question.options.map((option) => (
                    <label key={option}>
                      <input
                        checked={value === option}
                        name={question.id}
                        onChange={() => updateText(question.id, option)}
                        required={question.required}
                        type="radio"
                      />
                      <span>{option}</span>
                    </label>
                  ))}
                </div>
              ) : null}

              {question.answer_type === "MULTI_CHOICE" ? (
                <div className="choice-stack">
                  {question.options.map((option) => (
                    <label key={option}>
                      <input
                        checked={Array.isArray(value) && value.includes(option)}
                        onChange={(event) =>
                          updateMultiChoice(question.id, option, event.target.checked)
                        }
                        type="checkbox"
                      />
                      <span>{option}</span>
                    </label>
                  ))}
                </div>
              ) : null}
            </fieldset>
          );
        })}

        {validationMessage ? <p className="form-error">{validationMessage}</p> : null}

        <footer className="form-actions">
          <Button disabled={isSubmitting} type="submit">
            {isSubmitting ? "提交中…" : "提交答案并生成 Directions"}
          </Button>
        </footer>
      </form>
    </section>
  );
}
