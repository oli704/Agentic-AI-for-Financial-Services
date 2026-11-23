# System Design: AI-Assisted SAR (Suspicious Activity Report) Processing

A high-level design for a system that turns raw bank data into reviewed, audit-ready SAR filings using two LLM agents and a human approval gate.

Status legend: ✅ built in this repo · 🚧 Phase 4, in progress · 💡 proposed for production, not in the project scope

---

## 1. Problem Statement

Banks must file a SAR with FinCEN when they detect suspicious activity (structuring, fraud, sanctions, money laundering). Today analysts spend hours per case reading transactions and writing a narrative. Most flagged cases are false positives, so most of that effort is wasted.

**Goal:** cut analyst time per case while keeping a human accountable for every filing and every decision explainable to an examiner.

---

## 2. Requirements

### Functional
1. Ingest customer, account and transaction data and assemble a **case** per customer.
2. **Screen** customers and prioritize the highest-risk ones for analysis.
3. A **Risk Analyst agent** classifies the activity (Structuring / Sanctions / Fraud / Money_Laundering / Other), gives a confidence score, a risk level and key indicators.
4. A **human reviewer** approves or rejects each case before any narrative is written.
5. A **Compliance Officer agent** writes a regulatory narrative (≤120 words) with citations for approved cases.
6. Assemble a complete **SAR document** with metadata, subject info, narrative and a checksum.
7. Record an **audit trail** of every agent action and human decision.

### Non-functional
| Concern | Target |
|---|---|
| **Explainability** | Every output traces back to its inputs, prompt, model and reasoning. This is a regulatory requirement. |
| **Human oversight** | No SAR is produced without an explicit human decision. |
| **Cost** | LLM calls are the main cost. Spend the cheap stage on every case and the expensive stage only on approved ones. |
| **Correctness** | LLM output is never trusted raw. It is parsed and validated against a schema, with hard limits on narrative length. |
| **Auditability** | The audit log is append-only and survives agent failures, since failures must be logged too. |
| **Privacy** | PII (name, DOB, SSN last 4) is handled carefully and not logged beyond what the audit requires. |

### Out of scope (for the project)
Real-time transaction monitoring, e-filing to FinCEN's BSA E-Filing system, case-management UI, multi-bank tenancy.

---

## 3. Core Entities

| Entity | Fields (abridged) | Where |
|---|---|---|
| `Customer` | id, name, DOB, address, ssn_last_4, risk_rating | ✅ `CustomerData` |
| `Account` | id, customer_id, type, balance, status | ✅ `AccountData` |
| `Transaction` | id, account_id, date, type, amount, counterparty, method | ✅ `TransactionData` |
| `Case` | case_id, customer, accounts[], transactions[], data_sources | ✅ `CaseData` (rejects empty transaction lists and mismatched links) |
| `RiskAnalysis` | classification, confidence 0–1, reasoning ≤500 chars, key_indicators[], risk_level | ✅ `RiskAnalystOutput` |
| `ComplianceNarrative` | narrative, narrative_reasoning, regulatory_citations[], completeness_check | ✅ `ComplianceOfficerOutput` |
| `AuditEntry` | agent_type, action, case_id, input, output, reasoning, execution_time_ms, success, error | ✅ `ExplainabilityLogger` (JSONL) |
| `ReviewDecision` | case_id, reviewer, decision, rationale, timestamp | 🚧 Phase 4 |
| `SARDocument` | sar_id, filing metadata, subject, activity description, analysis, narrative, citations, checksum | 🚧 Phase 4 |

---

## 4. Interfaces

The project is notebook-driven, so the "API" is a set of Python interfaces. In production these would sit behind an internal service.

