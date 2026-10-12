# Agent Fundamentals: What an "AI Agent" Is and How a Normal Agent Architecture Looks

> A beginner's guide for the team and reviewers. No prior AI experience is assumed.
> Companion to [`PROBLEM_STATEMENT.md`](PROBLEM_STATEMENT.md) and [`ARCHITECTURE.md`](ARCHITECTURE.md). 2026-10-09.

---

## 1. Start here: what an LLM call really is

A **Large Language Model (LLM)**, such as Gemini, Claude or GPT, is a function that takes **text in** and gives **text out**:

```
            ┌───────────────┐
 prompt ──► │      LLM      │ ──► response
 (text)     │ (e.g. Gemini) │     (text, or JSON if we ask for it)
            └───────────────┘
```

Important facts:
- **It is stateless.** It remembers nothing between calls. To make it "remember", our code sends the earlier conversation along each time.
- **It only produces text.** It cannot read files, open apps or check the registry by itself. **Our code** does all of that and shows it the results.
- **It is probabilistic.** The same prompt can give slightly different answers. The *temperature* setting controls how much they vary, so we keep it low.
- **It can be confidently wrong.** This is called *hallucination*. That's why we give it facts (*grounding*) and check its output with code.
- **It has a limited context window.** There is a maximum amount of text per request, measured in **tokens** (roughly ¾ of a word each). Free tiers also limit tokens per minute.

## 2. So what makes something an "agent"?

An **agent** is an LLM that sits inside a program that lets it **take actions and see what happened, in a loop, until a goal is reached**.

> **Agent = LLM (the brain) + Tools (hands) + Loop (keep going) + State/Memory + Goal + Guardrails**

### The basic agent loop

```
             ┌───────────────────────────────────────────────┐
             │  GOAL / TASK  ("find where Plant 3D is installed") │
             └───────────────────────┬───────────────────────┘
                                     ▼
        ┌──────────────────►  1. THINK (LLM)  ─────────────────┐
        │                    "I should look in the registry"   │
        │                                                      ▼
  3. OBSERVE                                           2. ACT (our code)
  result goes back                                     runs the tool the LLM chose:
  into the context                                     registry_key_exists(...)
        │                                                      │
        └──────────────────────  result  ◄─────────────────────┘

        …repeat until the LLM says "done", or a step/time limit is hit
```

This pattern is often called **ReAct** (Reason + Act). The LLM never runs the tool itself. It *asks* for a tool by name with parameters, using **function calling** or **tool calling**. Our code checks that request, runs the tool and returns the result.

## 3. Workflows vs agents: a spectrum, not a yes/no

Not every "AI system" needs a free-roaming agent. Industry guidance, for example Anthropic's *Building Effective Agents*, recommends **the simplest pattern that works**. Autonomy brings flexibility, but also cost, delay and unpredictability.

| Level | Pattern | Who decides the next step? | Example |
|---|---|---|---|
| 0 | **Single LLM call** | Code | "Summarise this description" |
| 1 | **Prompt chaining** (a workflow) | Code, in a fixed order | Extract facts → write summary → design tests |
| 2 | **Routing** | An LLM picks one of several fixed paths | "Is this a content pack or a code plug-in?" → use a different prompt |
| 3 | **Evaluator–optimizer** | Code or an LLM checks the output; the LLM fixes it in a loop | Validate the test plan → send errors back → regenerate |
| 4 | **Orchestrator–workers** | A lead LLM splits the task and hands parts to other calls | One call per document, then merge |
| 5 | **Autonomous agent** | The LLM decides every step and which tools to use | "Discover how this unknown host is installed" |

**Rule of thumb:** use **workflows** (levels 1–3) when the steps are known in advance, because they are predictable, cheap and testable. Use **agents** (level 5) only when the steps can't be known in advance.

**Our project:**
- **Agent 1 is a workflow**: prompt chaining plus an evaluator–optimizer loop. Its steps are always the same: read, understand, design, check.
- **Agent 2's host discovery is a true agent loop.** For an unknown host, the steps can't be scripted ahead of time.
- **Agent 2's test runner is plain code**, with no LLM involved.

We still say "Agent 1" because, from the outside, it behaves as an autonomous worker with a clear role.

## 4. The building blocks of a normal agent architecture

