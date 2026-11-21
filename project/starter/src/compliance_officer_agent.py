# Compliance Officer Agent - ReACT Implementation  
# TODO: Implement Compliance Officer Agent using ReACT prompting

"""
Compliance Officer Agent Module

This agent generates regulatory-compliant SAR narratives using ReACT prompting.
It takes risk analysis results and creates structured documentation for 
FinCEN submission.

YOUR TASKS:
- Study ReACT (Reasoning + Action) prompting methodology
- Design system prompt with Reasoning/Action framework
- Implement narrative generation with word limits
- Validate regulatory compliance requirements
- Create proper audit logging and error handling
"""

import json
import re
import openai
from datetime import datetime
from typing import Dict, Any, List
from dotenv import load_dotenv

try:
    from foundation_sar import (
        ComplianceOfficerOutput,
        ExplainabilityLogger,
        CaseData,
        RiskAnalystOutput
    )
except ImportError:  # imported as part of the `src` package (e.g. by pytest)
    from .foundation_sar import (
        ComplianceOfficerOutput,
        ExplainabilityLogger,
        CaseData,
        RiskAnalystOutput
    )

# Load environment variables
load_dotenv()

class ComplianceOfficerAgent:
    """
    Compliance Officer agent using ReACT prompting framework.
    
    TODO: Implement agent that:
    - Uses Reasoning + Action structured prompting
    - Generates regulatory-compliant SAR narratives
    - Enforces word limits and terminology
    - Includes regulatory citations
    - Validates narrative completeness
    """
    
    def __init__(self, openai_client, explainability_logger, model="gpt-4"):
        """Initialize the Compliance Officer Agent
        
        Args:
            openai_client: OpenAI client instance
            explainability_logger: Logger for audit trails
            model: OpenAI model to use
        """
        self.client = openai_client
        self.logger = explainability_logger
        self.model = model
        self.system_prompt = """You are a senior BSA/AML Compliance Officer with 15 years of
experience writing Suspicious Activity Report (SAR) narratives for FinCEN submission.
You write precise, factual, regulator-ready narratives and rely only on the evidence
provided by the case data and the Risk Analyst's findings.

Work using the ReACT (Reasoning + Action) framework:

**REASONING PHASE** (think before you write):
1. Review the Risk Analyst's classification, confidence, risk level, and key indicators.
2. Assess the regulatory requirements: what must a SAR narrative contain for this
   type of activity?
3. Identify the key compliance elements: customer identification, suspicious activity
   description, transaction amounts and dates, and why the activity is suspicious.
4. Plan the narrative structure: who, what, when, how much, and why it is suspicious.

**ACTION PHASE** (then act on your reasoning):
1. Draft a concise narrative of NO MORE THAN 120 words.
2. Include specific details: customer identifier, exact amounts, dates, and counts.
3. Describe the suspicious activity pattern and why it is inconsistent with the
   customer's profile or expected behavior.
4. Use formal regulatory language, including terms such as "suspicious activity",
   "regulatory threshold", "financial institution", "money laundering" and
   "Bank Secrecy Act" where they apply.
5. Verify the narrative against the checklist below before responding.

Narrative requirements:
- Maximum 120 words. Count them.
- Objective and factual: no speculation, accusations, or legal conclusions.
- Never invent facts, amounts, dates, or names that are not in the provided data.
- Must contain: customer identification, description of suspicious activity,
  transaction amounts and dates, and the reason the activity is suspicious.

Regulatory citations: choose the relevant ones from
"31 CFR 1020.320 (BSA)", "12 CFR 21.11 (SAR Filing)", "FinCEN SAR Instructions".

Respond with ONLY a JSON object, no other text, in this format:
{
    "narrative": "<SAR narrative, max 120 words>",
    "narrative_reasoning": "<concise summary of your reasoning and action steps, max 500 characters>",
    "regulatory_citations": ["<citation>", "..."],
    "completeness_check": <true if the narrative satisfies every requirement above, otherwise false>
}

If the provided data is insufficient to cover a required element, do not fabricate it:
state what is known and set "completeness_check" to false."""

    def generate_compliance_narrative(self, case_data, risk_analysis) -> 'ComplianceOfficerOutput':
        """
        Generate regulatory-compliant SAR narrative using ReACT framework.
        
        TODO: Implement narrative generation that:
        - Creates ReACT-structured user prompt
        - Includes risk analysis findings
        - Makes OpenAI API call with constraints
        - Validates narrative word count
        - Parses and validates JSON response
        - Logs operations for audit
        """
        start_time = datetime.now()
        failure_reason = "Narrative generation failed"
        user_prompt = ""
        data = {}
        try:
            txn_lines = self._format_transactions_for_compliance(case_data.transactions)
            user_prompt = "\n".join([
                "Case Facts:",
                f"- Case ID: {case_data.case_id}",
                f"- Customer: {case_data.customer.name} (Customer ID: {case_data.customer.customer_id})",
                "Transactions:",
                txn_lines,
                "",
                self._format_risk_analysis_for_prompt(risk_analysis),
                "",
                "Complete the REASONING phase, then the ACTION phase, and respond with the JSON object only.",
            ])
            llm_response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            response_content = llm_response.choices[0].message.content
            try:
                json_from_response = self._extract_json_from_response(response_content)
                data = json.loads(json_from_response)
            except ValueError as parse_error:  # includes json.JSONDecodeError
                failure_reason = "JSON parsing failed"
                raise ValueError(f"Failed to parse Compliance Officer JSON output: {parse_error}") from parse_error

            validation = self._validate_narrative_compliance(data.get("narrative", ""))
            if not validation["within_word_limit"]:
                failure_reason = "Narrative exceeds word limit"
                raise ValueError(
                    f"Narrative is {validation['word_count']} words; limit is {validation['max_words']}."
                )

            result = ComplianceOfficerOutput(**data)
            self.logger.log_agent_action(  # log success for audit
                agent_type="ComplianceOfficer",
                action="generate_compliance_narrative",
                case_id=case_data.case_id,
                input_data=user_prompt,
                output_data=data,
                reasoning=result.narrative_reasoning,
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                success=True,
                error_message=None
            )
            return result
        except Exception as e:
            self.logger.log_agent_action(  # log failure for audit
                agent_type="ComplianceOfficer",
                action="generate_compliance_narrative",
                case_id=case_data.case_id,
                input_data=user_prompt,
                output_data=data or {},
                reasoning=failure_reason,
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                success=False,
                error_message=str(e)
            )
            raise

    def _extract_json_from_response(self, response_content: str) -> str:
        if response_content is None or response_content.strip() == "": #if there's nothing there, show error
            raise ValueError("No JSON content found: LLM response is empty.")
        if "```json" in response_content: #if there's ('''json), return inside the fence
            start = response_content.find("```json") + len("```json")
            end = response_content.find("```", start)
            json_str = response_content[start:end].strip()
        else: #it must be plain text, so find what's inside {}
            start = response_content.find("{")
            end = response_content.rfind("}")
            if start == -1 or end == -1: #unless there's no JSON at all, then raise error
                raise ValueError("No JSON content found in LLM response.")
            json_str = response_content[start:end + 1]
        return json_str 

    def _format_transactions_for_compliance(self, transactions) -> str:
        """Format transactions for the compliance prompt, one line per transaction"""
        lines = []
        for i, txn in enumerate(transactions, 1):
            line = f"{i}. {txn.transaction_date}: ${txn.amount:,.2f} {txn.transaction_type}"
            if txn.location:
                line += f" at {txn.location}"
            if txn.method:
                line += f" via {txn.method}"
            if txn.description:
                line += f" - {txn.description}"
            lines.append(line)
        return "\n".join(lines)

    def _format_risk_analysis_for_prompt(self, risk_analysis) -> str:
        indicators = "\n".join(f"  - {indicator}" for indicator in risk_analysis.key_indicators) #turning list of indicators into a block of text
        lines = [
            "Risk Analyst Findings:",
            f"- Classification: {risk_analysis.classification}",
            f"- Confidence Score: {risk_analysis.confidence_score}",
            f"- Risk Level: {risk_analysis.risk_level}",
            "- Key Suspicious Indicators:",
            indicators,
            f"- Analyst Reasoning: {risk_analysis.reasoning}",
        ]
        return "\n".join(lines)

    def _validate_narrative_compliance(self, narrative: str) -> Dict[str, Any]:
        """Validate narrative meets regulatory requirements
        
        TODO: Implement validation that checks:
        - Word count (≤120 words)
        - Required elements present
        - Appropriate terminology
        - Regulatory completeness
        """
        max_words = get_regulatory_requirements()["word_limit"]
        word_count = len((narrative or "").split())
        text = (narrative or "").lower()

        # Heuristic keyword/pattern checks for each required element
        elements_present = {
            "customer_identification": any(k in text for k in ("customer", "account holder", "subject", "account")),
            "suspicious_activity_description": any(k in text for k in ("suspicious", "structuring", "transactions", "deposits")),
            "transaction_amounts": bool(re.search(r"\$\s?\d", text)),
            "transaction_dates": bool(re.search(
                r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|"
                r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2}",
                text)),
            "why_suspicious": any(k in text for k in ("inconsistent", "indicat", "pattern", "threshold", "avoid", "unusual")),
        }
        missing = [name for name, present in elements_present.items() if not present]

        # Terminology: at least one required regulatory term must appear
        terms_found = [t for t in get_regulatory_requirements()["terminology"] if t.lower() in text]
        terminology_ok = len(terms_found) >= 1

        within_word_limit = validate_word_count(narrative or "", max_words)
        has_required_elements = not missing

        return {
            "word_count": word_count,
            "max_words": max_words,
            "within_word_limit": within_word_limit,
            "elements_present": elements_present,
            "missing_elements": missing,
            "has_required_elements": has_required_elements,
            "terms_found": terms_found,
            "terminology_ok": terminology_ok,
            "regulatory_complete": within_word_limit and has_required_elements and terminology_ok,
        }

