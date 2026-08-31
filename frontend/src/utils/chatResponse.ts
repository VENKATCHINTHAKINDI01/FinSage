// Shared by every UI that calls sendChatQuery() (/api/v1/chat/query).
//
// The endpoint has two response shapes depending on which path handled the
// intent (backend/api/chat.py):
//   - Pipeline path (most tax intents): one narrated prose answer at
//     agent_responses.pipeline.answer.
//   - Legacy orchestrator path (a handful of intents not yet migrated —
//     investment_advice, portfolio_analysis, government_benefits,
//     eligibility_check, compliance_check, cross_border_tax): one structured
//     JSON result per invoked agent, no single narrative field.
//
// PurchaseAdvisorChat previously looked for res.response / res.message /
// res.content, none of which this endpoint has ever returned — every chat
// reply silently fell through to a raw JSON.stringify dump (or, if that
// somehow threw, a canned fallback string). This never surfaced the real
// answer text.
function humanizeKey(key: string): string {
  return key
    .replace(/_agent$/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function summarizeAgentResult(data: Record<string, any>): string[] {
  const lines: string[] = [];
  const seen = new Set<string>();

  // top_recommendations/action_items are already curated subsets of the
  // fuller scheme_details/schemes/strategies lists — prefer the curated
  // list and skip the raw one so the same scheme doesn't render twice.
  const listFields = data.top_recommendations
    ? ['top_recommendations', 'action_items', 'next_steps', 'red_flags', 'missing_documents', 'reasons']
    : ['strategies', 'schemes', 'scheme_details', 'recommendations', 'action_items', 'next_steps', 'red_flags', 'missing_documents', 'reasons'];
  for (const key of listFields) {
    const val = data[key];
    if (Array.isArray(val) && val.length) {
      for (const item of val.slice(0, 5)) {
        if (typeof item === 'string') {
          if (!seen.has(item)) { seen.add(item); lines.push(`- ${item}`); }
        } else if (item && typeof item === 'object') {
          const label = item.name || item.title || item.action || item.scheme_name || item.description;
          if (label && !seen.has(label)) {
            seen.add(label);
            lines.push(`- ${label}${item.action && item.name ? `: ${item.action}` : ''}`);
          }
        }
      }
    }
  }

  const scalarFields = [
    'compliance_score', 'risk_level', 'audit_ready', 'total_estimated_savings',
    'total_potential_savings', 'potential_savings', 'schemes_found', 'eligible',
    'recommended_form', 'financial_year',
  ];
  for (const key of scalarFields) {
    const val = data[key];
    if (val !== undefined && val !== null && val !== '') {
      lines.push(`- ${humanizeKey(key)}: ${val}`);
    }
  }

  return lines;
}

export function formatChatAnswer(res: any): string {
  if (!res) {
    return "Sorry, I couldn't get a response. Please try again.";
  }
  if (res.success === false) {
    return res.message || res.error || 'Something went wrong processing that request.';
  }

  const pipelineAnswer = res?.agent_responses?.pipeline?.answer;
  if (typeof pipelineAnswer === 'string' && pipelineAnswer.trim()) {
    return pipelineAnswer.trim();
  }

  const agentResponses = res?.agent_responses;
  if (agentResponses && typeof agentResponses === 'object') {
    const sections: string[] = [];
    for (const [agentName, data] of Object.entries(agentResponses)) {
      if (!data || typeof data !== 'object') continue;
      const lines = summarizeAgentResult(data as Record<string, any>);
      if (lines.length) {
        sections.push(`**${humanizeKey(agentName)}**\n${lines.join('\n')}`);
      }
    }
    if (sections.length) return sections.join('\n\n');
  }

  return "I found some results but couldn't format them clearly — check the relevant page (Benefits, Compliance, Smart Savings) for full details.";
}
