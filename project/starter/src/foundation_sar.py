# Foundation SAR - Core Data Schemas and Utilities
"""
This module contains the foundational components for SAR processing:

1. Pydantic Data Schemas:
   - CustomerData: Customer profile information
   - AccountData: Account details and balances  
   - TransactionData: Individual transaction records
   - CaseData: Unified case combining all data sources
   - RiskAnalystOutput: Risk analysis results
   - ComplianceOfficerOutput: Compliance narrative results

2. Utility Classes:
   - ExplainabilityLogger: Audit trail logging
   - DataLoader: Combines fragmented data into case objects

YOUR TASKS:
- Study the data files in data/ folder
- Design Pydantic schemas that match the CSV structure
- Implement validation rules for financial data
- Create a DataLoader that builds unified case objects
- Add proper error handling and logging
"""

import json
import pandas as pd
from datetime import datetime, timezone, date
from typing import Dict, List, Optional, Any, Literal, Annotated
from pydantic import BaseModel, Field, field_validator, AfterValidator, StringConstraints, model_validator
import uuid
import os

# ===== TODO: IMPLEMENT PYDANTIC SCHEMAS =====

def _not_in_future(v: date) -> date:
    """Validator to ensure date is not in the future"""
    if v > date.today():
        raise ValueError("Date cannot be in the future")
    return v

PastOrTodayDate = Annotated[date, AfterValidator(_not_in_future)]

def _max_words(limit: int):
    def check(v: str) -> str:
        if len(v.split()) > limit:
            raise ValueError(f"Must be {limit} words or fewer")
        return v
    return AfterValidator(check)

Narrative = Annotated[str, _max_words(200)]

class CustomerData(BaseModel):
    customer_id: str = Field(..., description="Unique identifier for the customer")
    name: str = Field(..., description="Customer name")
    date_of_birth: PastOrTodayDate = Field(..., description="Customer's date of birth YYYY-MM-DD")
    ssn_last_4: Annotated[str, StringConstraints(pattern=r"^\d{4}$")] = Field(
        repr=False,  # keeps it out of repr/logs
        description="Last 4 digits of SSN")
    address: str = Field(..., description="Customer's address")
    phone: Optional[Annotated[str, StringConstraints(pattern=r"^\+?[\d\s().-]{7,20}(?:\s*(?:x|ext\.?)\s*\d{1,6})?$")]] = Field(None,
        description="Customer's phone number; digits with optional spaces, dots, dashes, brackets, leading + and extension (e.g. 555-123-4567 x89)")
    customer_since: PastOrTodayDate = Field(..., description="Date when the customer joined YYYY-MM-DD")
    risk_rating: Literal["Low", "Medium", "High"] = Field(..., description="Customer's risk rating (Low, Medium, High)")
    occupation: Optional[str] = Field(None, description="Customer's occupation")
    annual_income: Optional[float] = Field(None, ge=0, description="Customer's annual income in USD")
        
class AccountData(BaseModel):
    account_id: str = Field(..., description="Unique identifier for the account")
    customer_id: str = Field(...,json_schema_extra={"references": "CustomerData.customer_id"} ,description="Customer ID associated with the account. Must match CustomerData.customer_id")
    account_type: Literal["Checking", "Savings", "Money_Market", "Business_Checking"] = Field(..., description="Type of account (Checking, Savings, Money_Market, Business_Checking)")   
    opening_date: PastOrTodayDate = Field(..., description="Date when the account was opened YYYY-MM-DD")
    current_balance: float = Field(..., description="Current balance of the account (can be negative for overdrafts)")
    average_monthly_balance: float = Field(..., description="Average monthly balance of the account")
    status: Literal["Active", "Closed", "Suspended"] = Field(..., description="Status of the account (Active, Closed, Suspended)")

class TransactionData(BaseModel):
    transaction_id: str = Field(..., description="Unique identifier for the transaction")
    account_id: str = Field(..., description="Account ID associated with the transaction. Must match AccountData.account_id")
    transaction_date: PastOrTodayDate = Field(..., description="Date of the transaction YYYY-MM-DD")
    transaction_type: Literal[
    "Online_Transfer", "ACH_Debit", "ACH_Credit", "ATM_Withdrawal",
    "Wire_Transfer", "Direct_Deposit", "Check_Deposit", "Debit_Purchase",
    "Cash_Deposit", "Wire_Transfer_Debit", "Cash_Withdrawal", "Wire_Transfer_Credit","Deposit"] = Field(..., description="Type of transaction, e.g. Online_Transfer, ACH_Debit, Wire_Transfer, Cash_Deposit")
    amount: float = Field(..., description="Amount of the transaction")
    description: str = Field(..., description="Description of the transaction, e.g. 'Cash deposit at branch'")
    method: Literal["Electronic","ATM","Online","Mobile","Branch","Cash","Wire","ACH"] = Field(..., description="Method of the transaction")
    counterparty: Optional[str] = Field(None, description="Counterparty involved in the transaction, if applicable")
    location: Optional[str] = Field(None, description="Location or branch where the transaction occurred")