```python
# Ingestion
load_csv_data(data_dir)                                  -> (customers_df, accounts_df, transactions_df)
DataLoader.create_case_from_data(customer, accts, txns)  -> CaseData

# Stage 1
RiskAnalystAgent.analyze_case(case)                      -> RiskAnalystOutput

# Stage 2
ComplianceOfficerAgent.generate_compliance_narrative(case, risk) -> ComplianceOfficerOutput

# Phase 4
screen_high_risk_customers(customers, accounts, txns, top_n) -> [customer]
run_two_stage_sar_workflow(selected_customers)               -> (approved_sars, rejected_cases, audit_decisions)
create_sar_document(case, risk, narrative)                   -> SARDocument
```

A production REST surface might look like this (💡):

```
POST /cases/screen              run screening, create cases
GET  /cases?status=pending      review queue
GET  /cases/{id}                case + risk analysis + reasoning
POST /cases/{id}/decision       {decision: approve|reject, rationale}
GET  /sars/{id}                 final SAR document
GET  /audit?case_id=...         audit trail
```

---

## 5. High-Level Design

**Diagram:** [Google Slides](https://docs.google.com/presentation/d/14F1dllJ8hde7R1k6CPX3SGfVqCc1NzOCG5zD3OfmWQ0/edit) · [Whimsical board](https://whimsical.com/V3caHjjUCfW3y1iopnxw1f). The ASCII sketch below is a plain-text fallback.

```
 CSV / core banking data
          │
          ▼
 ┌─────────────────┐    ┌──────────────────────┐
 │  Data Loader    │───▶│  Customer Screening  │  rank by risk rating, volume,
 │  (build Cases)  │    │  (rules, no LLM)     │  frequency, recent activity
 └─────────────────┘    └──────────┬───────────┘
                                   │ top-N cases
                                   ▼
                        ┌──────────────────────┐
                        │ Stage 1: Risk Analyst│  Chain-of-Thought
                        │ (LLM, cheap)         │  → classification, confidence
                        └──────────┬───────────┘
                                   │ RiskAnalysis
                                   ▼
                        ┌──────────────────────┐
                        │   Human Review Gate  │  approve / reject + rationale
                        └───────┬──────┬───────┘
                       reject   │      │ approve
                  ┌─────────────┘      ▼
                  │          ┌──────────────────────┐
                  │          │ Stage 2: Compliance  │  ReACT (reason → act)
                  │          │ Officer (LLM)        │  → ≤120-word narrative + citations
                  │          └──────────┬───────────┘
                  │                     ▼
                  │          ┌──────────────────────┐
                  │          │  SAR Document Builder│  metadata + checksum
                  │          └──────────┬───────────┘
                  ▼                     ▼
        ┌────────────────────────────────────────────┐
        │  Explainability Logger (append-only JSONL) │◀── every step above writes here
        └────────────────────────────────────────────┘
                                   │
                                   ▼
                       Metrics / efficiency analysis
```

### Walkthrough
1. **Ingest.** `DataLoader` joins customer → accounts → transactions into a validated `CaseData`. Pydantic schemas reject malformed data at the boundary.
2. **Screen.** Deterministic rules rank customers so the LLM only sees the highest-risk cases. This is the first cost control.
3. **Stage 1, Risk Analyst.** A Chain-of-Thought prompt walks a fixed set of analysis steps and returns structured JSON.
4. **Human gate.** The reviewer sees the classification, confidence, indicators and reasoning, then approves or rejects.
5. **Stage 2, Compliance Officer.** Runs only for approved cases. A ReACT prompt separates a reasoning phase from an action phase, so the plan is visible before the text is written.
6. **Assemble.** Build the SAR document and checksum it so later tampering is detectable.
7. **Log and measure.** Every step writes an `AuditEntry`. Metrics are computed from the log.

### Key design decisions
| Decision | Why |
|---|---|
| **Two stages, not one big prompt** | Rejected cases never pay for narrative generation, and each prompt stays focused and testable. |
| **Human gate between the stages** | Meets the regulatory expectation of human accountability, and filters false positives before the costly step. |
| **Different prompting per stage** | CoT suits classification (analysis). ReACT suits drafting under constraints (plan, then write). |
| **Pydantic on both ends** | Validates input data and LLM output, and fails loudly instead of passing bad data downstream. |
| **Rules before LLMs for screening** | Cheap, deterministic and explainable. |

---

## 6. Deep Dives

### 6.1 Making LLM output reliable
- Prompts demand JSON only. `_extract_json_from_response` strips code fences and stray prose before `json.loads`.
- Output is validated against `RiskAnalystOutput` or `ComplianceOfficerOutput`: enum classifications, confidence in [0, 1], length caps.
- The narrative word limit (≤120) is checked in code after generation. It is never trusted to the prompt.
- Low temperature (0.2) keeps outputs consistent across runs.
- **Failure handling:** parse, validation and API errors are logged with a reason and re-raised. The workflow decides whether to skip or retry the case. 💡 In production, add bounded retries with a repair prompt, then route to a human queue.

### 6.2 Explainability and audit
- `ExplainabilityLogger` writes one JSON object per action to a JSONL file. This is append-only and easy to ship to a log store.
- Failures are logged as well as successes, because an examiner asks about both.
- The SAR checksum plus the audit log lets you reconstruct who or what decided what, and show the document was not changed afterwards.
- 💡 Production: write to WORM storage (S3 Object Lock) or a ledger table, and add a hash chain across entries.

### 6.3 Cost optimization
```
cost ≈ N_screened × cost(stage 1) + N_approved × cost(stage 2)
```
Compared with a single-stage design (`N_screened × (stage 1 + stage 2)`), savings grow as the rejection rate rises. Screening cuts `N_screened` before any LLM call. Phase 4's metrics step should quantify this: approval rate, calls avoided, and time per case.

### 6.4 Human-in-the-loop
- The notebook version is a synchronous prompt. In production the gate is an **asynchronous review queue**: the workflow persists state at "awaiting review" and resumes when a decision arrives.
- Capture the **rationale** for every decision, especially overrides of high-confidence AI output, since that feeds quality review and model evaluation.
- Guard against automation bias: show the evidence alongside the AI's conclusion, and sample-audit approved cases.

### 6.5 Scaling (💡, beyond the project)
| Pressure | Approach |
|---|---|
| Many cases | Queue (SQS/Kafka) plus stateless workers. Cases are independent, so they parallelize cleanly. |
| LLM rate limits | Per-worker concurrency caps, backoff with jitter, a shared token budget. |
| Large transaction histories | Summarize or aggregate before prompting (windowed totals, outliers, velocity) instead of sending raw rows. |
| Data freshness | Trigger screening from monitoring alerts instead of batch CSVs. |
| Storage | Cases and decisions in Postgres. Audit log in an append-only store. SAR PDFs in object storage. |

### 6.6 Security and privacy
- Minimize PII sent to the LLM. Send what the analysis needs, and consider tokenizing identifiers.
- Use a vendor and contract that exclude training on inputs, with zero-retention where available.
- Role-based access: analysts see cases, reviewers decide, auditors read the logs.
- SAR confidentiality is a legal requirement (tipping-off prohibition), so access must be tightly logged.

### 6.7 Evaluation and monitoring
- Offline: the pre-built test scenarios (`test_scenarios.py`) and unit suites check structure, limits and edge cases.
- Online: track agreement rate between the Risk Analyst and the human reviewer, narrative rejection rate and schema-failure rate.
- Drift: a falling agreement rate or a changing mix of classifications is the signal to revisit prompts or the model.

---

## 7. What's Built vs. What's Next

| Component | Status |
|---|---|
| Schemas, `DataLoader`, `ExplainabilityLogger` | ✅ |
| Risk Analyst agent (CoT) plus tests | ✅ |
| Compliance Officer agent (ReACT) plus tests | ✅ |
| Setup and data loading in notebook 3 | ✅ |
| Customer screening | 🚧 |
| Two-stage workflow and human gate | 🚧 |
| SAR document generation | 🚧 |
| Efficiency metrics and end-to-end demo | 🚧 |
| Async review queue, retries, WORM audit store, REST API | 💡 |