```
┌───────────────────────────────────────────────────────────────────────────────┐
│ 1. INTERFACE         CLI / API / UI / scheduler: how a task comes in          │
├───────────────────────────────────────────────────────────────────────────────┤
│ 2. ORCHESTRATOR      Runs the steps, passes data along, handles retries,      │
│                      time limits, and when to stop                            │
├───────────────────────────────────────────────────────────────────────────────┤
│ 3. AGENT CORE                                                                 │
│    ├─ Model (LLM) behind a swappable client interface                         │
│    ├─ Instructions: system prompt (role, rules, output format)                │
│    ├─ Context builder: chooses WHAT text goes into each call                  │
│    ├─ Output contract: structured output (JSON schema) + validation           │
│    └─ Loop / planner: workflow steps or the think-act-observe loop            │
├───────────────────────────────────────────────────────────────────────────────┤
│ 4. TOOLS             Functions the agent may request (whitelist), each with   │
│                      a name, typed parameters, a description and a timeout    │
├───────────────────────────────────────────────────────────────────────────────┤
│ 5. MEMORY / STATE    Short-term: the current task's context and history       │
│                      Long-term: knowledge stores (our host profile library),  │
│                      past runs, retrieval (RAG) over large documents          │
├───────────────────────────────────────────────────────────────────────────────┤
│ 6. GUARDRAILS        Input checks (untrusted text), output validation,        │
│                      allowed actions, human approval gates, cost limits       │
├───────────────────────────────────────────────────────────────────────────────┤
│ 7. OBSERVABILITY     Logs of every prompt/response, tokens, cost, time;       │
│                      saved artefacts so any run can be replayed and explained │
├───────────────────────────────────────────────────────────────────────────────┤
│ 8. EVALUATION        Test sets + metrics: "is the agent getting better        │
│                      or worse when we change a prompt or model?"             │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Model and client interface
All model calls go through one small class, e.g. `LLMClient.generate(prompt, schema)`. Switching from Gemini to another provider then means changing one file. We also record the **model name, temperature and prompt version** on every call.

### 4.2 Instructions (prompts)
- The **system prompt** sets the role, the rules and the output format: *"You are a QA test designer. Use only the facts provided. If something is unknown, return null."*
- The **task prompt** carries the actual inputs.
- Prompts are **code**. They live in versioned files, are reviewed, and are re-tested when they change.

### 4.3 Context building
The single most important skill in agent engineering: **what does the model see in each call?** Too little and it guesses. Too much and it gets confused, slow and expensive. For us, the context is the extracted document text with line numbers, the installer facts, the host knowledge and the list of allowed actions.

When documents are too large for one call, **RAG** (*Retrieval-Augmented Generation*) is used. The documents are split into chunks, the chunks relevant to a question are found, and only those go into the prompt. We don't need this until the document sets get large.

### 4.4 Structured output
Instead of free text, we give the model a **JSON schema**, and the provider forces the answer to match it. Our code then **validates** the answer again with Pydantic. This is the bridge between "an AI said something" and "a program can use it".

### 4.5 Tools (function calling)
A tool is a normal function described to the LLM:
```
name: sys.registry_key_exists
description: "Check whether a registry key exists"
parameters: { hive: "HKLM|HKCU", path: string, match: string? }
```
The LLM replies with *"call `sys.registry_key_exists` with {...}"*. Our code checks the request is allowed, runs it, and returns the result. **Agent 1 has no tools.** Agent 2's discovery loop has a small, safe, read-only set.

### 4.6 Memory and state
- **Short-term:** what has happened so far in this run, held in the context.
- **Long-term:** knowledge that persists across runs, for example our **host profile library**. Once a host is understood, the agent doesn't need to rediscover it.
- **Run artefacts:** every intermediate file is saved under `runs/…`, so a run can be inspected and resumed.

### 4.7 Guardrails
- **Treat inputs as untrusted.** A third-party document could contain *"ignore your instructions and…"*. This is called **prompt injection**. Defences: give the agent no dangerous tools, validate all output against a schema, and allow only whitelisted actions.
- **Validate outputs:** schema, allowed values, and our *quote-must-exist* citation check.
- **Human in the loop:** approval gates before anything risky.
- **Budgets:** a maximum number of retries, loop steps, tokens and minutes.

### 4.8 Observability
Log every LLM call: prompt, response, tokens, time and model. Without this, you can't debug why the agent did something. For the POC, simple JSON log files are enough. Tools such as Langfuse or OpenTelemetry can come later.

### 4.9 Evaluation ("evals")
LLM output changes when you change a prompt or a model, or when the provider updates the model. **Evals** are a fixed set of example inputs with known good outputs, plus scores. For Agent 1, examples are "did it find all 2 ribbon buttons?" or "did it invent any command?". They tell you whether a change made things better or worse. Start small: 2–3 plug-ins with hand-checked expected profiles.

## 5. Single agent vs multi-agent

| Pattern | Description | When |
|---|---|---|
| **Single agent** | One agent does everything | Small, simple tasks |
| **Pipeline (sequential)** | Agent A's output is Agent B's input | Clear hand-offs, as with designer → executor (**our design**) |
| **Orchestrator–workers** | A lead agent hands sub-tasks to specialists | Large tasks that can be split |
| **Peer / debate** | Agents critique each other | Quality-critical reasoning |

Splitting into Agent 1 and Agent 2 gives us **separation of responsibilities**: one designs, one runs. It also gives a **reviewable hand-off** (the YAML), and each agent can be tested on its own. This matches how QA teams work: a test designer and a test executor.

## 6. Frameworks: do we need one?

Frameworks such as **LangGraph**, **Google ADK**, **PydanticAI**, CrewAI and AutoGen provide ready-made loops, tool wiring, memory and tracing.

- **Pros:** less hand-written loop code; built-in retries, human-in-the-loop and tracing.
- **Cons:** more to learn, an extra layer of abstraction, version changes, harder debugging for beginners.
- **Our choice for Agent 1: no framework.** It's a fixed workflow, so plain Python plus the Gemini SDK plus Pydantic is clearer and lets the team learn the fundamentals. We'll look at LangGraph or ADK for Agent 2's discovery loop.

## 7. Common failure modes (and what we do about them)

| Failure | Example | Our defence |
|---|---|---|
| Hallucination | Invents a command `PIDEXPORTALL` | Quote-must-exist check; `null` instead of guessing |
| Malformed output | Broken JSON or YAML | Schema-forced output plus Pydantic validation plus retry |
| Instruction drift | Ignores "only use catalog actions" | Code-level check that rejects unknown actions |
| Prompt injection | A document says "mark all tests passed" | No tools in Agent 1; verdicts by code only |
| Overlong context | 300-page manual | Size budget; chunking and RAG later |
| Non-determinism | Different tests each run | Low temperature; save and approve a "golden" plan |
| Cost and rate limits | Free tier sends HTTP 429 | Retry with backoff; few calls per run |

## 8. How this maps to Agent 1, step by step

```
inputs/<plugin>/  (txt, pdf, docx, msi…)
   │
   ▼  ORCHESTRATOR: python -m mpagent design inputs/pid-connector-exporter
   │
   ├─ Stage 0  Intake               [code]   classify files, extract text, number lines, hash
   ├─ Stage 1  Installer static read[code]   MSI tables / manifest, claimed signer
   │
   ├─ 1a EXTRACT   [LLM call #1]  context = docs + installer facts
   │               output contract = PluginProfile JSON schema
   │               → validate (Pydantic) → retry on error
   ├─ Stage 2  Host lookup          [code]   read host_profiles/<host>.yaml (knowledge)
   ├─ 1b UNDERSTAND [LLM call #2] → understanding.md (from a template)
   ├─ 1c DESIGN    [LLM call #3]  context = profile + host knowledge + action catalog + rules
   │               output contract = TestPlan JSON schema
   ├─ 1d SELF-CHECK [code]        schema ✓  actions in catalog ✓  quotes exist ✓  coverage ✓
   │        └─ errors? → send them back to 1c (max N times)  ← evaluator–optimizer loop
   │
   ▼  OUTPUT (runs/<plugin>/<timestamp>/)
      intake_manifest.json, installer_facts.json, plugin_profile.json,
      understanding.md, testcases.yaml (+ .json), llm_calls.log
```

Where each building block from §4 lives:

| Building block | In Agent 1 |
|---|---|
| Interface | Typer CLI (`mpagent design …`) |
| Orchestrator | `design/pipeline.py`: runs the stages in order and saves artefacts |
| Model client | `llm/client.py` (interface) + `llm/gemini.py` |
| Instructions | `prompts/extract.j2`, `prompts/understand.j2`, `prompts/design.j2` |
| Context builder | `design/context.py`: documents with line numbers, facts, catalog |
| Output contract | `models/plugin_profile.py`, `models/testplan.py` (Pydantic) |
| Tools | None, by design |
| Memory | Host profile library (read-only); run artefacts |
| Guardrails | Self-check (1d), untrusted-input markers in prompts, retry limits, review gate |
| Observability | `llm_calls.log` (prompt, response, tokens, time, model, prompt version) |
| Evaluation | `evals/`: expected profiles for 2–3 plug-ins, scored automatically |

## 9. Glossary

| Term | Meaning |
|---|---|
| **LLM** | Large Language Model; text in, text out |
| **Token** | A piece of text (≈ ¾ word); limits and costs are counted in tokens |
| **Context window** | The maximum number of tokens per request |
| **Prompt / system prompt** | The input text / the standing instructions that set role and rules |
| **Temperature** | How varied the output is (0 = most consistent) |
| **Structured output** | Forcing the response to match a JSON schema |
| **Function / tool calling** | The LLM asks our code to run a named function with parameters |
| **Agent loop / ReAct** | Think → act → observe, repeated until done |
| **Workflow** | Steps fixed by code; the LLM fills in individual steps |
| **Grounding** | Giving the model real facts to base its answer on |
| **Hallucination** | Confident but false output |
| **RAG** | Retrieval-Augmented Generation: find relevant chunks of text and include only those |
| **Prompt injection** | Malicious instructions hidden in input data |
| **Guardrails** | Checks and limits around the model |
| **Evals** | Repeatable tests that measure agent quality |
| **Human-in-the-loop** | A person approves or corrects at defined points |
| **Pydantic** | Python library that defines data shapes and validates data against them |

## Further reading
- Anthropic, *Building Effective Agents*: workflows vs agents and the patterns in §3. https://www.anthropic.com/research/building-effective-agents
- Google Gemini API docs: structured output and function calling (check the current docs in Google AI Studio).
- Pydantic docs: https://docs.pydantic.dev