class CaseData(BaseModel):
    case_id: str = Field(..., description="Unique case identifier (generate with uuid)")
    customer: CustomerData = Field(..., description="Customer information object")
    accounts: List[AccountData] = Field(..., description="List of customer's accounts")
    transactions: List[TransactionData] = Field(..., description="List of suspicious transactions")
    case_created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc)) #better than string because it can be validated and sorted
    data_sources: Dict[str, str] = Field(..., description="Source tracking with keys like 'customer_source', 'account_source', 'transaction_source'")

    #validations

    @field_validator('transactions')
    @classmethod
    def transactions_not_empty(cls, v: List[TransactionData]) -> List[TransactionData]:
        if not v:
            raise ValueError("Transactions list cannot be empty")
        return v

    @model_validator(mode="after")
    def check_case_links(self):
        if any(a.customer_id != self.customer.customer_id for a in self.accounts):
            raise ValueError("All accounts must belong to the case's customer")
        account_ids = {a.account_id for a in self.accounts}
        if any(t.account_id not in account_ids for t in self.transactions):
            raise ValueError("All transactions must belong to accounts in the case")
        return self

class RiskAnalystOutput(BaseModel):
    classification: Literal['Structuring', 'Sanctions', 'Fraud', 'Money_Laundering', 'Other'] = Field(..., description="Risk classification")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    reasoning: str = Field(..., max_length=500, description="Step-by-step analysis reasoning (max 500 chars)")
    key_indicators: List[str] = Field(..., description="List of suspicious indicators found")
    risk_level: Literal['Low', 'Medium', 'High', 'Critical'] = Field(..., description="Risk assessment level")

class ComplianceOfficerOutput(BaseModel):
    narrative: Narrative = Field(..., max_length=1000, description="Regulatory narrative text (max 1000 chars for ≤200 words)")
    narrative_reasoning: str = Field(..., max_length=500, description="Reasoning for narrative construction (max 500 chars)")
    regulatory_citations: List[str] = Field(..., description="List of relevant regulations like: '31 CFR 1020.320 (BSA)', '12 CFR 21.11 (SAR Filing)', 'FinCEN SAR Instructions'")
    completeness_check: bool = Field(..., description="Whether narrative meets all requirements")

# ===== TODO: IMPLEMENT AUDIT LOGGING =====

class ExplainabilityLogger:
    """Simple audit logging for compliance trails

    ATTRIBUTES:
    - log_file: str = Path to JSONL log file (default: "sar_audit.jsonl")
    - entries: List = In-memory storage of log entries

    METHODS:
    - log_agent_action(): Logs agent actions with structured data
    
    LOG ENTRY STRUCTURE (use this exact format):
    {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'case_id': case_id,
        'agent_type': agent_type,  # "DataLoader", "RiskAnalyst", "ComplianceOfficer"
        'action': action,          # "create_case", "analyze_case", "generate_narrative"
        'input_summary': str(input_data),
        'output_summary': str(output_data),
        'reasoning': reasoning,
        'execution_time_ms': execution_time_ms,
        'success': success,        # True/False
        'error_message': error_message  # None if success=True
    }
    
    HINT: Write each entry as JSON + newline to create JSONL format
    HINT: Use 'a' mode to append to log file
    HINT: Store entries in self.entries list AND write to file
    """
    
    def __init__(self, log_file: str = "sar_audit.jsonl"):
        # TODO: Initialize with log_file path and empty entries list
        self.log_file = log_file
        self.entries = []
    
    def log_agent_action(self, agent_type: str, action: str, case_id: str, 
                        input_data: Dict, output_data: Dict, reasoning: str, 
                        execution_time_ms: float, success: bool = True, 
                        error_message: Optional[str] = None):
        """Log an agent action with essential context
        
        IMPLEMENTATION STEPS:
        1. Create entry dictionary with all fields (see structure above)
        2. Add entry to self.entries list
        3. Write entry to log file as JSON line
        
        HINT: Use json.dumps(entry) + '\n' for JSONL format
        HINT: Use datetime.now(timezone.utc).isoformat() for timestamp
        HINT: Convert input_data and output_data to strings with str()
        """
        entry ={'timestamp': datetime.now(timezone.utc).isoformat(),
                'case_id': case_id,
                'agent_type': agent_type,  # "DataLoader", "RiskAnalyst", "ComplianceOfficer"
                'action': action,          # "create_case", "analyze_case", "generate_narrative"
                'input_summary': str(input_data),
                'output_summary': str(output_data),
                'reasoning': reasoning,
                'execution_time_ms': execution_time_ms,
                'success': success,        # True/False
                'error_message': error_message  # None if success=True
            }
        self.entries.append(entry)
        with open(self.log_file,'a') as f:
            f.write(json.dumps(entry)+'\n')

