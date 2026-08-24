#!/usr/bin/env python3
"""Build the coding-agent n8n workflow JSON and optionally upload it."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "n8n" / "coding-agent.workflow.json"

OPENAI_CRED = {
    "openAiApi": {
        "id": "i92Ks4Gct1VxKMmv",
        "name": "OpenAI account Proxy",
    }
}
BALE_CRED = {
    "telegramApi": {
        "id": "PNyaR1tMoqmUKJQW",
        "name": "Bale account",
    }
}
BALE_CHAT_ID = "1753826181"
DATA_TABLE = {
    "__rl": True,
    "value": "GLZaGFNzA5EP8Jyl",
    "mode": "list",
    "cachedResultName": "coding_agent_memory",
}
MODEL = {
    "__rl": True,
    "value": "gpt-5.6-luna",
    "mode": "id",
}

PLANNER_SYS = """You are Planner, one role in a multi-agent C# coding system.
Always use model-facing JSON only. No markdown fences.

The user request may be in Persian or English. Think in the user's language for titles/summaries.
You only PLAN. Do not write source code.

Output exactly this JSON schema:
{
  "title": "string",
  "summary": "string",
  "assumptions": ["string"],
  "steps": ["string"],
  "files": [{"path": "string", "purpose": "string"}],
  "kind": "console" or "web",
  "run_expectation": "what a successful sandbox run should print or return",
  "risks": ["string"]
}

Rules:
- Target .NET 8 C# only. No JavaScript, Python, or other languages.
- Prefer a small, testable console app unless the user clearly asked for a web API.
- Keep scope small enough to compile and run in an isolated sandbox within 60 seconds.
- If the request is vague, pick reasonable defaults and list them in assumptions.
- If previous human feedback exists, incorporate it.
- If long-term memory lessons exist, reuse patterns that worked and avoid known failures.
"""

CODER_SYS = """You are Coder. Write a complete .NET 8 C# project from the approved plan.
Output JSON only, no markdown fences.

Schema:
{
  "kind": "console" or "web",
  "files": {
     "relative/path.cs": "full file contents",
     "App.csproj": "csproj contents"
  },
  "notes": "short"
}

Rules:
- C# / .NET 8 only.
- Always include a .csproj targeting net8.0.
- Console apps must write a clear success line to stdout.
- Web apps must use WebApplication.CreateBuilder, listen on ASPNETCORE_URLS, and expose GET /.
- Do not use external NuGet packages except the BCL / shared framework.
- No network calls, no file system access outside the app directory, no infinite loops.
- Produce a complete project that `dotnet restore && dotnet build && dotnet run` can execute.
- If human feedback exists, honor it.
"""

REVIEWER_SYS = """You are Reviewer/Tester. You receive the plan, the generated files, and REAL sandbox execution results.
Decide if the run satisfies the plan. Output JSON only.

Schema:
{
  "passed": true or false,
  "summary": "string",
  "issues": ["string"],
  "stdout_assessment": "string"
}

Rules:
- passed=true only if the sandbox compiled and ran (exit 0, not timed out) AND output matches the plan reasonably.
- Compile errors, timeouts, empty output when output was expected, or runtime exceptions => passed=false.
- Be strict but practical. A small working app beats an incomplete large one.
"""

FIXER_SYS = """You are Fixer. You receive the current files plus the real sandbox error/output and reviewer issues.
Rewrite the project so the next sandbox run succeeds. Output JSON only, same schema as Coder:

{
  "kind": "console" or "web",
  "files": {"relative/path": "contents"},
  "notes": "what you changed"
}

