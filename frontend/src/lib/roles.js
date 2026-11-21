// Role names and descriptions. The server decides what each role may do; this is display only.
export const ROLES = ['viewer', 'operator', 'developer', 'auditor', 'org_admin', 'platform_admin'];

export const ROLE_LABEL = {
  viewer: 'Viewer',
  operator: 'Operator',
  developer: 'Developer',
  auditor: 'Auditor',
  org_admin: 'Organization admin',
  platform_admin: 'Platform admin',
};

export const ROLE_HELP = {
  viewer: 'Sees agents and workflows shared with them. Cannot run or change anything.',
  operator: 'Chats and runs the agents and workflows shared with them.',
  developer: 'Everything an operator can, plus builds agents, workflows, triggers and connections.',
  auditor: 'Read-only view of everything in the organization, plus the audit log and monitoring.',
  org_admin: 'Full control of their organization: users, all agents and workflows, audit log.',
  platform_admin: 'Everything, in every organization: organizations, models and platform settings.',
};

export const isAdmin = (user) => user?.role === 'org_admin' || user?.role === 'platform_admin';
export const roleLabel = (role) => ROLE_LABEL[role] || role;
