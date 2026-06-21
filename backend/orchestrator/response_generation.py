import logging
from backend.orchestrator.agent_state import AgentState

logger = logging.getLogger(__name__)

def generate_response(state: AgentState) -> AgentState:
    """Format and build the final workflow response from all agent results."""
    logger.info("Generating final workflow response")
    
    response_parts = []
    
    # 1. Header
    response_parts.append("# 📊 FinSage AI - Complete Financial & Tax Analysis Report\n")
    
    # 2. Executive Summary
    savings = state.get("savings", 0.0)
    response_parts.append("## 💡 Executive Summary")
    response_parts.append(f"- **Total Potential Annual Savings:** ₹{savings:,.2f}")
    
    # Calculate a mock quality/confidence score based on execution success
    success_count = sum(1 for res in state.get("agent_results", {}).values() if res and res.status == "success")
    total_agents = len(state.get("agents_to_invoke", [])) or 1
    quality_score = round(min(0.95, 0.5 + 0.45 * (success_count / total_agents)), 2)
    state["quality_score"] = quality_score
    response_parts.append(f"- **Report Quality Score:** {quality_score * 100}% Confidence\n")
    
    # 3. Income Analysis
    inc = state.get("income_analysis", {})
    if inc:
        response_parts.append("### 💰 Income Sources Breakdown")
        total_income = inc.get("total_income", 0.0)
        response_parts.append(f"- **Total Gross Annual Income:** ₹{total_income:,.2f}")
        pt_ded = inc.get("professional_tax_deduction", 0.0)
        if pt_ded > 0:
            response_parts.append(f"- **Professional Tax Deduction:** ₹{pt_ded:,.2f}")
            
        sources = inc.get("income_sources", [])
        if sources:
            response_parts.append("\n**Classified Income Streams:**")
            for src in sources:
                response_parts.append(
                    f"  - **{src.get('type')}:** ₹{src.get('amount', 0):,.2f} ({src.get('regularity', 'regular')}) "
                    f"| *Filing Source:* {src.get('tax_filing', 'N/A')}"
                )
        response_parts.append("")
        
    # 4. Tax Deductions
    decs = state.get("deductions_found", [])
    if decs:
        response_parts.append("### 🔍 Identified Tax Deductions")
        for dec in decs:
            desc = dec.get("description", "Deductible expense")
            code = f" (Section {dec['scheme_code']})" if dec.get("scheme_code") else ""
            response_parts.append(
                f"- **{dec.get('category')}{code}:** ₹{dec.get('amount', 0):,.2f} | *Confidence:* {dec.get('confidence', 'high')}\n"
                f"  *{desc}*"
            )
        response_parts.append("")
        
    # 5. Tax Strategies
    strats = state.get("strategies_validated", [])
    if strats:
        response_parts.append("### 📈 Recommended Tax Optimization Strategies")
        for strat in strats:
            risk = strat.get("risk", "Low")
            diff = strat.get("difficulty", "Easy")
            action = strat.get("action_required", strat.get("action", ""))
            response_parts.append(
                f"- **{strat.get('strategy_name')}:** Potential Savings of **₹{strat.get('savings', strat.get('estimated_savings', 0)):,.2f}**\n"
                f"  - *Action:* {action}\n"
                f"  - *Difficulty:* {diff} | *Risk Level:* {risk} | *Timeline:* {strat.get('timeline')}"
            )
        response_parts.append("")
        
    # 6. Fallback if no specific data was set
    if not inc and not decs and not strats:
        response_parts.append("Analysis completed. Detailed information could not be parsed from agent outputs. Please refine your query.")
        
    state["response"] = "\n".join(response_parts)
    
    # Store recommendation list for API response
    recs_list = []
    for strat in strats:
        recs_list.append(f"{strat.get('strategy_name')}: {strat.get('action_required', strat.get('action', ''))}")
    state["recommendations"] = recs_list
    
    return state
