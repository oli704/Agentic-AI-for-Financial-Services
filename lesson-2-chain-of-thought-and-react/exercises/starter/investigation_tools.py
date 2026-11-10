"""
Financial Investigation Tools for ReACT Framework

This module provides pre-defined tools for financial compliance investigations
that can be used with the ReACT (Reasoning and Acting) framework.
"""

import json
import re
from datetime import datetime, timedelta


# Tool 1: Transaction History Lookup
def get_transaction_history(account_id, days=30):
    """Retrieve transaction history for an account (simulated data)"""

    if "high_risk" in account_id:
        # Structuring pattern: repeated cash deposits just under the $10K threshold
        transactions = [
            {"date": "2026-11-02", "type": "cash_deposit", "amount": 9800.00,  "description": "Cash deposit - Branch 12"},
            {"date": "2024-01-04", "type": "cash_deposit", "amount": 9500.00,  "description": "Cash deposit - Branch 7"},
            {"date": "2024-01-06", "type": "cash_deposit", "amount": 9900.00,  "description": "Cash deposit - Branch 12"},
            {"date": "2024-01-09", "type": "cash_deposit", "amount": 9700.00,  "description": "Cash deposit - Branch 3"},
            {"date": "2024-01-11", "type": "wire_out",     "amount": 38000.00, "description": "Wire transfer - overseas account"},
        ]

    elif "business" in account_id:
        # Large wire transfers, typical for business operations
        transactions = [
            {"date": "2024-01-03", "type": "wire_in",  "amount": 125000.00, "description": "Customer payment - Invoice #4471"},
            {"date": "2024-01-08", "type": "wire_out", "amount": 80000.00,  "description": "Supplier payment - Acme Manufacturing"},
            {"date": "2024-01-15", "type": "wire_in",  "amount": 95000.00,  "description": "Customer payment - Invoice #4452"},
            {"date": "2024-01-22", "type": "ach_out",  "amount": 45000.00,  "description": "Payroll"},
        ]

    else:
        # Normal personal account activity
        transactions = [
            {"date": "2024-01-01", "type": "ach_in", "amount": 3200.00, "description": "Payroll deposit"},
            {"date": "2024-01-05", "type": "debit",  "amount": 1450.00, "description": "Rent payment"},
            {"date": "2024-01-10", "type": "debit",  "amount": 54.20,   "description": "Grocery store"},
            {"date": "2024-01-14", "type": "debit",  "amount": 38.75,   "description": "Gas station"},
            {"date": "2024-01-15", "type": "ach_in", "amount": 3200.00, "description": "Payroll deposit"},
        ]

    return {
        "account_id": account_id,
        "period_days": days,
        "transaction_count": len(transactions),
        "transactions": transactions,
    }


# Tool 2: Customer Profile Lookup
def get_customer_profile(customer_id):
    """Retrieve customer profile and risk information (simulated data)"""
    
    # TODO: Create profiles dictionary with customer data
    # Include: name, occupation, income, account_age, risk_score, etc.
    profiles = {
        "CUST_001": {
            "customer_id": "CUST_001",
            "name": "John Smith",
            "account_id": "high_risk_account_001",
            "occupation": "Restaurant owner",
            "annual_income": 85000,
            "account_age_months": 4,
            "risk_score": 8.5,          # out of 10
            "kyc_status": "verified",
            "previous_sars": 1,
            "pep_status": False,
        },
        "CUST_002": {
            "customer_id": "CUST_002",
            "name": "Acme Manufacturing Ltd",
            "account_id": "business_account_002",
            "occupation": "Industrial manufacturing",
            "annual_income": 2500000,
            "account_age_months": 60,
            "risk_score": 3.0,
            "kyc_status": "verified",
            "previous_sars": 0,
            "pep_status": False,
        },
        "CUST_003": {
            "customer_id": "CUST_003",
            "name": "Sarah Johnson",
            "account_id": "personal_account_003",
            "occupation": "Teacher",
            "annual_income": 62000,
            "account_age_months": 96,
            "risk_score": 1.5,
            "kyc_status": "verified",
            "previous_sars": 0,
            "pep_status": False,
        },
    }
    
    return profiles.get(customer_id, {"error": "Customer not found"})


# Tool 3: Regulatory Threshold Check
def check_regulatory_thresholds(amount, type):
    """Check transaction against regulatory reporting thresholds"""
    


    # TODO: Define regulatory thresholds
    thresholds = {
        "CTR_threshold": 10000,  # Currency Transaction Report
        "SAR_threshold": 5000,   # Suspicious Activity Report
        "wire_threshold": 3000,  # Enhanced monitoring for wires
    }


    
    # TODO: Calculate compliance requirements
    results = {
        "amount": amount,
        "type": type,
        "CTR_flag": amount > thresholds["CTR_threshold"],
        "SAR_flag": amount > thresholds["SAR_threshold"],
        "enhanced_monitoring_flag": (amount > thresholds["wire_threshold"] and "wire" in type.lower()),
    }
    
    return results


# Tool Registry
INVESTIGATION_TOOLS = {
    "get_transaction_history": get_transaction_history,
    "get_customer_profile": get_customer_profile,
    "check_regulatory_thresholds": check_regulatory_thresholds
}


# Tool Execution Functions
def parse_tool_calls(text):
    """Parse JSON tool calls from LLM response"""
    # TODO: Create regex pattern to find JSON tool calls
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    
    # TODO: Find matches and parse JSON
    tool_calls = []
    for match in re.findall(json_pattern, text, re.DOTALL):
        try:
            call = json.loads(match)
            if "tool" in call:
                tool_calls.append(call)
        except json.JSONDecodeError:
            continue
    return tool_calls


def execute_tool(tool_name, parameters):
    """Execute a tool with given parameters"""
    # TODO: Check if tool exists and execute
    if tool_name not in INVESTIGATION_TOOLS:
        return {"error": f"Tool {tool_name} not found"}
    
    try:
        # TODO: Execute tool function
        return INVESTIGATION_TOOLS[tool_name](**parameters)
    except Exception as e:
        return {"error": f"Tool execution failed: {str(e)}"}


def process_tool_calls(llm_response):
    """Process all tool calls in LLM response and return results"""
    results = []
    for call in parse_tool_calls(llm_response):
        name, params = call["tool"], call.get("parameters", {})
        print(f"🔧 Executing {name}({params})")
        result = execute_tool(name, params)
        print(f"📊 Result: {json.dumps(result, indent=2, default=str)}")
        results.append({"tool": name, "parameters": params, "result": result})
    return results
    
    results = []
    return results