class DataLoader:
    """Simple loader that creates case objects from CSV data
    
    ATTRIBUTES:
    - logger: ExplainabilityLogger = For audit logging
    
    HELPFUL METHODS:
    - create_case_from_data(): Creates CaseData from input dictionaries
    
    IMPLEMENTATION PATTERN:
    1. Start timing with start_time = datetime.now()
    2. Generate case_id with str(uuid.uuid4())
    3. Create CustomerData object from customer_data dict
    4. Filter accounts where acc['customer_id'] == customer.customer_id
    5. Get account_ids set from filtered accounts
    6. Filter transactions where txn['account_id'] in account_ids
    7. Create CaseData object with all components
    8. Calculate execution_time_ms
    9. Log success/failure with self.logger.log_agent_action()
    10. Return CaseData object (or raise exception on failure)
    """
    
    def __init__(self, explainability_logger: ExplainabilityLogger):
        self.logger = explainability_logger
    
    def create_case_from_data(self, 
                            customer_data: Dict,
                            account_data: List[Dict],
                            transaction_data: List[Dict]) -> CaseData:
        start_time = datetime.now(timezone.utc)
        case_id = str(uuid.uuid4())
        try:
            customer = CustomerData(**customer_data)
            accounts = [AccountData(**acc) for acc in account_data if acc['customer_id'] == customer.customer_id]
            account_ids = {acc.account_id for acc in accounts}
            transactions = [TransactionData(**txn) for txn in transaction_data if txn['account_id'] in account_ids]
            case = CaseData(
                case_id=case_id,
                customer=customer,
                accounts=accounts,
                transactions=transactions,
                case_created_at=start_time,
                data_sources={
                    'customer_source': f"csv_extract_{start_time.strftime('%Y%m%d')}",
                    'account_source': f"csv_extract_{start_time.strftime('%Y%m%d')}",
                    'transaction_source': f"csv_extract_{start_time.strftime('%Y%m%d')}"
                })
            self.logger.log_agent_action(agent_type="DataLoader",
                                         input_data={"accounts":len(account_data),"transactions":len(transaction_data)},
                                         output_data={"accounts":len(accounts),"transactions":len(transactions)},
                                         reasoning="Case creation successful",
                                         action="create_case",
                                         error_message=None,
                                         success=True,
                                         case_id=case_id,
                                         execution_time_ms=(datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        except Exception as e:
            self.logger.log_agent_action(agent_type="DataLoader",
                                         input_data={"accounts":len(account_data),"transactions":len(transaction_data)},
                                         output_data={},
                                         reasoning="Case creation failed",
                                         action="create_case",
                                         error_message=str(e),
                                         success=False,
                                         case_id=case_id,
                                         execution_time_ms=(datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            raise
        return case
        

# ===== HELPER FUNCTIONS (PROVIDED) =====

def load_csv_data(data_dir: str = "data/") -> tuple:
    """Helper function to load all CSV files
    
    Returns:
        tuple: (customers_df, accounts_df, transactions_df)
    """
    try:
        customers_df = pd.read_csv(f"{data_dir}/customers.csv")
        accounts_df = pd.read_csv(f"{data_dir}/accounts.csv") 
        transactions_df = pd.read_csv(f"{data_dir}/transactions.csv")
        return customers_df, accounts_df, transactions_df
    except FileNotFoundError as e:
        raise FileNotFoundError(f"CSV file not found: {e}")
    except Exception as e:
        raise Exception(f"Error loading CSV data: {e}")

if __name__ == "__main__":
    print("🏗️  Foundation SAR Module")
    print("Core data schemas and utilities for SAR processing")
    print("\n📋 TODO Items:")
    print("• Implement Pydantic schemas based on CSV data")
    print("• Create ExplainabilityLogger for audit trails")
    print("• Build DataLoader for case object creation")
    print("• Add comprehensive error handling")
    print("• Write unit tests for all components")