Rules:
- C# / .NET 8 only. Full files, not patches.
- Fix the actual error text. Do not repeat a previous failing approach if it is listed in prior attempts.
- Keep the approved plan and human feedback.
- No extra NuGet packages.
"""


def uid() -> str:
    return str(uuid.uuid4())


def llm(name: str, x: int, y: int) -> dict:
    return {
        "parameters": {
            "model": MODEL,
            "options": {"temperature": 0.2},
        },
        "id": uid(),
        "name": name,
        "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
        "typeVersion": 1.3,
        "position": [x, y],
        "credentials": OPENAI_CRED,
    }


def agent(name: str, x: int, y: int, prompt_expr: str, system: str) -> dict:
    return {
        "parameters": {
            "promptType": "define",
            "text": prompt_expr,
            "options": {
                "systemMessage": system,
                "maxIterations": 3,
            },
        },
        "id": uid(),
        "name": name,
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 3.1,
        "position": [x, y],
    }


def code(name: str, x: int, y: int, js: str, extra: dict | None = None) -> dict:
    node = {
        "parameters": {"jsCode": js},
        "id": uid(),
        "name": name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [x, y],
    }
    if extra:
        node.update(extra)
    return node


def sticky(name: str, x: int, y: int, w: int, h: int, content: str, color: int = 7) -> dict:
    return {
        "parameters": {"content": content, "width": w, "height": h, "color": color},
        "id": uid(),
        "name": name,
        "type": "n8n-nodes-base.stickyNote",
        "typeVersion": 1,
        "position": [x, y],
    }


def conn(src: str, dst: str, src_type: str = "main", index: int = 0) -> tuple:
    return src, src_type, index, dst


JS_EXTRACT = r"""
function extractJson(text) {
  if (text && typeof text === 'object' && !Array.isArray(text)) return text;
  const raw0 = String(text || '').trim();
  const unfenced = raw0.replace(/```json/gi, '```');
  const fence = unfenced.match(/```\s*([\s\S]*?)```/);
  const raw = fence ? fence[1] : unfenced;
  const start = raw.indexOf('{');
  const end = raw.lastIndexOf('}');
  if (start < 0 || end <= start) throw new Error('Model did not return JSON');
  return JSON.parse(raw.slice(start, end + 1));
}
function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
"""


def build_workflow(sandbox_url: str, sandbox_token: str) -> dict:
    form_trigger = {
        "parameters": {
            "formTitle": "ایجنت کدنویس C#",
            "formDescription": "درخواست را بنویسید. برنامه به بله ارسال می‌شود؛ تأیید و بازخورد متنی را همان‌جا بدهید. سپس کد تولید، در sandbox اجرا و در GitHub به‌صورت PR ثبت می‌شود.",
            "formFields": {
                "values": [
                    {
                        "fieldLabel": "درخواست",
                        "fieldName": "user_request",
                        "fieldType": "textarea",
                        "placeholder": "مثال: یک اپ کنسول مدیریت وظایف با دسته‌بندی بساز",
                        "requiredField": True,
                    },
                    {
                        "fieldLabel": "نام پروژه (اختیاری)",
                        "fieldName": "project_name",
                        "fieldType": "text",
                        "placeholder": "task-manager",
                    },
                ]
            },
            "responseMode": "onReceived",
            "options": {
                "path": "coding-agent",
                "buttonLabel": "شروع",
                "appendAttribution": False,
                "respondWith": "text",
                "formSubmittedText": "درخواست ثبت شد. برنامه Planner به بله ارسال می‌شود؛ پاسخ را در همان چت بدهید.",
            },
        },
        "id": uid(),
        "name": "On form submission",
        "type": "n8n-nodes-base.formTrigger",
        "typeVersion": 2.2,
        "position": [0, 0],
        "webhookId": uid(),
    }

    load_memory = {
        "parameters": {
            "operation": "get",
            "dataTableId": DATA_TABLE,
            "returnAll": False,
            "limit": 8,
            "orderBy": True,
            "orderByColumn": "createdAt",
            "orderByDirection": "DESC",
            "matchType": "anyCondition",
            "filters": {},
        },
        "id": uid(),
        "name": "Load long-term memory",
        "type": "n8n-nodes-base.dataTable",
        "typeVersion": 1.1,
        "position": [240, 0],
        "alwaysOutputData": True,
    }

    init_state = code(
        "Init State",
        480,
        0,
        f"""
const form = $('On form submission').first().json;
const memory = $input.all().map(i => ({{
  user_request: i.json.user_request || '',
  lesson: i.json.lesson || ''
}})).filter(x => x.lesson || x.user_request);

const runId = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
return [{{ json: {{
  run_id: runId,
  started_at: new Date().toISOString(),
  user_request: form.user_request || form['درخواست'] || '',
  project_name: form.project_name || form['نام پروژه (اختیاری)'] || ('app-' + runId),
  memory,
  plan_round: 1,
  max_plan_rounds: 3,
  fix_attempt: 0,
  max_fix: 3,
  human_feedback: '',
  decision: '',
  plan: null,
  files: {{}},
  kind: 'console',
  attempts: [],
  execution: null,
  review: null,
  github: null,
  sandbox_url: {json.dumps(sandbox_url)},
  sandbox_token: {json.dumps(sandbox_token)}
}}}}];
""".strip(),
    )

    plan_anchor = code("Plan Anchor", 720, 0, "return [{ json: $input.item.json }];")

    build_planner = code(
        "Build Planner Prompt",
        960,
        0,
        """
const s = $input.item.json;
const mem = (s.memory || []).slice(0, 8).map((m, i) =>
  `#${i+1} request: ${m.user_request}\\nlesson: ${m.lesson}`).join('\\n\\n') || '(empty)';
const prompt = [
  'User request:', s.user_request,
  '',
  'Project name:', s.project_name,
  '',
  'Plan round:', s.plan_round, 'of', s.max_plan_rounds,
  '',
  'Human feedback so far:', s.human_feedback || '(none)',
  '',
  'Long-term memory from previous runs:',
  mem
].join('\\n');
return [{ json: { ...s, prompt } }];
""".strip(),
    )

    planner = agent("Planner", 1200, 0, "={{ $json.prompt }}", PLANNER_SYS)
    planner_llm = llm("LLM Planner gpt-5.6-luna", 1200, 260)

    parse_plan = code(
        "Parse Plan",
        1480,
        0,
        JS_EXTRACT
        + """
const s = $('Build Planner Prompt').item.json;
let plan;
try { plan = extractJson($input.item.json.output); }
catch (e) {
  plan = {
    title: s.project_name,
    summary: 'Planner JSON parse failed; using a minimal console app plan. ' + e.message,
    assumptions: ['Fallback plan because planner output was not valid JSON'],
    steps: ['Create a .NET 8 console app that prints a result for the user request'],
    files: [{ path: 'Program.cs', purpose: 'entry' }, { path: 'App.csproj', purpose: 'project' }],
    kind: 'console',
    run_expectation: 'Process exits 0 and prints a short success message',
    risks: ['Original planner output was malformed']
  };
}
const planText = JSON.stringify(plan, null, 2);
let plan_telegram = '📋 برنامه Planner\\n\\nعنوان: ' + (plan.title || '') +
  '\\nخلاصه: ' + (plan.summary || '') +
  '\\n\\n' + planText;
if (plan_telegram.length > 3500) plan_telegram = plan_telegram.slice(0, 3500) + '\\n…';
plan_telegram += '\\n\\nدکمه را بزنید. تصمیم (تأیید یا اصلاح) و بازخورد متنی را بفرستید. بازخورد خالی مجاز نیست.';
return [{ json: { ...s, plan, kind: plan.kind || 'console', plan_telegram } }];
""".strip(),
    )

    hitl = {
        "parameters": {
            "operation": "sendAndWait",
            "chatId": BALE_CHAT_ID,
            "message": "={{ $json.plan_telegram }}",
            "responseType": "customForm",
            "defineForm": "fields",
            "formFields": {
                "values": [
                    {
                        "fieldLabel": "تصمیم",
                        "fieldName": "decision",
                        "fieldType": "dropdown",
                        "fieldOptions": {
                            "values": [
                                {"option": "تأیید و ادامه"},
                                {"option": "اصلاح برنامه"},
                            ]
                        },
                        "requiredField": True,
                    },
                    {
                        "fieldLabel": "بازخورد متنی",
                        "fieldName": "feedback",
                        "fieldType": "textarea",
                        "placeholder": "حتماً بنویسید: تأیید با توضیح، یا تغییرات درخواستی",
                        "requiredField": True,
                    },
                ]
            },
            "options": {
                "messageButtonLabel": "بازخورد بده",
                "responseFormTitle": "بازبینی برنامه Planner",
                "responseFormDescription": "تصمیم بگیرید و بازخورد متنی بنویسید. بازخورد خالی مجاز نیست.",
                "responseFormButtonLabel": "ارسال",
            },
        },
        "id": uid(),
        "name": "Human review of plan",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [1760, 0],
        "webhookId": uid(),
        "credentials": BALE_CRED,
    }

    apply_hitl = code(
        "Apply human feedback",
        2040,
        0,
        """
const s = $('Parse Plan').item.json;
const form = $input.item.json || {};
const data = form.data || form;
const decision = data.decision || data['تصمیم'] || form.decision || form.text || data.text || '';
const feedback = data.feedback || data['بازخورد متنی'] || form.feedback || form.text || data.text || '';
s.decision = String(decision);
s.human_feedback = [s.human_feedback, feedback].filter(Boolean).join('\\n---\\n');
s.needs_replan = String(decision).includes('اصلاح') && (s.plan_round < s.max_plan_rounds);
if (s.needs_replan) s.plan_round += 1;
return [{ json: s }];
""".strip(),
    )

    if_replan = {
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 2,
                },
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": "={{ $json.needs_replan }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "id": uid(),
        "name": "Need replan?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [2280, 0],
    }

    build_coder = code(
        "Build Coder Prompt",
        2560,
        0,
        """
const s = $input.item.json;
const prompt = [
  'User request:', s.user_request,
  '',
  'Human feedback:', s.human_feedback || '(none)',
  '',
  'Approved plan JSON:',
  JSON.stringify(s.plan, null, 2)
].join('\\n');
return [{ json: { ...s, prompt } }];
""".strip(),
    )

    coder = agent("Coder", 2800, 0, "={{ $json.prompt }}", CODER_SYS)
    coder_llm = llm("LLM Coder gpt-5.6-luna", 2800, 260)

    parse_code = code(
        "Parse Code",
        3080,
        0,
        JS_EXTRACT
        + """
const s = $('Build Coder Prompt').item.json;
let payload;
try { payload = extractJson($input.item.json.output); }
catch (e) {
  payload = {
    kind: 'console',
    files: {
      'App.csproj': '<Project Sdk="Microsoft.NET.Sdk">\\n  <PropertyGroup>\\n    <OutputType>Exe</OutputType>\\n    <TargetFramework>net8.0</TargetFramework>\\n    <ImplicitUsings>enable</ImplicitUsings>\\n    <Nullable>enable</Nullable>\\n  </PropertyGroup>\\n</Project>\\n',
      'Program.cs': 'Console.WriteLine("Coder JSON parse failed: ' + String(e.message).replace(/"/g, '') + '");\\n'
    },
    notes: 'fallback because coder output was not JSON'
  };
}
const files = payload.files || {};
if (!Object.keys(files).length) throw new Error('Coder returned no files');
return [{ json: { ...s, files, kind: payload.kind || s.kind || 'console', coder_notes: payload.notes || '' } }];
""".strip(),
    )

    loop_anchor = code("Loop Anchor", 3320, 0, "return [{ json: $input.item.json }];")

    execute = {
        "parameters": {
            "method": "POST",
            "url": "={{ $json.sandbox_url }}/execute",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "X-Sandbox-Token", "value": "={{ $json.sandbox_token }}"},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ run_id: $json.run_id, kind: $json.kind, timeout_seconds: 60, files: $json.files }) }}",
            "options": {
                "timeout": 130000,
                "response": {"response": {"neverError": True}},
            },
        },
        "id": uid(),
        "name": "Execute in C# sandbox",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [3560, 0],
        "onError": "continueRegularOutput",
    }

    merge_run = code(
        "Merge sandbox result",
        3800,
        0,
        """
const state = $('Loop Anchor').item.json;
const exec = $input.item.json || {};
state.execution = exec;
state.attempts = state.attempts || [];
state.attempts.push({
  n: state.attempts.length + 1,
  stage: exec.stage || 'run',
  ok: !!exec.ok,
  exit_code: exec.exit_code,
  timed_out: !!exec.timed_out,
  stdout: exec.stdout || '',
  stderr: exec.stderr || '',
  http_body: exec.http_body || '',
  duration_ms: exec.duration_ms
});
return [{ json: state }];
""".strip(),
    )

    build_reviewer = code(
        "Build Reviewer Prompt",
        4040,
        0,
        """
const s = $input.item.json;
const fileList = Object.keys(s.files || {}).join(', ');
const prompt = [
  'User request:', s.user_request,
  '',
  'Plan:', JSON.stringify(s.plan, null, 2),
  '',
  'Human feedback:', s.human_feedback || '(none)',
  '',
  'Files:', fileList,
  '',
  'Sandbox result JSON:', JSON.stringify(s.execution, null, 2),
  '',
  'Previous attempts:', JSON.stringify(s.attempts, null, 2)
].join('\\n');
return [{ json: { ...s, prompt } }];
""".strip(),
    )

    reviewer = agent("Reviewer / Tester", 4280, 0, "={{ $json.prompt }}", REVIEWER_SYS)
    reviewer_llm = llm("LLM Reviewer gpt-5.6-luna", 4280, 260)

    parse_review = code(
        "Parse Review",
        4560,
        0,
        JS_EXTRACT
        + """
const s = $('Build Reviewer Prompt').item.json;
let review;
try { review = extractJson($input.item.json.output); }
catch (e) {
  review = {
    passed: false,
    summary: 'Reviewer JSON parse failed: ' + e.message,
    issues: ['Could not parse reviewer output'],
    stdout_assessment: ''
  };
}
if (s.execution && s.execution.ok === false) review.passed = false;
const needs_fix = review.passed !== true && s.fix_attempt < s.max_fix;
return [{ json: { ...s, review, needs_fix } }];
""".strip(),
    )

    if_fix = {
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 2,
                },
                "conditions": [
                    {
                        "id": uid(),
                        "leftValue": "={{ $json.needs_fix }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "id": uid(),
        "name": "Need fix?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [4800, 0],
    }

    build_fixer = code(
        "Build Fixer Prompt",
        4800,
        280,
        """
const s = $input.item.json;
s.fix_attempt = (s.fix_attempt || 0) + 1;
const prompt = [
  'User request:', s.user_request,
  '',
  'Plan:', JSON.stringify(s.plan, null, 2),
  '',
  'Human feedback:', s.human_feedback || '(none)',
  '',
  'Fix attempt:', s.fix_attempt, 'of', s.max_fix,
  '',
  'Current files JSON:', JSON.stringify(s.files),
  '',
  'Last sandbox result:', JSON.stringify(s.execution, null, 2),
  '',
  'Reviewer issues:', JSON.stringify(s.review, null, 2),
  '',
  'Prior attempts (do not repeat failing approaches):',
  JSON.stringify(s.attempts, null, 2)
].join('\\n');
return [{ json: { ...s, prompt } }];
""".strip(),
    )

    fixer = agent("Fixer", 5080, 280, "={{ $json.prompt }}", FIXER_SYS)
    fixer_llm = llm("LLM Fixer gpt-5.6-luna", 5080, 520)

    parse_fix = code(
        "Parse Fix",
        5360,
        280,
        JS_EXTRACT
        + """
const s = $('Build Fixer Prompt').item.json;
let payload;
try { payload = extractJson($input.item.json.output); }
catch (e) {
  payload = { kind: s.kind, files: s.files, notes: 'Fixer JSON parse failed: ' + e.message };
}
const files = payload.files && Object.keys(payload.files).length ? payload.files : s.files;
return [{ json: { ...s, files, kind: payload.kind || s.kind, fixer_notes: payload.notes || '' } }];
""".strip(),
    )

    draft_report = code(
        "Draft report",
        5080,
        -160,
        """
const s = $input.item.json;
const files = Object.keys(s.files || {});
const attempts = s.attempts || [];
const passed = !!(s.review && s.review.passed);
s.report_md = [
  '# گزارش اجرای ایجنت کدنویس',
  '',
  '- Run ID: `' + s.run_id + '`',
  '- زمان شروع: ' + s.started_at,
  '- مدل: `gpt-5.6-luna`',
  '- نتیجه موقت: ' + (passed ? 'موفق' : 'ناموفق تا این لحظه'),
  '',
  '## درخواست کاربر',
  '',
  s.user_request,
  '',
  '## بازخورد انسان',
  '',
  s.human_feedback || '(ثبت نشد)',
  '',
  '## برنامه Planner',
  '',
  '```json',
  JSON.stringify(s.plan, null, 2),
  '```',
  '',
  '## فایل‌های پروژه',
  '',
  files.map(f => '- `' + f + '`').join('\\n') || '(هیچ)',
  '',
  '## نتیجه اجرای واقعی sandbox',
  '',
  '```json',
  JSON.stringify(s.execution, null, 2),
  '```'
].join('\\n');
return [{ json: s }];
""".strip(),
    )

    github = {
        "parameters": {
            "method": "POST",
            "url": "={{ $json.sandbox_url }}/github/publish",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "X-Sandbox-Token", "value": "={{ $json.sandbox_token }}"},
                    {"name": "Content-Type", "value": "application/json"},
                ]
            },
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ run_id: $json.run_id, title: 'feat: ' + ($json.plan && $json.plan.title ? $json.plan.title : $json.project_name), body: 'Automated PR from n8n coding agent.\\n\\nRequest:\\n' + $json.user_request + '\\n\\nHuman feedback:\\n' + ($json.human_feedback || '(none)'), files: $json.files, report_md: $json.report_md || '' }) }}",
            "options": {
                "timeout": 120000,
                "response": {"response": {"neverError": True}},
            },
        },
        "id": uid(),
        "name": "Open GitHub PR",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [5080, 0],
        "onError": "continueRegularOutput",
    }

    merge_gh = code(
        "Merge GitHub result",
        5320,
        0,
        """
const s = $('Parse Review').item.json;
s.github = $input.item.json || {};
const passed = !!(s.review && s.review.passed);
const stuck = !passed;
const files = Object.keys(s.files || {});
const attempts = s.attempts || [];
const last = attempts[attempts.length - 1] || {};
const lessonObj = {
  run_id: s.run_id,
  success: passed,
  kind: s.kind,
  fix_attempts: s.fix_attempt,
  last_stage: last.stage || null,
  last_stderr: (last.stderr || '').slice(0, 500),
  github_pr: s.github.pr_url || s.github.html_url || '',
  pattern: passed ? 'Succeeded with this plan/kind' : 'Failed after max fixes; avoid this error pattern'
};
s.lesson = JSON.stringify(lessonObj);
s.stuck = stuck;
s.report_md = [
  '# گزارش اجرای ایجنت کدنویس',
  '',
  '- Run ID: `' + s.run_id + '`',
  '- زمان شروع: ' + s.started_at,
  '- مدل: `gpt-5.6-luna`',
  '- نتیجه: ' + (passed ? 'موفق' : 'ناموفق / گیر کرده پس از محدودیت‌ها'),
  '',
  '## درخواست کاربر',
  '',
  s.user_request,
  '',
  '## بازخورد انسان',
  '',
  s.human_feedback || '(ثبت نشد)',
  '',
  '## برنامه Planner',
  '',
  '```json',
  JSON.stringify(s.plan, null, 2),
  '```',
  '',
  '## فایل‌های پروژه',
  '',
  files.map(f => '- `' + f + '`').join('\\n') || '(هیچ)',
  '',
  '## نتیجه اجرای واقعی sandbox',
  '',
  '```json',
  JSON.stringify(s.execution, null, 2),
  '```',
  '',
  '## تلاش‌های اصلاح (حداکثر ۳)',
  '',
  '```json',
  JSON.stringify(attempts, null, 2),
  '```',
  '',
  '## نظر Reviewer',
  '',
  '```json',
  JSON.stringify(s.review, null, 2),
  '```',
  '',
  '## GitHub PR',
  '',
  s.github.pr_url || s.github.error || JSON.stringify(s.github),
  '',
  stuck ? '## چرا گیر کرد\\n\\nپس از ' + s.fix_attempt + ' تلاش اصلاح، اجرا موفق نشد. آخرین خطا در stderr بالا آمده است.' : ''
].join('\\n');
s.report_html = '<pre>' + s.report_md.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</pre>';
return [{ json: s }];
""".strip(),
    )

    save_memory = {
        "parameters": {
            "operation": "insert",
            "dataTableId": DATA_TABLE,
            "columns": {
                "mappingMode": "defineBelow",
                "value": {
                    "user_request": "={{ $json.user_request }}",
                    "lesson": "={{ $json.lesson }}",
                },
                "matchingColumns": [],
                "schema": [
                    {
                        "id": "user_request",
                        "displayName": "user_request",
                        "required": False,
                        "defaultMatch": False,
                        "display": True,
                        "type": "string",
                        "canBeUsedToMatch": True,
                    },
                    {
                        "id": "lesson",
                        "displayName": "lesson",
                        "required": False,
                        "defaultMatch": False,
                        "display": True,
                        "type": "string",
                        "canBeUsedToMatch": True,
                    },
                ],
                "attemptToConvertTypes": False,
                "convertFieldsToString": False,
            },
            "options": {},
        },
        "id": uid(),
        "name": "Save long-term memory",
        "type": "n8n-nodes-base.dataTable",
        "typeVersion": 1.1,
        "position": [5560, 0],
        "onError": "continueRegularOutput",
    }

    keep_report = code(
        "Prepare report for Bale",
        5800,
        0,
        """
const s = $('Merge GitHub result').item.json;
let text = String(s.report_md || '');
if (text.length > 4000) text = text.slice(0, 4000) + '\\n…';
return [{ json: { ...s, report_telegram: text } }];
""".strip(),
    )

    ending = {
        "parameters": {
            "chatId": BALE_CHAT_ID,
            "text": "={{ $json.report_telegram }}",
            "additionalFields": {
                "appendAttribution": False,
            },
        },
        "id": uid(),
        "name": "Send Markdown report",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [6040, 0],
        "webhookId": uid(),
        "credentials": BALE_CRED,
        "onError": "continueRegularOutput",
    }

    notes = [
        sticky(
            "Sticky architecture",
            -40,
            -420,
            520,
            360,
            "## معماری چند-عاملی\n\n1. **Planner** — تجزیه درخواست\n2. **Human-in-the-Loop** — تأیید + بازخورد متنی در بله (Telegram node + Bale account)\n3. **Coder** — تولید پروژه C# / .NET 8\n4. **Sandbox Docker** — اجرای واقعی با timeout\n5. **Reviewer/Tester** — قضاوت روی خروجی واقعی\n6. **Fixer** — حداکثر ۳ اصلاح\n\nمدل همه نقش‌ها: `gpt-5.6-luna`",
            6,
        ),
        sticky(
            "Sticky limits",
            1760,
            -300,
            420,
            240,
            "## محدودیت منابع\n\n- حداکثر ۳ تلاش Fixer\n- timeout کل ورک‌فلو: ۱۵ دقیقه\n- timeout هر اجرای sandbox: ۶۰ ثانیه\n- حافظه کانتینر: ۱GB\n\nاگر موفق نشد، گزارش Markdown می‌گوید کجا گیر کرد.",
            5,
        ),
        sticky(
            "Sticky memory github",
            5080,
            -300,
            420,
            240,
            "## حافظه و GitHub\n\n- کوتاه‌مدت: state بین نودها (`attempts`, فایل‌ها، خطاها)\n- بلندمدت: Data Table `coding_agent_memory`\n- خروجی: PR روی `ashkandehnavi/n8n-code`",
            4,
        ),
    ]

    nodes = notes + [
        form_trigger,
        load_memory,
        init_state,
        plan_anchor,
        build_planner,
        planner,
        planner_llm,
        parse_plan,
        hitl,
        apply_hitl,
        if_replan,
        build_coder,
        coder,
        coder_llm,
        parse_code,
        loop_anchor,
        execute,
        merge_run,
        build_reviewer,
        reviewer,
        reviewer_llm,
        parse_review,
        if_fix,
        draft_report,
        build_fixer,
        fixer,
        fixer_llm,
        parse_fix,
        github,
        merge_gh,
        save_memory,
        keep_report,
        ending,
    ]

    pairs = [
        conn("On form submission", "Load long-term memory"),
        conn("Load long-term memory", "Init State"),
        conn("Init State", "Plan Anchor"),
        conn("Plan Anchor", "Build Planner Prompt"),
        conn("Build Planner Prompt", "Planner"),
        conn("LLM Planner gpt-5.6-luna", "Planner", "ai_languageModel", 0),
        conn("Planner", "Parse Plan"),
        conn("Parse Plan", "Human review of plan"),
        conn("Human review of plan", "Apply human feedback"),
        conn("Apply human feedback", "Need replan?"),
        # IF true = replan, false = coder
        conn("Need replan?", "Plan Anchor", "main", 0),
        conn("Need replan?", "Build Coder Prompt", "main", 1),
        conn("Build Coder Prompt", "Coder"),
        conn("LLM Coder gpt-5.6-luna", "Coder", "ai_languageModel", 0),
        conn("Coder", "Parse Code"),
        conn("Parse Code", "Loop Anchor"),
        conn("Loop Anchor", "Execute in C# sandbox"),
        conn("Execute in C# sandbox", "Merge sandbox result"),
        conn("Merge sandbox result", "Build Reviewer Prompt"),
        conn("Build Reviewer Prompt", "Reviewer / Tester"),
        conn("LLM Reviewer gpt-5.6-luna", "Reviewer / Tester", "ai_languageModel", 0),
        conn("Reviewer / Tester", "Parse Review"),
        conn("Parse Review", "Need fix?"),
        conn("Need fix?", "Build Fixer Prompt", "main", 0),
        conn("Need fix?", "Draft report", "main", 1),
        conn("Draft report", "Open GitHub PR"),
        conn("Build Fixer Prompt", "Fixer"),
        conn("LLM Fixer gpt-5.6-luna", "Fixer", "ai_languageModel", 0),
        conn("Fixer", "Parse Fix"),
        conn("Parse Fix", "Loop Anchor"),
        conn("Open GitHub PR", "Merge GitHub result"),
        conn("Merge GitHub result", "Save long-term memory"),
        conn("Save long-term memory", "Prepare report for Bale"),
        conn("Prepare report for Bale", "Send Markdown report"),
    ]

    connections: dict = {}
    for src, src_type, index, dst in pairs:
        connections.setdefault(src, {}).setdefault(src_type, [])
        outputs = connections[src][src_type]
        while len(outputs) <= index:
            outputs.append([])
        outputs[index].append({"node": dst, "type": src_type if src_type != "ai_languageModel" else "ai_languageModel", "index": 0})

    # ai_languageModel destination type must be ai_languageModel
    for src, block in connections.items():
        if "ai_languageModel" in block:
            for branch in block["ai_languageModel"]:
                for item in branch:
                    item["type"] = "ai_languageModel"

    return {
        "name": "final exam",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "binaryMode": "separate",
            "availableInMCP": False,
            "executionTimeout": 900,
            "timezone": "Asia/Tehran",
        },
        "pinData": {},
        "meta": {"templateCredsSetupCompleted": True},
    }


def main() -> None:
    sandbox_url = os.environ.get("SANDBOX_URL", "https://SANDBOX_URL_PLACEHOLDER").rstrip("/")
    sandbox_token = os.environ.get("SANDBOX_TOKEN", "SANDBOX_TOKEN_PLACEHOLDER")
    wf = build_workflow(sandbox_url, sandbox_token)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} nodes={len(wf['nodes'])}")


if __name__ == "__main__":
    main()
