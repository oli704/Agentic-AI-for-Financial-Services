# Risk Analyst Agent - Chain-of-Thought Implementation
"""
Risk Analyst Agent Module

This agent performs suspicious activity classification using Chain-of-Thought reasoning.
It analyzes customer profiles, account behavior, and transaction patterns to identify
potential financial crimes.

YOUR TASKS:
- Study Chain-of-Thought prompting methodology
- Design system prompt with structured reasoning framework
- Implement case analysis with proper error handling
- Parse and validate structured JSON responses
- Create comprehensive audit logging
"""

import json
import openai
from datetime import datetime
from typing import Dict, Any, List
from dotenv import load_dotenv
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

    TODO: Implement agent that:
    - Uses systematic Chain-of-Thought prompting
    - Classifies suspicious activity patterns
    - Returns structured JSON output
    - Handles errors gracefully
    - Logs all operations for audit
    """

    def __init__(self, openai_client, explainability_logger, model="gpt-4"):
        """Initialize the Risk Analyst Agent
        Args:
            openai_client: OpenAI client instance
            explainability_logger: Logger for audit trails
            model: OpenAI model to use
        """
        self.client = openai_client
        self.explainability_logger = explainability_logger
        self.model = model

        # Chain-of-Thought system prompt
        self.system_prompt = """You are a senior financial crimes analyst with 15 years of
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
and number of indicators.
5. **Classification Decision**: Choose the single best-fitting category.

Classification must be exactly one of:
Structuring, Sanctions, Fraud, Money_Laundering, Other

Risk level must be exactly one of: Low, Medium, High, Critical

Respond with ONLY a JSON object, no other text, in this format:
{
    "classification": "<one of the categories above>",
    "confidence_score": <float between 0.0 and 1.0>,
    "reasoning": "<concise summary of your step-by-step analysis, max 500 characters>",
    "key_indicators": ["<specific suspicious indicator>", "..."],
    "risk_level": "<Low | Medium | High | Critical>"
}

Base conclusions only on the data provided. If the evidence is weak, use "Other" with
a low confidence score and risk level rather than overstating the risk."""

    def analyze_case(self, case_data) -> 'RiskAnalystOutput':  # Use quotes for forward reference
        """
        Perform risk analysis on a case using Chain-of-Thought reasoning.
        TODO: Implement analysis that:
        - Creates structured user prompt with case details
        - Makes OpenAI API call with system prompt
        - Parses and validates JSON response
        - Handles errors and logs operations
        - Returns validated RiskAnalystOutput
        """
        start_time = datetime.now()
        user_prompt = None
        data = None
        try:
            system_prompt = self.system_prompt
            user_prompt = self._format_case_for_prompt(case_data)
            llm_response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                max_tokens=600
            )
            response_content = llm_response.choices[0].message.content
            json_from_response = self._extract_json_from_response(response_content)
            data = json.loads(json_from_response)
            result = RiskAnalystOutput(**data)
            self.explainability_logger.log_agent_action( #log success for audit
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
            self.explainability_logger.log_agent_action( #log failure for audit
                agent_type="RiskAnalyst",
                action="analyze_case",
                case_id=case_data.case_id,
                input_data=user_prompt,
                output_data=data or {},
                reasoning="Analysis failed",
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                success=False,
                error_message=str(e)
            )
            raise

    def _extract_json_from_response(self, response_content: str) -> str:
        """Extract JSON content from LLM response"""
        if response_content is None or response_content.strip() == "": #if there's nothing there, show error
            raise ValueError("LLM response is empty. No content to extract.")
        if "```json" in response_content: #if there's ('''json), return inside the fence
            start = response_content.find("```json") + len("```json")
            end = response_content.find("```", start)
            json_str = response_content[start:end].strip()
        else: #it must be plain text, so find what's inside {}
            start = response_content.find("{")
            end = response_content.rfind("}")
            if start == -1 or end == -1: #unless there's no JSON at all, then raise error
                raise ValueError("No JSON object found in LLM response.")
            json_str = response_content[start:end + 1]
        return json_str

    def _format_case_for_prompt(self, case_data) -> str:
        """Format case data for inclusion in the LLM prompt"""
        lines = []
        lines.append("Customer Profile:")
        lines.append(f"- Name: {case_data.customer.name}")
        lines.append(f"- Date of Birth: {case_data.customer.date_of_birth}")
        lines.append("Account Information:")
        for account in case_data.accounts:
            lines.append(f"- Account Number: {account.account_id}")
            lines.append(f"- Account Type: {account.account_type}")
            lines.append(f"- Status: {account.status}")
            lines.append(f"- Balance: ${account.current_balance:.2f}")
            lines.append(f"- Opening Date: {account.opening_date}")
            lines.append("")
        lines.append("Transaction Details:")
        for txn in case_data.transactions:
            lines.append(f"- {txn.transaction_date}: {txn.transaction_type} of ${txn.amount:.2f} to {txn.counterparty}")
        lines.append("Financial Summary Statistics:")
        lines.append(f"- Total Transactions: {len(case_data.transactions)}")
        lines.append(f"- Total Transaction Amount: ${sum(txn.amount for txn in case_data.transactions):.2f}")
        lines.append(f"- Average Transaction Amount: ${sum(txn.amount for txn in case_data.transactions)/len(case_data.transactions):.2f}")
        return "\n".join(lines)

 # ===== PROMPT ENGINEERING HELPERS =====

def create_chain_of_thought_framework():
    """Helper function showing Chain-of-Thought structure

    TODO: Study this example and adapt for financial crime analysis:

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

def get_classification_categories():
    """Standard SAR classification categories

    TODO: Use these categories in your prompts:
    """
    return {
        "Structuring": "Transactions designed to avoid reporting thresholds",
        "Sanctions": "Potential sanctions violations or prohibited parties",
        "Fraud": "Fraudulent transactions or identity-related crimes",
        "Money_Laundering": "Complex schemes to obscure illicit fund sources",
        "Other": "Suspicious patterns not fitting standard categories"
    }

# ===== TESTING UTILITIES =====

def test_agent_with_sample_case():
    """Test the agent with a sample case
    """
    print("🧪 Testing Risk Analyst Agent")
    print("TODO: Implement test case")

if __name__ == "__main__":
    print("🔍 Risk Analyst Agent Module")
    print("Chain-of-Thought reasoning for suspicious activity classification")
    print("\n📋 TODO Items:")
    print("• Design Chain-of-Thought system prompt")
    print("• Implement analyze_case method")
    print("• Add JSON parsing and validation")
    print("• Create comprehensive error handling")
    print("• Test with sample cases")
    print("\n💡 Key Concepts:")
    print("• Chain-of-Thought: Step-by-step reasoning")
    print("• Structured Output: Validated JSON responses")
    print("• Financial Crime Detection: Pattern recognition")
    print("• Audit Logging: Complete decision trails")
