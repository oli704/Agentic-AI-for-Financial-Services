# Risk Analyst Agent - Chain-of-Thought Implementation
"""
Risk Analyst Agent Module

This agent performs suspicious activity classification using Chain-of-Thought reasoning.
It analyzes customer profiles, account behavior, and transaction patterns to identify
potential financial crimes.

Design notes:
- A 5-step Chain-of-Thought system prompt drives the analysis and calibrates confidence.
- LLM output is parsed from JSON and validated against RiskAnalystOutput; one retry is
  made if schema validation fails.
- Every call, successful or failed, is written to the audit log.
"""

import json
import openai
from datetime import datetime
from typing import Any, Dict, List
from dotenv import load_dotenv
from pydantic import ValidationError
try:
    from foundation_sar import (
        RiskAnalystOutput,
        ExplainabilityLogger,
        CaseData
    )
except ImportError:  # imported as part of the `src` package (e.g. by pytest)
    from .foundation_sar import (
        RiskAnalystOutput,
        ExplainabilityLogger,
        CaseData
    )

# Load environment variables
load_dotenv()


class RiskAnalystAgent:
    """
    Risk Analyst agent using Chain-of-Thought reasoning.

    The agent:
    - Uses systematic Chain-of-Thought prompting
    - Classifies suspicious activity patterns
    - Returns structured, schema-validated output
    - Handles errors gracefully
    - Logs all operations for audit
    """

    def __init__(self, openai_client: openai.OpenAI, explainability_logger: ExplainabilityLogger,
                 model: str = "gpt-4o") -> None:
        """Initialize the Risk Analyst Agent
        Args:
            openai_client: OpenAI client instance
            explainability_logger: Logger for audit trails
            model: OpenAI model to use
        """
        self.client = openai_client
        self.logger = explainability_logger
        self.model = model
        self.system_prompt = """You are a senior Financial Crime Risk Analyst with 15 years of
experience in AML/BSA compliance, transaction monitoring, and SAR investigations.
You review cases objectively and rely only on the evidence provided.

Analyze each case by thinking step by step through this framework:

1. **Data Review**: Summarize the customer profile, account details, and transaction
   facts. Note totals, counts, dates, amounts, and counterparties.
2. **Pattern Recognition**: Identify unusual patterns, such as amounts just under
   reporting thresholds, rapid movement of funds, repeated transactions, activity
   inconsistent with the customer's profile, or high-risk jurisdictions.
3. **Regulatory Mapping**: Consider which regulations or typologies the patterns
   relate to (e.g. BSA/CTR thresholds, structuring, OFAC sanctions, fraud typologies).
4. **Risk Quantification**: Judge severity and your confidence based on the strength
and number of indicators. Calibrate confidence_score using this scale:
   - 0.90-1.00: Multiple independent indicators and a clear, textbook typology match,
     with no plausible innocent explanation in the data.
   - 0.70-0.89: A clear pattern with a good typology fit, but some ambiguity or a
     possible legitimate explanation.
   - 0.50-0.69: Some suspicious indicators, but the evidence is partial or mixed.
   - 0.30-0.49: Weak or isolated indicators; activity may well be legitimate.
   - Below 0.30: Little or no evidence of suspicious activity.
   Use the specific value the evidence supports (e.g. 0.62, 0.78, 0.93). Do not
   default to a round or habitual number.
5. **Classification Decision**: Choose the single best-fitting category.

Classification must be exactly one of:
Structuring, Sanctions, Fraud, Money_Laundering, Other

Risk level must be exactly one of: Low, Medium, High, Critical

Respond with ONLY a JSON object, no other text, in this format:
{
    "classification": "<one of the categories above>",
    "confidence_score": <float between 0.0 and 1.0>,
    "reasoning": "<concise summary of your step-by-step analysis, max 400 characters>",
    "key_indicators": ["<specific suspicious indicator>", "..."],
    "risk_level": "<Low | Medium | High | Critical>"
}

Base conclusions only on the data provided. If the evidence is weak, use "Other" with
a low confidence score and risk level rather than overstating the risk."""

    def analyze_case(self, case_data: CaseData) -> RiskAnalystOutput:
        """
        Perform risk analysis on a case using Chain-of-Thought reasoning.

        Builds the user prompt from the case, calls the model, parses and validates the
        JSON response (retrying once on schema failure) and logs the outcome.

        Args:
            case_data: The validated case to analyse

        Returns:
            The validated RiskAnalystOutput

        Raises:
            ValueError: If the response contains no parseable JSON
            pydantic.ValidationError: If the output still fails the schema after a retry
        """
        start_time = datetime.now()
        user_prompt = None
        data = None
        failure_reason = "Analysis failed"
        try:
            system_prompt = self.system_prompt
            user_prompt = self._format_case_for_prompt(case_data)
            max_attempts = 2  # retry once if the model's output fails schema validation
            for attempt in range(1, max_attempts + 1):
                llm_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,  # changed from 0.2 to match test_api_call_parameters
                    max_tokens=1000  # changed from 600 to match test_api_call_parameters
                )
                response_content = llm_response.choices[0].message.content
                try:
                    json_from_response = self._extract_json_from_response(response_content)
                    data = json.loads(json_from_response)
                except ValueError as parse_error:  # includes json.JSONDecodeError
                    failure_reason = "JSON parsing failed"
                    raise ValueError(f"Failed to parse Risk Analyst JSON output: {parse_error}") from parse_error
                try:
                    result = RiskAnalystOutput(**data)
                    break
                except ValidationError:
                    failure_reason = "Output validation failed"
                    if attempt == max_attempts:
                        raise
            self.logger.log_agent_action( #log success for audit
                agent_type="RiskAnalyst",
                action="analyze_case",
                case_id=case_data.case_id,
                input_data=user_prompt,
                output_data=data,
                reasoning=result.reasoning,
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                success=True,
                error_message=None
            )
            return result
        except Exception as e:
            self.logger.log_agent_action( #log failure for audit
                agent_type="RiskAnalyst",
                action="analyze_case",
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
        """Extract JSON content from LLM response"""
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

    def _format_accounts(self, accounts: List[Any]) -> str:
        """Format account data for inclusion in the LLM prompt"""
        lines = []
        for account in accounts:
            lines.append(f"- Account Number: {account.account_id}")
            lines.append(f"- Account Type: {account.account_type}")
            lines.append(f"- Status: {account.status}")
            lines.append(f"- Balance: ${account.current_balance:,.2f}")
            lines.append(f"- Opening Date: {account.opening_date}")
            lines.append("")
        return "\n".join(lines)

    def _format_transactions(self, transactions: List[Any]) -> str:
        """Format transaction data for inclusion in the LLM prompt"""
        lines = []
        for i, txn in enumerate(transactions, 1):
            line = f"{i}. {txn.transaction_date}: {txn.transaction_type} ${txn.amount:,.2f}"
            if txn.counterparty:
                line += f" to {txn.counterparty}"
            if txn.description:
                line += f" - {txn.description}"
            if txn.location:
                line += f" (Location: {txn.location})"
            lines.append(line)
        return "\n".join(lines)

    def _format_case_for_prompt(self, case_data: CaseData) -> str:
        """Format case data for inclusion in the LLM prompt"""
        transactions = case_data.transactions
        total = sum(txn.amount for txn in transactions)
        average = total / len(transactions) if transactions else 0.0
        lines = [
            "Customer Profile:",
            f"- Name: {case_data.customer.name}",
            f"- Date of Birth: {case_data.customer.date_of_birth}",
            "Account Information:",
            self._format_accounts(case_data.accounts),
            "Transaction Details:",
            self._format_transactions(transactions),
            "Financial Summary Statistics:",
            f"- Total Transactions: {len(transactions)}",
            f"- Total Transaction Amount: ${total:,.2f}",
            f"- Average Transaction Amount: ${average:,.2f}",
        ]
        return "\n".join(lines)

 # ===== PROMPT ENGINEERING HELPERS =====

def create_chain_of_thought_framework() -> Dict[str, str]:
    """Return the Chain-of-Thought structure used in the system prompt

    **Analysis Framework** (Think step-by-step):
    1. **Data Review**: What does the data tell us?
    2. **Pattern Recognition**: What patterns are suspicious?
    3. **Regulatory Mapping**: Which regulations apply?
    4. **Risk Quantification**: How severe is the risk?
    5. **Classification Decision**: What category fits best?
    """
    return {
        "step_1": "Data Review - Examine all available information",
        "step_2": "Pattern Recognition - Identify suspicious indicators",
        "step_3": "Regulatory Mapping - Connect to known typologies",
        "step_4": "Risk Quantification - Assess severity level",
        "step_5": "Classification Decision - Determine final category"
    }

def get_classification_categories() -> Dict[str, str]:
    """Return the standard SAR classification categories with short descriptions"""
    return {
        "Structuring": "Transactions designed to avoid reporting thresholds",
        "Sanctions": "Potential sanctions violations or prohibited parties",
        "Fraud": "Fraudulent transactions or identity-related crimes",
        "Money_Laundering": "Complex schemes to obscure illicit fund sources",
        "Other": "Suspicious patterns not fitting standard categories"
    }

# ===== TESTING UTILITIES =====

def test_agent_with_sample_case() -> None:
    """Offline smoke test: the framework helpers cover every classification category

    Makes no API calls. Full agent behaviour is covered by tests/test_risk_analyst.py.
    """
    print("🧪 Testing Risk Analyst Agent")
    categories = get_classification_categories()
    steps = create_chain_of_thought_framework()
    assert set(categories) == {"Structuring", "Sanctions", "Fraud", "Money_Laundering", "Other"}
    assert len(steps) == 5
    print(f"✅ {len(categories)} categories and {len(steps)} reasoning steps defined")

if __name__ == "__main__":
    print("🔍 Risk Analyst Agent Module")
    print("Chain-of-Thought reasoning for suspicious activity classification")
    print("\n📦 Components:")
    print("• RiskAnalystAgent.analyze_case: Chain-of-Thought analysis")
    print("• JSON parsing and schema validation with one retry")
    print("• Audit logging for every call")
    print("\n🧪 Run the tests: python -m pytest tests/test_risk_analyst.py")
    print("\n💡 Key Concepts:")
    print("• Chain-of-Thought: Step-by-step reasoning")
    print("• Structured Output: Validated JSON responses")
    print("• Financial Crime Detection: Pattern recognition")
    print("• Audit Logging: Complete decision trails")
