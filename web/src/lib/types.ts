export type ShoppingItem = {
  id: number;
  user_id: string;
  name: string;
  category: string;
  checked: boolean;
  source_decision_id?: number | null;
  created_at?: string;
  checked_at?: string | null;
};

export type Decision = {
  id?: number | null;
  decision_id?: number | null;
  ok?: boolean;
  domain?: string | null;
  suggestion?: string;
  justification?: string;
  execution_type?: string | null;
  execution_label?: string | null;
  execution_url?: string | null;
  status?: string;
  reroll_index?: number;
  locked?: boolean;
  refused?: boolean;
  refusal_message?: string | null;
  ui_message?: string | null;
  needs_domain_pick?: boolean;
  favorite?: boolean;
  context?: Record<string, unknown>;
  created_at?: string;
  user_id?: string;
  accepted?: boolean;
  route_log_id?: number | null;
};

export type UserProfile = {
  id: string;
  language?: string;
  is_pro?: number | boolean;
  profile_json?: Record<string, unknown> | string;
  guest?: boolean;
  email?: string;
  created_at?: string;
};