# ===== REACT PROMPTING HELPERS =====

def create_react_framework():
    """Helper function showing ReACT structure
    
    TODO: Study this example and adapt for compliance narratives:
    
    **REASONING Phase:**
    1. Review the risk analyst's findings
    2. Assess regulatory narrative requirements
    3. Identify key compliance elements
    4. Consider narrative structure
    
    **ACTION Phase:**
    1. Draft concise narrative (≤120 words)
    2. Include specific details and amounts
    3. Reference suspicious activity pattern
    4. Ensure regulatory language
    """
    return {
        "reasoning_phase": [
            "Review risk analysis findings",
            "Assess regulatory requirements", 
            "Identify compliance elements",
            "Plan narrative structure"
        ],
        "action_phase": [
            "Draft concise narrative",
            "Include specific details",
            "Reference activity patterns",
            "Use regulatory language"
        ]
    }

def get_regulatory_requirements():
    """Key regulatory requirements for SAR narratives
    
    TODO: Use these requirements in your prompts:
    """
    return {
        "word_limit": 120,
        "required_elements": [
            "Customer identification",
            "Suspicious activity description", 
            "Transaction amounts and dates",
            "Why activity is suspicious"
        ],
        "terminology": [
            "Suspicious activity",
            "Regulatory threshold",
            "Financial institution",
            "Money laundering",
            "Bank Secrecy Act"
        ],
        "citations": [
            "31 CFR 1020.320 (BSA)",
            "12 CFR 21.11 (SAR Filing)",
            "FinCEN SAR Instructions"
        ]
    }

# ===== TESTING UTILITIES =====

def test_narrative_generation():
    """Test the agent with sample risk analysis
    
    TODO: Use this function to test your implementation:
    - Create sample risk analysis results
    - Initialize compliance agent
    - Generate narrative
    - Validate compliance requirements
    """
    print("🧪 Testing Compliance Officer Agent")
    print("TODO: Implement test case")

def validate_word_count(text: str, max_words: int = 120) -> bool:
    """Helper to validate word count
    
    TODO: Use this utility in your validation:
    """
    word_count = len(text.split())
    return word_count <= max_words

if __name__ == "__main__":
    print("✅ Compliance Officer Agent Module")
    print("ReACT prompting for regulatory narrative generation")
    print("\n📋 TODO Items:")
    print("• Design ReACT system prompt")
    print("• Implement generate_compliance_narrative method")
    print("• Add narrative validation (word count, terminology)")
    print("• Create regulatory citation system")
    print("• Test with sample risk analysis results")
    print("\n💡 Key Concepts:")
    print("• ReACT: Reasoning + Action structured prompting")
    print("• Regulatory Compliance: BSA/AML requirements")
    print("• Narrative Constraints: Word limits and terminology")
    print("• Audit Logging: Complete decision documentation")
