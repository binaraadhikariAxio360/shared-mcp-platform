'use client';

import React, { useState, useEffect } from 'react';
import {
  AlertOctagon,
  AlertTriangle,
  Bot,
  Briefcase,
  CheckCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  ExternalLink,
  FileCheck2,
  FileText,
  Filter,
  FolderKanban,
  Layers,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Terminal,
  Trash2,
  User,
  UserCheck,
  Users,
  X,
  LogOut,
  LogIn,
  Shield,
} from 'lucide-react';

interface SessionProfile {
  tenantId: string;
  tenantName: string;
  userRole: string;
  userId: string;
  userName: string;
  roleLabel: string;
  description: string;
}

const DEMO_PROFILES: SessionProfile[] = [
  {
    tenantId: 'tenant-001',
    tenantName: 'Vanguard Enterprise Operations',
    userRole: 'OPERATIONS_DIRECTOR',
    userId: 'user-dir-001',
    userName: 'Alexandra Ramos',
    roleLabel: 'Operations Director (Admin)',
    description: 'Full CRUD on projects, deliverables, team workload, and compliance controls.',
  },
  {
    tenantId: 'tenant-001',
    tenantName: 'Vanguard Enterprise Operations',
    userRole: 'PROJECT_MANAGER',
    userId: 'user-pm-001',
    userName: 'Marcus Chen',
    roleLabel: 'Project Manager (Manager)',
    description: 'Full CRUD on deliverables and sprint projects; update workload assignments.',
  },
  {
    tenantId: 'tenant-001',
    tenantName: 'Vanguard Enterprise Operations',
    userRole: 'TEAM_CONTRIBUTOR',
    userId: 'user-staff-001',
    userName: 'Devon Cooper',
    roleLabel: 'Team Contributor (Staff)',
    description: 'Update assigned deliverable status; cannot delete deliverables or edit projects.',
  },
  {
    tenantId: 'tenant-001',
    tenantName: 'Vanguard Enterprise Operations',
    userRole: 'COMPLIANCE_AUDITOR',
    userId: 'user-audit-001',
    userName: 'Evelyn Cross',
    roleLabel: 'Compliance Auditor (Auditor)',
    description: 'Audit compliance documents (mark AUDITED); read-only on operational tasks.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'BluePeak Global Operations',
    userRole: 'OPERATIONS_DIRECTOR',
    userId: 'user-dir-002',
    userName: 'Sterling Archer',
    roleLabel: 'Operations Director (Admin)',
    description: 'Global operations and sprint compliance orchestrator for BluePeak.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'BluePeak Global Operations',
    userRole: 'PROJECT_MANAGER',
    userId: 'user-pm-002',
    userName: 'Sophia Rivera',
    roleLabel: 'Project Manager (Manager)',
    description: 'Manage sprint deliverables, milestones, and cross-functional capacity.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'BluePeak Global Operations',
    userRole: 'TEAM_CONTRIBUTOR',
    userId: 'user-staff-002',
    userName: 'Liam Gallagher',
    roleLabel: 'Team Contributor (Staff)',
    description: 'Complete operational sprint tasks and track technical milestones.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'BluePeak Global Operations',
    userRole: 'COMPLIANCE_AUDITOR',
    userId: 'user-audit-002',
    userName: 'Harold Finch',
    roleLabel: 'Compliance Auditor (Auditor)',
    description: 'Lead external security auditing, ISO certifications, and risk reviews.',
  },
];

interface OpsProject {
  id: string;
  name: string;
  code: string;
  status: string;
  sprint_cycle: string;
  target_date: string;
}

interface OpsTeamMember {
  id: string;
  name: string;
  role: string;
  email?: string;
  max_task_threshold: number;
  active_tasks_count: number;
}

interface OpsDeliverable {
  id: string;
  title: string;
  project_id?: string;
  project_name?: string;
  assignee_id?: string;
  assignee_name?: string;
  priority: string;
  status: string;
  due_date: string;
  sla_days_overdue: number;
}

interface OpsComplianceDoc {
  id: string;
  title: string;
  standard: string;
  status: string;
  audit_date: string;
  auditor_name: string;
}

interface DashboardSummary {
  tenant_id: string;
  organization_name: string;
  active_projects_count: number;
  overdue_tasks_count: number;
  critical_overdue_count: number;
  overburdened_staff_count: number;
  compliance_audited_count: number;
  total_deliverables_count: number;
  completion_rate: number;
  sla_escalation_status: string;
  priority_breakdown: Record<string, number>;
  status_breakdown: Record<string, number>;
}

interface CopilotExecution {
  query: string;
  tool: string;
  status: 'executing' | 'success' | 'error';
  latencyMs: number;
  resultSummary: string;
  jsonTrace?: any;
}

const API_BASE = 'http://localhost:5004';

export default function OnScribeDashboard() {
  // Multi-Tenant & RBAC Session State
  const [tenantId, setTenantId] = useState('tenant-001');
  const [userRole, setUserRole] = useState('OPERATIONS_DIRECTOR');
  const [userId, setUserId] = useState('user-dir-001');
  const [userName, setUserName] = useState('Evelyn Reed');
  const [companyName, setCompanyName] = useState('Vanguard Enterprise Operations');
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isSessionChecked, setIsSessionChecked] = useState(false);

  // Dedicated SaaS Auth Portal State
  const [authTab, setAuthTab] = useState<'signin' | 'signup'>('signin');
  const [loginEmail, setLoginEmail] = useState('director@apexops.com');
  const [loginPassword, setLoginPassword] = useState('password123');
  const [registerFullName, setRegisterFullName] = useState('');
  const [registerEmail, setRegisterEmail] = useState('');
  const [registerPassword, setRegisterPassword] = useState('');
  const [registerCompany, setRegisterCompany] = useState('');
  const [registerRole, setRegisterRole] = useState('OPERATIONS_DIRECTOR');
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(false);

  // Profile Switcher Modal State
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [modalTenant, setModalTenant] = useState('tenant-001');
  const [modalRole, setModalRole] = useState('OPERATIONS_DIRECTOR');

  const [activeTab, setActiveTab] = useState<'dashboard' | 'deliverables' | 'projects' | 'team' | 'compliance'>('dashboard');
  const [loading, setLoading] = useState(true);
  const [dbHealthy, setDbHealthy] = useState<boolean | null>(null);

  // Core Data State
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [deliverables, setDeliverables] = useState<OpsDeliverable[]>([]);
  const [projects, setProjects] = useState<OpsProject[]>([]);
  const [team, setTeam] = useState<OpsTeamMember[]>([]);
  const [complianceDocs, setComplianceDocs] = useState<OpsComplianceDoc[]>([]);

  // Filters & Search
  const [deliverableFilter, setDeliverableFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Modals
  const [showAddDeliverableModal, setShowAddDeliverableModal] = useState(false);
  const [showAddProjectModal, setShowAddProjectModal] = useState(false);
  const [showAddTeamModal, setShowAddTeamModal] = useState(false);
  const [showAddComplianceModal, setShowAddComplianceModal] = useState(false);

  // Form State
  const [newDeliverable, setNewDeliverable] = useState({
    title: '',
    project_id: '',
    assignee_id: '',
    priority: 'HIGH',
    due_date: '2026-11-15',
    sla_days_overdue: 0,
  });

  const [newProject, setNewProject] = useState({
    name: '',
    code: '',
    sprint_cycle: 'Sprint 24-Q4',
    target_date: '2026-12-15',
  });

  const [newTeamMember, setNewTeamMember] = useState({
    name: '',
    role: 'Operations Analyst',
    email: '',
    max_task_threshold: 4,
  });

  const [newCompliance, setNewCompliance] = useState({
    title: '',
    standard: 'ISO 27001',
    status: 'AUDITED',
    audit_date: '2026-10-20',
    auditor_name: 'Apex Governance Bureau',
  });

  // Copilot Drawer State
  const [copilotOpen, setCopilotOpen] = useState(true);
  const [copilotInput, setCopilotInput] = useState('');
  const [isCopilotExecuting, setIsCopilotExecuting] = useState(false);
  const [copilotHistory, setCopilotHistory] = useState<CopilotExecution[]>([
    {
      query: 'Audit critical SLA violations and team bottleneck capacity',
      tool: 'onscribe.list_overdue_tasks',
      status: 'success',
      latencyMs: 38,
      resultSummary: 'Identified 4 overdue deliverables. Devon Cooper is operating above threshold (5/4 tasks).',
      jsonTrace: {
        overdue_count: 4,
        critical_count: 1,
        overburdened_lead: 'Devon Cooper (125% capacity)',
      },
    },
  ]);
  const [expandedTraceIndex, setExpandedTraceIndex] = useState<number | null>(null);

  // Toast feedback
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  // Dynamic Request Headers Helper
  const getHeaders = (extraHeaders: Record<string, string> = {}) => ({
    'Content-Type': 'application/json',
    'x-tenant-id': tenantId,
    'x-user-role': userRole,
    'x-user-id': userId,
    ...extraHeaders,
  });

  // ---------------------------------------------------------------------------
  // Data Fetching with Multi-Tenant & RBAC Isolation
  // ---------------------------------------------------------------------------
  const fetchDataFor = async (tId: string, uRole: string, uId: string) => {
    setLoading(true);
    try {
      const headers = {
        'Content-Type': 'application/json',
        'x-tenant-id': tId,
        'x-user-role': uRole,
        'x-user-id': uId,
      };

      // 1. Health
      try {
        const healthRes = await fetch(`${API_BASE}/health`);
        if (healthRes.ok) {
          const h = await healthRes.json();
          setDbHealthy(h.database_connected);
        } else {
          setDbHealthy(false);
        }
      } catch {
        setDbHealthy(false);
      }

      // 2. Summary
      const summaryRes = await fetch(`${API_BASE}/api/v1/dashboard/summary`, { headers });
      if (summaryRes.ok) setSummary(await summaryRes.json());

      // 3. Deliverables
      const dlvRes = await fetch(`${API_BASE}/api/v1/deliverables`, { headers });
      if (dlvRes.ok) setDeliverables(await dlvRes.json());

      // 4. Projects
      const prjRes = await fetch(`${API_BASE}/api/v1/projects`, { headers });
      if (prjRes.ok) setProjects(await prjRes.json());

      // 5. Team
      const teamRes = await fetch(`${API_BASE}/api/v1/team`, { headers });
      if (teamRes.ok) setTeam(await teamRes.json());

      // 6. Compliance
      const cmpRes = await fetch(`${API_BASE}/api/v1/compliance`, { headers });
      if (cmpRes.ok) setComplianceDocs(await cmpRes.json());
    } catch (err) {
      console.error('Error fetching OnScribe data:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchData = () => fetchDataFor(tenantId, userRole, userId);

  // Mount Session Restoration
  useEffect(() => {
    try {
      const saved = localStorage.getItem('onscribe_auth_session');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed?.user) {
          setTenantId(parsed.user.tenant_id);
          setUserRole(parsed.user.role);
          setUserId(parsed.user.id);
          setUserName(parsed.user.name);
          setCompanyName(parsed.user.company_name || parsed.user.tenant_id);
          setIsLoggedIn(true);
          fetchDataFor(parsed.user.tenant_id, parsed.user.role, parsed.user.id);
        } else {
          setIsLoggedIn(false);
        }
      } else {
        setIsLoggedIn(false);
      }
    } catch (e) {
      setIsLoggedIn(false);
    } finally {
      setIsSessionChecked(true);
    }
  }, []);

  const handleAuthLogin = async (e?: React.FormEvent, customEmail?: string, customPass?: string) => {
    if (e) e.preventDefault();
    setAuthError(null);
    setIsAuthLoading(true);
    const emailToUse = customEmail || loginEmail;
    const passToUse = customPass || loginPassword;
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: emailToUse, password: passToUse }),
      });
      const data = await res.json();
      if (!res.ok) {
        setAuthError(data.detail || 'Login failed. Please check credentials.');
        showToast(data.detail || 'Login failed');
      } else {
        localStorage.setItem('onscribe_auth_session', JSON.stringify({ token: data.access_token, user: data.user }));
        setTenantId(data.user.tenant_id);
        setUserRole(data.user.role);
        setUserId(data.user.id);
        setUserName(data.user.name);
        setCompanyName(data.user.company_name || data.user.tenant_id);
        setIsLoggedIn(true);
        setShowAuthModal(false);
        fetchDataFor(data.user.tenant_id, data.user.role, data.user.id);
        showToast(`Welcome back, ${data.user.name}!`);
      }
    } catch (err: any) {
      setAuthError('Unable to connect to authentication backend.');
    } finally {
      setIsAuthLoading(false);
    }
  };

  const handleAuthRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!registerEmail || !registerPassword || !registerFullName) {
      setAuthError('Please fill in all required fields.');
      return;
    }
    setAuthError(null);
    setIsAuthLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: registerFullName,
          email: registerEmail,
          password: registerPassword,
          company_name: registerCompany || undefined,
          role: registerRole,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setAuthError(data.detail || 'Registration failed.');
        showToast(data.detail || 'Registration failed');
      } else {
        localStorage.setItem('onscribe_auth_session', JSON.stringify({ token: data.access_token, user: data.user }));
        setTenantId(data.user.tenant_id);
        setUserRole(data.user.role);
        setUserId(data.user.id);
        setUserName(data.user.name);
        setCompanyName(data.user.company_name || data.user.tenant_id);
        setIsLoggedIn(true);
        setShowAuthModal(false);
        fetchDataFor(data.user.tenant_id, data.user.role, data.user.id);
        showToast(`Operations unit registered for ${data.user.company_name}!`);
      }
    } catch (err: any) {
      setAuthError('Unable to connect to authentication backend.');
    } finally {
      setIsAuthLoading(false);
    }
  };

  const handleSwitchSession = (targetTenant: string, targetRole: string) => {
    const profileMatch = DEMO_PROFILES.find(
      (p) => p.tenantId === targetTenant && p.userRole === targetRole
    ) || {
      tenantId: targetTenant,
      tenantName: targetTenant === 'tenant-001' ? 'Apex Operations' : 'BluePeak Ops',
      userRole: targetRole,
      userId: `user-${targetRole.toLowerCase()}-${targetTenant}`,
      userName: `User (${targetRole})`,
      roleLabel: targetRole,
      description: '',
    };

    setSummary(null);
    setDeliverables([]);
    setProjects([]);
    setTeam([]);
    setComplianceDocs([]);

    setTenantId(targetTenant);
    setUserRole(targetRole);
    setUserId(profileMatch.userId);
    setUserName(profileMatch.userName);
    setCompanyName(profileMatch.tenantName);
    setIsLoggedIn(true);
    setShowAuthModal(false);

    localStorage.setItem('onscribe_auth_session', JSON.stringify({
      token: `moc_sess_${profileMatch.userId}_${targetTenant}`,
      user: {
        id: profileMatch.userId,
        name: profileMatch.userName,
        email: `${targetRole.toLowerCase()}@${targetTenant}.com`,
        role: targetRole,
        tenant_id: targetTenant,
        company_name: profileMatch.tenantName,
      }
    }));

    fetchDataFor(targetTenant, targetRole, profileMatch.userId);
    showToast(`Active: ${profileMatch.userName} (${targetRole}) • ${targetTenant}`);
  };

  const handleSignOut = () => {
    localStorage.removeItem('onscribe_auth_session');
    setSummary(null);
    setDeliverables([]);
    setProjects([]);
    setTeam([]);
    setComplianceDocs([]);
    setIsLoggedIn(false);
    setUserRole('COMPLIANCE_AUDITOR');
    setUserName('Guest Auditor');
    setCompanyName('');
    showToast('Signed out of session. Session purged.');
  };

  // ---------------------------------------------------------------------------
  // Deliverable Actions
  // ---------------------------------------------------------------------------
  const handleToggleDeliverableStatus = async (dlv: OpsDeliverable) => {
    const nextStatus = dlv.status === 'COMPLETED' ? 'IN_PROGRESS' : 'COMPLETED';
    const original = [...deliverables];

    // Optimistic UI update
    setDeliverables((prev) =>
      prev.map((item) => (item.id === dlv.id ? { ...item, status: nextStatus, sla_days_overdue: nextStatus === 'COMPLETED' ? 0 : item.sla_days_overdue } : item))
    );

    try {
      const res = await fetch(`${API_BASE}/api/v1/deliverables/${dlv.id}`, {
        method: 'PUT',
        headers: getHeaders(),
        body: JSON.stringify({ status: nextStatus }),
      });
      if (res.ok) {
        showToast(`Deliverable marked as ${nextStatus}`);
        fetchData();
      } else {
        setDeliverables(original);
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission Denied: Cannot update deliverable status');
      }
    } catch (err) {
      setDeliverables(original);
      showToast('Network error while updating deliverable');
    }
  };

  const handleCreateDeliverable = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDeliverable.title) return;

    try {
      const res = await fetch(`${API_BASE}/api/v1/deliverables`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(newDeliverable),
      });
      if (res.ok) {
        showToast('Deliverable added to sprint board');
        setShowAddDeliverableModal(false);
        setNewDeliverable({
          title: '',
          project_id: '',
          assignee_id: '',
          priority: 'HIGH',
          due_date: '2026-11-15',
          sla_days_overdue: 0,
        });
        fetchData();
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission Denied: Cannot create deliverable');
      }
    } catch {
      showToast('Error creating deliverable');
    }
  };

  const handleDeleteDeliverable = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/deliverables/${id}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });
      if (res.ok) {
        showToast('Deliverable deleted');
        setDeliverables((prev) => prev.filter((d) => d.id !== id));
        fetchData();
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission Denied: Cannot delete deliverable');
      }
    } catch {
      showToast('Failed to delete deliverable');
    }
  };

  // ---------------------------------------------------------------------------
  // Project Actions
  // ---------------------------------------------------------------------------
  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProject.name || !newProject.code) return;

    try {
      const res = await fetch(`${API_BASE}/api/v1/projects`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(newProject),
      });
      if (res.ok) {
        showToast(`Project '${newProject.name}' activated`);
        setShowAddProjectModal(false);
        setNewProject({ name: '', code: '', sprint_cycle: 'Sprint 24-Q4', target_date: '2026-12-15' });
        fetchData();
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission Denied: Cannot create project');
      }
    } catch {
      showToast('Error registering project');
    }
  };

  const handleDeleteProject = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/projects/${id}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });
      if (res.ok) {
        showToast('Project archived');
        fetchData();
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission Denied: Cannot delete project');
      }
    } catch {
      showToast('Failed to delete project');
    }
  };

  // ---------------------------------------------------------------------------
  // Team Actions
  // ---------------------------------------------------------------------------
  const handleCreateTeamMember = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTeamMember.name) return;

    try {
      const res = await fetch(`${API_BASE}/api/v1/team`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(newTeamMember),
      });
      if (res.ok) {
        showToast(`Onboarded ${newTeamMember.name} to team roster`);
        setShowAddTeamModal(false);
        setNewTeamMember({ name: '', role: 'Operations Analyst', email: '', max_task_threshold: 4 });
        fetchData();
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission Denied: Cannot onboard team members');
      }
    } catch {
      showToast('Error creating team member');
    }
  };

  // ---------------------------------------------------------------------------
  // Compliance Actions
  // ---------------------------------------------------------------------------
  const handleCreateCompliance = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCompliance.title) return;

    try {
      const res = await fetch(`${API_BASE}/api/v1/compliance`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(newCompliance),
      });
      if (res.ok) {
        showToast(`Registered compliance standard '${newCompliance.title}'`);
        setShowAddComplianceModal(false);
        setNewCompliance({
          title: '',
          standard: 'ISO 27001',
          status: 'AUDITED',
          audit_date: '2026-10-20',
          auditor_name: 'Apex Governance Bureau',
        });
        fetchData();
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission Denied: Cannot register compliance documents');
      }
    } catch {
      showToast('Error adding compliance record');
    }
  };

  // ---------------------------------------------------------------------------
  // Live AI Copilot Tool Execution
  // ---------------------------------------------------------------------------
  const executeCopilotTool = async (promptQuery: string) => {
    setIsCopilotExecuting(true);
    const start = performance.now();

    let endpoint = `${API_BASE}/internal/tools/onscribe.get_operations_summary`;
    let toolName = 'onscribe.get_operations_summary';
    let body: any = {};

    const lower = promptQuery.toLowerCase();
    if (lower.includes('overdue') || lower.includes('critical') || lower.includes('sla')) {
      endpoint = `${API_BASE}/internal/tools/onscribe.list_overdue_tasks`;
      toolName = 'onscribe.list_overdue_tasks';
      body = { priority: lower.includes('critical') ? 'CRITICAL' : undefined };
    } else if (lower.includes('workload') || lower.includes('staff') || lower.includes('capacity') || lower.includes('overload')) {
      endpoint = `${API_BASE}/internal/tools/onscribe.analyze_team_workload`;
      toolName = 'onscribe.analyze_team_workload';
      body = {};
    }

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(body),
      });

      const latencyMs = Math.round(performance.now() - start);

      if (res.ok) {
        const data = await res.json();
        let summaryText = '';

        if (toolName === 'onscribe.list_overdue_tasks') {
          summaryText = `Found ${data.count} overdue tasks (${data.critical_count} critical SLA breaches).`;
        } else if (toolName === 'onscribe.analyze_team_workload') {
          summaryText = `Audited ${data.member_count} staff members. ${data.overburdened_count} exceeding capacity threshold.`;
        } else {
          summaryText = `Operations status: ${data.sla_risk_level} SLA risk. ${data.active_projects} active sprint projects.`;
        }

        setCopilotHistory((prev) => [
          {
            query: promptQuery,
            tool: toolName,
            status: 'success',
            latencyMs,
            resultSummary: summaryText,
            jsonTrace: data,
          },
          ...prev,
        ]);
      } else {
        setCopilotHistory((prev) => [
          {
            query: promptQuery,
            tool: toolName,
            status: 'error',
            latencyMs: Math.round(performance.now() - start),
            resultSummary: 'Database tool execution failed.',
          },
          ...prev,
        ]);
      }
    } catch (err: any) {
      setCopilotHistory((prev) => [
        {
          query: promptQuery,
          tool: toolName,
          status: 'error',
          latencyMs: Math.round(performance.now() - start),
          resultSummary: `Connection error: ${err.message || 'Network error'}`,
        },
        ...prev,
      ]);
    } finally {
      setIsCopilotExecuting(false);
      setCopilotInput('');
    }
  };

  // Filtered deliverables
  const filteredDeliverables = deliverables.filter((d) => {
    if (deliverableFilter === 'OVERDUE' && d.status !== 'OVERDUE') return false;
    if (deliverableFilter === 'IN_PROGRESS' && d.status !== 'IN_PROGRESS') return false;
    if (deliverableFilter === 'COMPLETED' && d.status !== 'COMPLETED') return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        d.title.toLowerCase().includes(q) ||
        (d.assignee_name && d.assignee_name.toLowerCase().includes(q)) ||
        (d.project_name && d.project_name.toLowerCase().includes(q))
      );
    }
    return true;
  });

  if (!isSessionChecked) {
    return (
      <div className="min-h-screen w-screen flex items-center justify-center bg-slate-950 text-white">
        <RefreshCw className="w-8 h-8 animate-spin text-sky-400" />
      </div>
    );
  }

  if (isSessionChecked && !isLoggedIn) {
    return (
      <div className="min-h-screen w-screen flex flex-col items-center justify-center bg-gradient-to-br from-slate-950 via-slate-900 to-sky-950 text-slate-100 p-6 relative overflow-y-auto">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-sky-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col items-center mb-6 text-center z-10">
          <div className="h-14 w-14 rounded-2xl bg-gradient-to-tr from-sky-600 via-sky-500 to-blue-600 flex items-center justify-center text-white shadow-xl shadow-sky-500/25 mb-3 border border-sky-400/30">
            <FolderKanban className="w-7 h-7" />
          </div>
          <h1 className="text-2xl font-black tracking-tight text-white flex items-center gap-2">
            OnScribe <span className="text-sky-400 font-medium text-xs px-2 py-0.5 rounded-full bg-sky-950/80 border border-sky-500/30">Operations SaaS</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1 max-w-sm">
            Operations & Compliance Orchestration with PostgreSQL 16 Multi-Tenant Isolation
          </p>
        </div>

        <div className="w-full max-w-md bg-slate-900/80 border border-slate-800 rounded-2xl shadow-2xl backdrop-blur-xl p-6 z-10">
          <div className="flex p-1 bg-slate-800/80 rounded-xl mb-5 border border-slate-700/60">
            <button
              onClick={() => { setAuthTab('signin'); setAuthError(null); }}
              className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
                authTab === 'signin'
                  ? 'bg-sky-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setAuthTab('signup'); setAuthError(null); }}
              className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
                authTab === 'signup'
                  ? 'bg-sky-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Register Unit
            </button>
          </div>

          {authError && (
            <div className="mb-4 p-3 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2 animate-in fade-in">
              <AlertOctagon className="w-4 h-4 shrink-0 text-rose-400" />
              <span>{authError}</span>
            </div>
          )}

          {authTab === 'signin' ? (
            <form onSubmit={(e) => handleAuthLogin(e)} className="space-y-3.5">
              <div>
                <label className="block text-[11px] font-medium text-slate-300 mb-1">Email Address</label>
                <input
                  type="email"
                  required
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  placeholder="director@apexops.com"
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-300 mb-1">Password</label>
                <input
                  type="password"
                  required
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 focus:ring-1 focus:ring-sky-500"
                />
              </div>

              <button
                type="submit"
                disabled={isAuthLoading}
                className="w-full mt-2 py-2.5 px-4 bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white font-semibold text-xs rounded-xl shadow-lg shadow-sky-600/30 transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                {isAuthLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
                <span>{isAuthLoading ? 'Authenticating...' : 'Sign In to Operations'}</span>
              </button>
            </form>
          ) : (
            <form onSubmit={handleAuthRegister} className="space-y-3">
              <div>
                <label className="block text-[11px] font-medium text-slate-300 mb-1">Full Name</label>
                <input
                  type="text"
                  required
                  value={registerFullName}
                  onChange={(e) => setRegisterFullName(e.target.value)}
                  placeholder="Evelyn Reed"
                  className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-300 mb-1">Operations Organization Name</label>
                <input
                  type="text"
                  value={registerCompany}
                  onChange={(e) => setRegisterCompany(e.target.value)}
                  placeholder="Apex Global Operations"
                  className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[11px] font-medium text-slate-300 mb-1">Email</label>
                  <input
                    type="email"
                    required
                    value={registerEmail}
                    onChange={(e) => setRegisterEmail(e.target.value)}
                    placeholder="director@apexops.com"
                    className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-300 mb-1">Password</label>
                  <input
                    type="password"
                    required
                    value={registerPassword}
                    onChange={(e) => setRegisterPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-300 mb-1">Operational Role</label>
                <select
                  value={registerRole}
                  onChange={(e) => setRegisterRole(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-white focus:outline-none focus:border-sky-500"
                >
                  <option value="OPERATIONS_DIRECTOR">Operations Director (Admin)</option>
                  <option value="PROJECT_MANAGER">Project Manager (Editor)</option>
                  <option value="TEAM_LEAD">Team Lead (Editor)</option>
                  <option value="COMPLIANCE_AUDITOR">Compliance Auditor (Viewer)</option>
                </select>
              </div>

              <button
                type="submit"
                disabled={isAuthLoading}
                className="w-full mt-2 py-2.5 px-4 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold text-xs rounded-xl shadow-lg shadow-blue-600/30 transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                {isAuthLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                <span>{isAuthLoading ? 'Provisioning Unit...' : 'Create Operations Unit & Account'}</span>
              </button>
            </form>
          )}

          <div className="mt-5 pt-4 border-t border-slate-800">
            <p className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase text-center mb-2.5">
              1-Click Demo Evaluation Personas
            </p>
            <div className="space-y-1.5">
              <button
                type="button"
                onClick={() => handleAuthLogin(undefined, 'director@apexops.com', 'password123')}
                className="w-full p-2 rounded-xl bg-slate-800/70 hover:bg-sky-950/40 hover:border-sky-500/50 border border-slate-700/60 text-left transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="text-xs font-bold text-white group-hover:text-sky-300">Evelyn Reed (Operations Director)</p>
                  <p className="text-[10px] text-slate-400">Apex Enterprise Operations • <span className="font-mono text-sky-400">tenant-001</span></p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 font-medium">Quick Login</span>
              </button>

              <button
                type="button"
                onClick={() => handleAuthLogin(undefined, 'pm@apexops.com', 'password123')}
                className="w-full p-2 rounded-xl bg-slate-800/70 hover:bg-blue-950/40 hover:border-blue-500/50 border border-slate-700/60 text-left transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="text-xs font-bold text-white group-hover:text-blue-300">Aaron Zhang (Project Manager)</p>
                  <p className="text-[10px] text-slate-400">Apex Enterprise Operations • <span className="font-mono text-blue-400">tenant-001</span></p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 font-medium">Quick Login</span>
              </button>

              <button
                type="button"
                onClick={() => handleAuthLogin(undefined, 'director@bluepeakops.com', 'password123')}
                className="w-full p-2 rounded-xl bg-slate-800/70 hover:bg-purple-950/40 hover:border-purple-500/50 border border-slate-700/60 text-left transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="text-xs font-bold text-white group-hover:text-purple-300">Commander Jackson Vance (Operations Director)</p>
                  <p className="text-[10px] text-slate-400">BluePeak Global Operations • <span className="font-mono text-purple-400">tenant-002</span></p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 font-medium">Quick Login</span>
              </button>
            </div>
          </div>
        </div>

        <div className="mt-5 text-center text-[11px] text-slate-500 flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-sky-500" />
          <span>Shared PostgreSQL 16 Multi-Tenant Isolation • Row-Level Security Enforced</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full bg-slate-50 text-slate-900 font-sans overflow-hidden">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-5 right-5 z-50 bg-slate-900 text-white px-4 py-3 rounded-lg shadow-xl text-sm flex items-center gap-2 border border-slate-700 animate-in fade-in slide-in-from-bottom-3">
          <Sparkles className="w-4 h-4 text-sky-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* LEFT PERSISTENT SIDEBAR (~260px) */}
      {/* --------------------------------------------------------------------- */}
      <aside className="w-[260px] flex-shrink-0 bg-white border-r border-slate-200 flex flex-col justify-between shadow-xs z-20">
        <div>
          {/* Logo & Identity */}
          <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-sky-600 to-blue-600 flex items-center justify-center text-white shadow-xs">
              <FolderKanban className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-slate-900 tracking-tight text-sm">OnScribe</span>
                <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded-sm bg-sky-50 text-sky-700 border border-sky-200">
                  Ops
                </span>
              </div>
              <p className="text-[11px] text-slate-600 truncate max-w-[150px]">Operations & Compliance</p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="p-3 space-y-1">
            <button
              onClick={() => setActiveTab('dashboard')}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'dashboard' ? 'bg-sky-50 text-sky-700 font-semibold shadow-xs' : 'text-slate-600 hover:bg-slate-100/70 hover:text-slate-900'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Layers className="w-4 h-4" />
                <span>Executive Dashboard</span>
              </div>
              {summary && summary.overdue_tasks_count > 0 && (
                <span className="text-[11px] px-1.5 py-0.2 rounded-full bg-rose-100 text-rose-700 font-bold border border-rose-200">
                  {summary.overdue_tasks_count}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab('deliverables')}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'deliverables' ? 'bg-sky-50 text-sky-700 font-semibold shadow-xs' : 'text-slate-600 hover:bg-slate-100/70 hover:text-slate-900'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <FileCheck2 className="w-4 h-4" />
                <span>Deliverables & Tasks</span>
              </div>
              <span className="text-[11px] px-1.5 py-0.2 rounded-full bg-slate-100 text-slate-600 font-semibold">
                {deliverables.length}
              </span>
            </button>

            <button
              onClick={() => setActiveTab('projects')}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'projects' ? 'bg-sky-50 text-sky-700 font-semibold shadow-xs' : 'text-slate-600 hover:bg-slate-100/70 hover:text-slate-900'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Briefcase className="w-4 h-4" />
                <span>Sprint Projects</span>
              </div>
              <span className="text-[11px] px-1.5 py-0.2 rounded-full bg-slate-100 text-slate-600 font-semibold">
                {projects.length}
              </span>
            </button>

            <button
              onClick={() => setActiveTab('team')}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'team' ? 'bg-sky-50 text-sky-700 font-semibold shadow-xs' : 'text-slate-600 hover:bg-slate-100/70 hover:text-slate-900'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Users className="w-4 h-4" />
                <span>Team Workload</span>
              </div>
              <span className="text-[11px] px-1.5 py-0.2 rounded-full bg-slate-100 text-slate-600 font-semibold">
                {team.length}
              </span>
            </button>

            <button
              onClick={() => setActiveTab('compliance')}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'compliance' ? 'bg-sky-50 text-sky-700 font-semibold shadow-xs' : 'text-slate-600 hover:bg-slate-100/70 hover:text-slate-900'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <ShieldCheck className="w-4 h-4" />
                <span>Compliance & Audits</span>
              </div>
              <span className="text-[11px] px-1.5 py-0.2 rounded-full bg-slate-100 text-slate-600 font-semibold">
                {complianceDocs.length}
              </span>
            </button>
          </nav>
        </div>

        {/* Footer & Ecosystem Hub Switcher */}
        <div className="p-3 border-t border-slate-100 space-y-3">
          {/* Multi-App Hub Links */}
          <div className="bg-slate-50/80 p-2.5 rounded-lg border border-slate-200/80">
            <span className="text-[10px] uppercase font-bold text-slate-600 tracking-wider block mb-1.5">
              Axio360 Ecosystem Hub
            </span>
            <div className="grid grid-cols-3 gap-1">
              <a
                href="http://localhost:3001"
                target="_blank"
                rel="noreferrer"
                className="text-[11px] text-center py-1 rounded bg-white text-slate-700 hover:bg-emerald-50 hover:text-emerald-700 border border-slate-200/60 transition-colors flex items-center justify-center gap-1 font-medium"
                title="PractiCare Clinic Management"
              >
                <span>Clin</span>
                <ExternalLink className="w-2.5 h-2.5" />
              </a>
              <a
                href="http://localhost:3002"
                target="_blank"
                rel="noreferrer"
                className="text-[11px] text-center py-1 rounded bg-white text-slate-700 hover:bg-indigo-50 hover:text-indigo-700 border border-slate-200/60 transition-colors flex items-center justify-center gap-1 font-medium"
                title="TaxSnap Corporate Tax"
              >
                <span>Tax</span>
                <ExternalLink className="w-2.5 h-2.5" />
              </a>
              <a
                href="http://localhost:3003"
                target="_blank"
                rel="noreferrer"
                className="text-[11px] text-center py-1 rounded bg-white text-slate-700 hover:bg-rose-50 hover:text-rose-700 border border-slate-200/60 transition-colors flex items-center justify-center gap-1 font-medium"
                title="PropSights Real Estate"
              >
                <span>Prop</span>
                <ExternalLink className="w-2.5 h-2.5" />
              </a>
            </div>
          </div>
        </div>

        {/* User Profile Card & Tenant Switcher Footer */}
        <div className="p-3 border-t border-slate-200/80 bg-slate-50/70">
          {isLoggedIn ? (
            <div className="space-y-2">
              <div
                onClick={() => setShowAuthModal(true)}
                className="group p-2.5 rounded-xl border border-slate-200 bg-white hover:border-sky-300 hover:shadow-xs transition-all cursor-pointer"
              >
                <div className="flex items-center gap-2.5">
                  <div className="relative">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-sky-600 to-sky-500 text-white font-bold text-xs flex items-center justify-center shadow-xs">
                      {userName.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()}
                    </div>
                    <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-white" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-bold text-slate-800 truncate group-hover:text-sky-600 transition-colors">
                      {userName}
                    </p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[9px] font-bold tracking-tight uppercase bg-sky-50 text-sky-700 border border-sky-200">
                        {userRole}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="mt-2 pt-1.5 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-500">
                  <span className="truncate max-w-[140px] font-medium text-slate-600">
                    {companyName || (tenantId === 'tenant-001' ? 'Apex Operations' : 'BluePeak Ops')} • {tenantId}
                  </span>
                  <span className="text-sky-600 font-semibold group-hover:underline">Switch</span>
                </div>
              </div>

              <button
                onClick={handleSignOut}
                className="w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg border border-slate-200 bg-white hover:bg-rose-50 hover:text-rose-700 hover:border-rose-200 text-slate-600 font-medium text-[11px] transition-all"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Sign Out</span>
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowAuthModal(true)}
              className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl bg-sky-600 hover:bg-sky-700 text-white font-semibold text-xs shadow-xs transition-all"
            >
              <LogIn className="w-4 h-4" />
              <span>Sign In / Switch Profile</span>
            </button>
          )}

          {/* Database Context */}
          <div className="mt-2.5 pt-2 border-t border-slate-200/60 flex items-center justify-between text-[10px] text-slate-400">
            <div className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="font-mono font-medium text-slate-600">PostgreSQL 16</span>
            </div>
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${
                dbHealthy
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-rose-50 text-rose-700 border-rose-200'
              }`}
            >
              {dbHealthy ? 'PG: Live' : 'PG: Offline'}
            </span>
          </div>
        </div>
      </aside>

      {/* --------------------------------------------------------------------- */}
      {/* MAIN CONTENT CANVAS */}
      {/* --------------------------------------------------------------------- */}
      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* Top Header Bar */}
        <header className="h-16 px-6 bg-white border-b border-slate-200 flex items-center justify-between flex-shrink-0 sticky top-0 z-10 shadow-xs">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-bold text-slate-900 tracking-tight">
              {activeTab === 'dashboard' && 'Operations Executive Dashboard'}
              {activeTab === 'deliverables' && 'Deliverables & Sprint Tasks'}
              {activeTab === 'projects' && 'Active Sprint Projects'}
              {activeTab === 'team' && 'Team Capacity & Workload Orchestration'}
              {activeTab === 'compliance' && 'Compliance Documents & Governance'}
            </h1>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 font-medium">
              {tenantId === 'tenant-001' ? 'Apex Operations Solutions Inc. | US-DEL-984210' : 'BluePeak Global Operations | UK-LON-440182'}
            </span>
            {userRole !== 'OPERATIONS_DIRECTOR' && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 flex items-center gap-1">
                <Shield className="w-3 h-3 text-sky-600" />
                <span>Role: {userRole}</span>
              </span>
            )}
            {!isLoggedIn && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-200">
                Read-Only Mode
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={fetchData}
              disabled={loading}
              className="p-2 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors"
              title="Refresh Data from PostgreSQL"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>

            {activeTab === 'deliverables' && isLoggedIn && userRole !== 'COMPLIANCE_AUDITOR' && (
              <button
                onClick={() => setShowAddDeliverableModal(true)}
                className="px-3.5 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg text-xs font-semibold shadow-xs flex items-center gap-1.5 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>New Deliverable</span>
              </button>
            )}

            {activeTab === 'projects' && isLoggedIn && (userRole === 'OPERATIONS_DIRECTOR' || userRole === 'PROJECT_MANAGER') && (
              <button
                onClick={() => setShowAddProjectModal(true)}
                className="px-3.5 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg text-xs font-semibold shadow-xs flex items-center gap-1.5 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>New Project</span>
              </button>
            )}

            {activeTab === 'team' && isLoggedIn && userRole === 'OPERATIONS_DIRECTOR' && (
              <button
                onClick={() => setShowAddTeamModal(true)}
                className="px-3.5 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg text-xs font-semibold shadow-xs flex items-center gap-1.5 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Member</span>
              </button>
            )}

            {activeTab === 'compliance' && isLoggedIn && (userRole === 'OPERATIONS_DIRECTOR' || userRole === 'COMPLIANCE_AUDITOR') && (
              <button
                onClick={() => setShowAddComplianceModal(true)}
                className="px-3.5 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg text-xs font-semibold shadow-xs flex items-center gap-1.5 transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Register Standard</span>
              </button>
            )}

            <button
              onClick={() => setCopilotOpen(!copilotOpen)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border flex items-center gap-1.5 transition-colors ${
                copilotOpen
                  ? 'bg-sky-50 text-sky-700 border-sky-200'
                  : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
              }`}
            >
              <Bot className="w-3.5 h-3.5 text-sky-600" />
              <span>AI Copilot</span>
            </button>
          </div>
        </header>

        {/* View Content */}
        <div className="p-6 space-y-6">
          {/* ----------------------------------------------------------------- */}
          {/* TAB 1: EXECUTIVE DASHBOARD */}
          {/* ----------------------------------------------------------------- */}
          {activeTab === 'dashboard' && summary && (
            <div className="space-y-6">
              {/* Top 4 KPI Metric Cards */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-white p-5 rounded-xl border border-slate-200/90 shadow-xs">
                  <div className="flex items-center justify-between text-slate-600 mb-2">
                    <span className="text-xs font-medium uppercase tracking-wider">Overdue SLA Deliverables</span>
                    <AlertTriangle className="w-4 h-4 text-rose-500" />
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-2xl font-bold text-rose-600">{summary.overdue_tasks_count}</span>
                    <span className="text-xs text-rose-600 font-semibold">({summary.critical_overdue_count} Critical)</span>
                  </div>
                  <p className="text-[11px] text-slate-600 mt-1">Requiring immediate executive intervention</p>
                </div>

                <div className="bg-white p-5 rounded-xl border border-slate-200/90 shadow-xs">
                  <div className="flex items-center justify-between text-slate-600 mb-2">
                    <span className="text-xs font-medium uppercase tracking-wider">Active Sprint Projects</span>
                    <Briefcase className="w-4 h-4 text-sky-600" />
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-2xl font-bold text-slate-900">{summary.active_projects_count}</span>
                    <span className="text-xs text-emerald-600 font-medium">Sprint 24-Q4</span>
                  </div>
                  <p className="text-[11px] text-slate-600 mt-1">ISO 27001, ERP Migration in flight</p>
                </div>

                <div className="bg-white p-5 rounded-xl border border-slate-200/90 shadow-xs">
                  <div className="flex items-center justify-between text-slate-600 mb-2">
                    <span className="text-xs font-medium uppercase tracking-wider">Overburdened Staff</span>
                    <Users className="w-4 h-4 text-amber-500" />
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-2xl font-bold text-amber-600">{summary.overburdened_staff_count}</span>
                    <span className="text-xs text-amber-600 font-semibold">&gt; 100% capacity</span>
                  </div>
                  <p className="text-[11px] text-slate-600 mt-1">Threshold exceeded (Devon Cooper: 5/4 tasks)</p>
                </div>

                <div className="bg-white p-5 rounded-xl border border-slate-200/90 shadow-xs">
                  <div className="flex items-center justify-between text-slate-600 mb-2">
                    <span className="text-xs font-medium uppercase tracking-wider">Audited Governance Docs</span>
                    <ShieldCheck className="w-4 h-4 text-emerald-600" />
                  </div>
                  <div className="flex items-baseline gap-2">
                    <span className="text-2xl font-bold text-emerald-700">{summary.compliance_audited_count}</span>
                    <span className="text-xs text-emerald-600 font-medium">100% Clean Audit</span>
                  </div>
                  <p className="text-[11px] text-slate-600 mt-1">ISO 27001, SOC 2, GDPR verified</p>
                </div>
              </div>

              {/* SLA Escalation Alert Banner */}
              <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-rose-100 text-rose-700 rounded-lg">
                    <AlertOctagon className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-rose-900">
                      SLA Escalation Alert: {summary.sla_escalation_status}
                    </h3>
                    <p className="text-xs text-rose-700 mt-0.5">
                      Third-party pen-test validation sign-off is 5 days past SLA due date with ISO 27001 recertification deadline approaching.
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setActiveTab('deliverables')}
                  className="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-semibold transition-colors"
                >
                  Inspect Deliverables
                </button>
              </div>

              {/* Two Column Layout: Team Capacity vs Urgent Deliverables */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Team Capacity Progress Bars */}
                <div className="bg-white p-5 rounded-xl border border-slate-200/90 shadow-xs space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                    <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                      <Users className="w-4 h-4 text-sky-600" />
                      <span>Team Capacity Load Balancing</span>
                    </h3>
                    <button
                      onClick={() => setActiveTab('team')}
                      className="text-xs text-sky-600 hover:text-sky-700 font-semibold"
                    >
                      View All Members
                    </button>
                  </div>

                  <div className="space-y-3.5">
                    {team.map((m) => {
                      const ratio = Math.round((m.active_tasks_count / m.max_task_threshold) * 100);
                      const isOver = m.active_tasks_count > m.max_task_threshold;
                      return (
                        <div key={m.id} className="space-y-1">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-semibold text-slate-900">{m.name}</span>
                            <div className="flex items-center gap-2">
                              <span className="text-slate-600">
                                {m.active_tasks_count} / {m.max_task_threshold} tasks
                              </span>
                              <span
                                className={`px-1.5 py-0.2 rounded font-bold text-[10px] ${
                                  isOver ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'
                                }`}
                              >
                                {ratio}%
                              </span>
                            </div>
                          </div>
                          <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${
                                isOver ? 'bg-rose-500' : ratio >= 80 ? 'bg-amber-500' : 'bg-emerald-500'
                              }`}
                              style={{ width: `${Math.min(ratio, 100)}%` }}
                            ></div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Overdue Deliverables Snapshot */}
                <div className="bg-white p-5 rounded-xl border border-slate-200/90 shadow-xs space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                    <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                      <Clock className="w-4 h-4 text-rose-500" />
                      <span>Overdue Deliverables Queue</span>
                    </h3>
                    <span className="text-xs text-rose-600 font-bold bg-rose-50 px-2 py-0.5 rounded-full border border-rose-200">
                      {deliverables.filter((d) => d.status === 'OVERDUE').length} Overdue
                    </span>
                  </div>

                  <div className="divide-y divide-slate-100">
                    {deliverables
                      .filter((d) => d.status === 'OVERDUE')
                      .slice(0, 4)
                      .map((d) => (
                        <div key={d.id} className="py-2.5 flex items-center justify-between text-xs">
                          <div className="space-y-0.5 max-w-[280px]">
                            <p className="font-semibold text-slate-900 truncate">{d.title}</p>
                            <p className="text-[11px] text-slate-600 truncate">
                              Assignee: {d.assignee_name || 'Unassigned'} | Due {d.due_date}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-700 border border-rose-200">
                              +{d.sla_days_overdue}d SLA
                            </span>
                            <button
                              onClick={() => handleToggleDeliverableStatus(d)}
                              className="px-2 py-1 bg-slate-100 hover:bg-emerald-50 hover:text-emerald-700 rounded text-[11px] font-medium transition-colors"
                            >
                              Complete
                            </button>
                          </div>
                        </div>
                      ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ----------------------------------------------------------------- */}
          {/* TAB 2: DELIVERABLES & TASKS (FULL CRUD) */}
          {/* ----------------------------------------------------------------- */}
          {activeTab === 'deliverables' && (
            <div className="bg-white rounded-xl border border-slate-200/90 shadow-xs overflow-hidden">
              {/* Filter & Search Bar */}
              <div className="p-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <Search className="w-4 h-4 text-slate-600 absolute left-3 top-2.5" />
                    <input
                      type="text"
                      placeholder="Search deliverables, projects..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg w-64 focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800 placeholder-slate-600"
                    />
                  </div>

                  <div className="flex items-center gap-1 bg-slate-50 p-1 rounded-lg border border-slate-200 text-xs">
                    {(['ALL', 'OVERDUE', 'IN_PROGRESS', 'COMPLETED'] as const).map((status) => (
                      <button
                        key={status}
                        onClick={() => setDeliverableFilter(status)}
                        className={`px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
                          deliverableFilter === status ? 'bg-white text-sky-700 shadow-xs' : 'text-slate-600 hover:text-slate-900'
                        }`}
                      >
                        {status}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="text-xs text-slate-600 font-medium">
                  Showing {filteredDeliverables.length} of {deliverables.length} items
                </div>
              </div>

              {/* Deliverables Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50/75 border-b border-slate-200/80 text-slate-600 uppercase font-bold tracking-wider text-[10px]">
                    <tr>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Deliverable Title</th>
                      <th className="px-4 py-3">Sprint Project</th>
                      <th className="px-4 py-3">Assignee</th>
                      <th className="px-4 py-3">Priority</th>
                      <th className="px-4 py-3">Due Date</th>
                      <th className="px-4 py-3">SLA Variance</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredDeliverables.map((d) => (
                      <tr key={d.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="px-4 py-3">
                          <button
                            onClick={() => handleToggleDeliverableStatus(d)}
                            className="flex items-center gap-1.5"
                          >
                            {d.status === 'COMPLETED' ? (
                              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                            ) : (
                              <div className="w-4 h-4 rounded-full border-2 border-slate-300 hover:border-sky-500"></div>
                            )}
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                d.status === 'OVERDUE'
                                  ? 'bg-rose-100 text-rose-700 border border-rose-200'
                                  : d.status === 'COMPLETED'
                                  ? 'bg-emerald-100 text-emerald-700 border border-emerald-200'
                                  : 'bg-blue-100 text-blue-700 border border-blue-200'
                              }`}
                            >
                              {d.status}
                            </span>
                          </button>
                        </td>
                        <td className="px-4 py-3 font-semibold text-slate-900 max-w-[260px] truncate">
                          {d.title}
                        </td>
                        <td className="px-4 py-3 text-slate-600 font-medium">
                          {d.project_name || 'General Sprint'}
                        </td>
                        <td className="px-4 py-3 text-slate-700">
                          <div className="flex items-center gap-1.5">
                            <UserCheck className="w-3.5 h-3.5 text-slate-600" />
                            <span>{d.assignee_name || 'Unassigned'}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              d.priority === 'CRITICAL'
                                ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                : d.priority === 'HIGH'
                                ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                : 'bg-slate-100 text-slate-700 border border-slate-200'
                            }`}
                          >
                            {d.priority}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-600 font-mono text-[11px]">{d.due_date}</td>
                        <td className="px-4 py-3">
                          {d.sla_days_overdue > 0 ? (
                            <span className="text-rose-600 font-bold">+{d.sla_days_overdue}d Breached</span>
                          ) : (
                            <span className="text-emerald-600 font-medium">On Schedule</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => handleDeleteDeliverable(d.id)}
                            className="p-1 text-slate-600 hover:text-rose-600 rounded transition-colors"
                            title="Delete Deliverable"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ----------------------------------------------------------------- */}
          {/* TAB 3: SPRINT PROJECTS (FULL CRUD) */}
          {/* ----------------------------------------------------------------- */}
          {activeTab === 'projects' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              {projects.map((p) => {
                const projectDeliverables = deliverables.filter((d) => d.project_id === p.id);
                const completed = projectDeliverables.filter((d) => d.status === 'COMPLETED').length;
                const overdue = projectDeliverables.filter((d) => d.status === 'OVERDUE').length;
                const progressPct = projectDeliverables.length > 0 ? Math.round((completed / projectDeliverables.length) * 100) : 0;

                return (
                  <div key={p.id} className="bg-white p-5 rounded-xl border border-slate-200/90 shadow-xs flex flex-col justify-between space-y-4">
                    <div>
                      <div className="flex items-start justify-between">
                        <div className="space-y-1">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-sky-50 text-sky-700 border border-sky-200">
                            {p.code}
                          </span>
                          <h3 className="font-bold text-slate-900 text-sm mt-1">{p.name}</h3>
                        </div>
                        <button
                          onClick={() => handleDeleteProject(p.id)}
                          className="text-slate-600 hover:text-rose-600 p-1 rounded"
                          title="Archive Project"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      <div className="mt-4 space-y-2 text-xs text-slate-600">
                        <div className="flex justify-between">
                          <span>Sprint Cycle:</span>
                          <span className="font-semibold text-slate-800">{p.sprint_cycle}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Target Date:</span>
                          <span className="font-mono text-slate-800">{p.target_date}</span>
                        </div>
                        <div className="flex justify-between">
                          <span>Overdue Tasks:</span>
                          <span className={overdue > 0 ? 'text-rose-600 font-bold' : 'text-emerald-600 font-medium'}>
                            {overdue}
                          </span>
                        </div>
                      </div>

                      <div className="mt-4 space-y-1">
                        <div className="flex justify-between text-[11px]">
                          <span className="text-slate-600">Sprint Completion</span>
                          <span className="font-bold text-slate-900">{progressPct}%</span>
                        </div>
                        <div className="w-full bg-slate-100 rounded-full h-2">
                          <div
                            className="bg-sky-600 h-2 rounded-full transition-all"
                            style={{ width: `${progressPct}%` }}
                          ></div>
                        </div>
                      </div>
                    </div>

                    <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-600">
                      <span>{projectDeliverables.length} Deliverables linked</span>
                      <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 font-semibold border border-emerald-200">
                        {p.status}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* ----------------------------------------------------------------- */}
          {/* TAB 4: TEAM WORKLOAD & CAPACITY (FULL CRUD) */}
          {/* ----------------------------------------------------------------- */}
          {activeTab === 'team' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {team.map((m) => {
                const ratio = Math.round((m.active_tasks_count / m.max_task_threshold) * 100);
                const isOver = m.active_tasks_count > m.max_task_threshold;
                const assignedDeliverables = deliverables.filter((d) => d.assignee_id === m.id);

                return (
                  <div key={m.id} className="bg-white p-5 rounded-xl border border-slate-200/90 shadow-xs space-y-4">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center font-bold text-slate-700 border border-slate-200">
                          {m.name.charAt(0)}
                        </div>
                        <div>
                          <h3 className="font-bold text-slate-900 text-sm">{m.name}</h3>
                          <p className="text-xs text-slate-600">{m.role}</p>
                          {m.email && <p className="text-[11px] text-slate-600">{m.email}</p>}
                        </div>
                      </div>

                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                          isOver
                            ? 'bg-rose-100 text-rose-700 border-rose-200'
                            : ratio >= 80
                            ? 'bg-amber-100 text-amber-700 border-amber-200'
                            : 'bg-emerald-100 text-emerald-700 border-emerald-200'
                        }`}
                      >
                        {isOver ? 'OVERLOADED (>100%)' : ratio >= 80 ? 'AT CAPACITY' : 'OPTIMAL LOAD'}
                      </span>
                    </div>

                    <div className="space-y-1.5">
                      <div className="flex justify-between text-xs">
                        <span className="text-slate-600">Task Allocation vs Threshold</span>
                        <span className="font-bold text-slate-900">
                          {m.active_tasks_count} of {m.max_task_threshold} max ({ratio}%)
                        </span>
                      </div>
                      <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${
                            isOver ? 'bg-rose-500' : ratio >= 80 ? 'bg-amber-500' : 'bg-emerald-500'
                          }`}
                          style={{ width: `${Math.min(ratio, 100)}%` }}
                        ></div>
                      </div>
                    </div>

                    <div className="pt-3 border-t border-slate-100">
                      <span className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider block mb-2">
                        Assigned Active Deliverables ({assignedDeliverables.length})
                      </span>
                      <div className="space-y-1.5">
                        {assignedDeliverables.slice(0, 3).map((d) => (
                          <div key={d.id} className="text-xs flex items-center justify-between text-slate-700 bg-slate-50 p-2 rounded border border-slate-200/60">
                            <span className="truncate max-w-[280px] font-medium">{d.title}</span>
                            <span className={d.status === 'OVERDUE' ? 'text-rose-600 font-bold' : 'text-slate-600'}>
                              {d.status}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* ----------------------------------------------------------------- */}
          {/* TAB 5: COMPLIANCE & AUDITS (FULL CRUD) */}
          {/* ----------------------------------------------------------------- */}
          {activeTab === 'compliance' && (
            <div className="bg-white rounded-xl border border-slate-200/90 shadow-xs overflow-hidden">
              <div className="p-4 border-b border-slate-100 flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-slate-900 text-sm">Regulatory Compliance Register</h3>
                  <p className="text-xs text-slate-600">18 Audited baseline standards with zero active non-conformities</p>
                </div>
                <span className="px-2.5 py-1 rounded bg-emerald-50 text-emerald-700 font-semibold text-xs border border-emerald-200">
                  Audit Standard: Current (Q4 2026)
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50/75 border-b border-slate-200/80 text-slate-600 uppercase font-bold tracking-wider text-[10px]">
                    <tr>
                      <th className="px-4 py-3">Control Standard</th>
                      <th className="px-4 py-3">Document Title</th>
                      <th className="px-4 py-3">Verification Status</th>
                      <th className="px-4 py-3">Audit Date</th>
                      <th className="px-4 py-3">Auditor / Entity</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {complianceDocs.map((doc) => (
                      <tr key={doc.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="px-4 py-3 font-semibold text-sky-700">{doc.standard}</td>
                        <td className="px-4 py-3 font-medium text-slate-900">{doc.title}</td>
                        <td className="px-4 py-3">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-700 border border-emerald-200">
                            {doc.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono text-[11px] text-slate-600">{doc.audit_date}</td>
                        <td className="px-4 py-3 text-slate-600">{doc.auditor_name}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* --------------------------------------------------------------------- */}
      {/* RIGHT AI COPILOT DRAWER (~410px) */}
      {/* --------------------------------------------------------------------- */}
      {copilotOpen && (
        <aside className="w-[410px] flex-shrink-0 bg-white border-l border-slate-200 flex flex-col justify-between shadow-xs z-20">
          <div>
            {/* Header */}
            <div className="p-4 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-sky-50 text-sky-600 flex items-center justify-center border border-sky-200">
                  <Bot className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-xs font-bold text-slate-900">OnScribe Operations Intelligence</h3>
                  <p className="text-[10px] text-slate-600">Synced with live PostgreSQL</p>
                </div>
              </div>
              <button
                onClick={() => setCopilotOpen(false)}
                className="text-slate-600 hover:text-slate-900 p-1 rounded"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Suggestion Chips */}
            <div className="p-3 border-b border-slate-100 bg-slate-50/60 space-y-1.5">
              <span className="text-[10px] uppercase font-bold text-slate-600 tracking-wider block">
                Direct PostgreSQL Tool Queries
              </span>
              <div className="flex flex-wrap gap-1.5">
                <button
                  onClick={() => executeCopilotTool('List critical overdue tasks')}
                  className="text-[11px] px-2.5 py-1 bg-white hover:bg-sky-50 hover:text-sky-700 text-slate-700 rounded-lg border border-slate-200 transition-colors font-medium shadow-2xs"
                >
                  ⚡ List critical overdue tasks
                </button>
                <button
                  onClick={() => executeCopilotTool('Analyze overloaded staff')}
                  className="text-[11px] px-2.5 py-1 bg-white hover:bg-sky-50 hover:text-sky-700 text-slate-700 rounded-lg border border-slate-200 transition-colors font-medium shadow-2xs"
                >
                  👥 Analyze overloaded staff
                </button>
                <button
                  onClick={() => executeCopilotTool('Summarize operations SLA')}
                  className="text-[11px] px-2.5 py-1 bg-white hover:bg-sky-50 hover:text-sky-700 text-slate-700 rounded-lg border border-slate-200 transition-colors font-medium shadow-2xs"
                >
                  📊 Summarize operations SLA
                </button>
              </div>
            </div>

            {/* Execution History Feed */}
            <div className="p-3 space-y-3 max-h-[calc(100vh-250px)] overflow-y-auto">
              {copilotHistory.map((exec, idx) => (
                <div key={idx} className="bg-slate-50 rounded-lg p-3 border border-slate-200 text-xs space-y-2">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="font-semibold text-slate-800 truncate max-w-[240px]">&ldquo;{exec.query}&rdquo;</span>
                    <span className="font-mono text-emerald-600 text-[10px]">{exec.latencyMs}ms</span>
                  </div>

                  <div className="flex items-center gap-1.5 text-[10px] font-mono text-slate-600">
                    <Terminal className="w-3 h-3 text-sky-600" />
                    <span>{exec.tool}</span>
                  </div>

                  <p className="text-slate-700 text-[11px] font-medium leading-relaxed">{exec.resultSummary}</p>

                  {exec.jsonTrace && (
                    <div className="pt-1">
                      <button
                        onClick={() => setExpandedTraceIndex(expandedTraceIndex === idx ? null : idx)}
                        className="text-[10px] text-sky-600 hover:underline flex items-center gap-1 font-semibold"
                      >
                        {expandedTraceIndex === idx ? 'Hide JSON Trace' : 'View SQL JSON Trace'}
                        <ChevronRight className={`w-3 h-3 transition-transform ${expandedTraceIndex === idx ? 'rotate-90' : ''}`} />
                      </button>
                      {expandedTraceIndex === idx && (
                        <pre className="mt-2 p-2 bg-slate-900 text-slate-100 rounded text-[10px] font-mono overflow-x-auto max-h-40">
                          {JSON.stringify(exec.jsonTrace, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Input Bar */}
          <div className="p-3 border-t border-slate-100">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (copilotInput.trim()) executeCopilotTool(copilotInput);
              }}
              className="flex items-center gap-1.5"
            >
              <input
                type="text"
                placeholder="Ask operations intelligence..."
                value={copilotInput}
                onChange={(e) => setCopilotInput(e.target.value)}
                disabled={isCopilotExecuting}
                className="flex-1 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800 placeholder-slate-600"
              />
              <button
                type="submit"
                disabled={isCopilotExecuting || !copilotInput.trim()}
                className="p-2 bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white rounded-lg transition-colors"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </form>
          </div>
        </aside>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* MODAL: ADD DELIVERABLE */}
      {/* --------------------------------------------------------------------- */}
      {showAddDeliverableModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-bold text-slate-900 text-sm">Add New Sprint Deliverable</h3>
              <button onClick={() => setShowAddDeliverableModal(false)} className="text-slate-600 hover:text-slate-800">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateDeliverable} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-semibold mb-1">Deliverable Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Conduct ISO 27001 Access Control Review"
                  value={newDeliverable.title}
                  onChange={(e) => setNewDeliverable({ ...newDeliverable, title: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Sprint Project</label>
                  <select
                    value={newDeliverable.project_id}
                    onChange={(e) => setNewDeliverable({ ...newDeliverable, project_id: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                  >
                    <option value="">Select Project...</option>
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Assignee</label>
                  <select
                    value={newDeliverable.assignee_id}
                    onChange={(e) => setNewDeliverable({ ...newDeliverable, assignee_id: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                  >
                    <option value="">Select Member...</option>
                    {team.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Priority</label>
                  <select
                    value={newDeliverable.priority}
                    onChange={(e) => setNewDeliverable({ ...newDeliverable, priority: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                  >
                    <option value="CRITICAL">CRITICAL</option>
                    <option value="HIGH">HIGH</option>
                    <option value="MEDIUM">MEDIUM</option>
                    <option value="LOW">LOW</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Due Date</label>
                  <input
                    type="date"
                    value={newDeliverable.due_date}
                    onChange={(e) => setNewDeliverable({ ...newDeliverable, due_date: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                  />
                </div>
              </div>

              <div className="pt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowAddDeliverableModal(false)}
                  className="px-3.5 py-1.5 border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Create Deliverable
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* MODAL: ADD PROJECT */}
      {/* --------------------------------------------------------------------- */}
      {showAddProjectModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-bold text-slate-900 text-sm">Register New Sprint Project</h3>
              <button onClick={() => setShowAddProjectModal(false)} className="text-slate-600 hover:text-slate-800">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateProject} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-semibold mb-1">Project Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. SOC 2 Type II Surveillance Audit"
                  value={newProject.name}
                  onChange={(e) => setNewProject({ ...newProject, name: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Project Code</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. SOC2-SURV"
                    value={newProject.code}
                    onChange={(e) => setNewProject({ ...newProject, code: e.target.value.toUpperCase() })}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Sprint Cycle</label>
                  <input
                    type="text"
                    value={newProject.sprint_cycle}
                    onChange={(e) => setNewProject({ ...newProject, sprint_cycle: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">Target Date</label>
                <input
                  type="date"
                  value={newProject.target_date}
                  onChange={(e) => setNewProject({ ...newProject, target_date: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                />
              </div>

              <div className="pt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowAddProjectModal(false)}
                  className="px-3.5 py-1.5 border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Register Project
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* MODAL: ADD TEAM MEMBER */}
      {/* --------------------------------------------------------------------- */}
      {showAddTeamModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-bold text-slate-900 text-sm">Onboard Operations Team Member</h3>
              <button onClick={() => setShowAddTeamModal(false)} className="text-slate-600 hover:text-slate-800">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateTeamMember} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-semibold mb-1">Member Full Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Zachary Miller"
                  value={newTeamMember.name}
                  onChange={(e) => setNewTeamMember({ ...newTeamMember, name: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                />
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">Role & Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Security Compliance Auditor"
                  value={newTeamMember.role}
                  onChange={(e) => setNewTeamMember({ ...newTeamMember, role: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Internal Email</label>
                  <input
                    type="email"
                    placeholder="zachary@apexops.internal"
                    value={newTeamMember.email}
                    onChange={(e) => setNewTeamMember({ ...newTeamMember, email: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                  />
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Max Task Threshold</label>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    value={newTeamMember.max_task_threshold}
                    onChange={(e) => setNewTeamMember({ ...newTeamMember, max_task_threshold: parseInt(e.target.value) || 4 })}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                  />
                </div>
              </div>

              <div className="pt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowAddTeamModal(false)}
                  className="px-3.5 py-1.5 border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Onboard Member
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* MODAL: ADD COMPLIANCE STANDARD */}
      {/* --------------------------------------------------------------------- */}
      {showAddComplianceModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-bold text-slate-900 text-sm">Register Compliance Standard</h3>
              <button onClick={() => setShowAddComplianceModal(false)} className="text-slate-600 hover:text-slate-800">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateCompliance} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 font-semibold mb-1">Document Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Cloud Disaster Recovery Annual Attestation"
                  value={newCompliance.title}
                  onChange={(e) => setNewCompliance({ ...newCompliance, title: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Standard Framework</label>
                  <select
                    value={newCompliance.standard}
                    onChange={(e) => setNewCompliance({ ...newCompliance, standard: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                  >
                    <option value="ISO 27001">ISO 27001</option>
                    <option value="SOC 2">SOC 2</option>
                    <option value="Vendor Risk">Vendor Risk</option>
                    <option value="GDPR">GDPR</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-700 font-semibold mb-1">Verification Status</label>
                  <select
                    value={newCompliance.status}
                    onChange={(e) => setNewCompliance({ ...newCompliance, status: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                  >
                    <option value="AUDITED">AUDITED</option>
                    <option value="IN_REVIEW">IN_REVIEW</option>
                    <option value="NON_CONFORMANT">NON_CONFORMANT</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-slate-700 font-semibold mb-1">Auditor Entity</label>
                <input
                  type="text"
                  value={newCompliance.auditor_name}
                  onChange={(e) => setNewCompliance({ ...newCompliance, auditor_name: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-sky-500 text-slate-800"
                />
              </div>

              <div className="pt-3 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowAddComplianceModal(false)}
                  className="px-3.5 py-1.5 border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Register Document
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 5: AUTHENTICATION / PROFILE SWITCHER */}
      {showAuthModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-lg w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3.5 border-b border-slate-100">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-sky-100 text-sky-700 flex items-center justify-center font-bold">
                  <ShieldCheck className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900">Switch Company & User Role</h3>
                  <p className="text-[11px] text-slate-500">Operations & Compliance Multi-Tenant Partitioning</p>
                </div>
              </div>
              <button
                onClick={() => setShowAuthModal(false)}
                className="text-slate-400 hover:text-slate-600 rounded-lg p-1 hover:bg-slate-100 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="mt-4 space-y-4 text-xs">
              {/* Manual Dropdowns */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Company / Tenant</label>
                  <select
                    value={modalTenant}
                    onChange={(e) => setModalTenant(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-medium text-slate-800 focus:bg-white focus:outline-none focus:border-sky-600"
                  >
                    <option value="tenant-001">Vanguard Enterprise (tenant-001)</option>
                    <option value="tenant-002">BluePeak Global (tenant-002)</option>
                  </select>
                </div>

                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Assigned Role</label>
                  <select
                    value={modalRole}
                    onChange={(e) => setModalRole(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-medium text-slate-800 focus:bg-white focus:outline-none focus:border-sky-600"
                  >
                    <option value="OPERATIONS_DIRECTOR">Operations Director (Admin)</option>
                    <option value="PROJECT_MANAGER">Project Manager (Manager)</option>
                    <option value="TEAM_CONTRIBUTOR">Team Contributor (Staff)</option>
                    <option value="COMPLIANCE_AUDITOR">Compliance Auditor (Auditor)</option>
                  </select>
                </div>
              </div>

              {/* Demo Quick-Select Profiles */}
              <div>
                <label className="font-semibold text-slate-700 block mb-1.5">
                  Demo Quick-Select Profiles (Company A vs Company B)
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {DEMO_PROFILES.map((p) => {
                    const isSelected = tenantId === p.tenantId && userRole === p.userRole && isLoggedIn;
                    return (
                      <button
                        key={`${p.tenantId}-${p.userRole}`}
                        type="button"
                        onClick={() => {
                          setModalTenant(p.tenantId);
                          setModalRole(p.userRole);
                          handleSwitchSession(p.tenantId, p.userRole);
                        }}
                        className={`text-left p-2.5 rounded-xl border transition-all ${
                          isSelected
                            ? 'bg-sky-50 border-sky-400 ring-2 ring-sky-500/20'
                            : 'bg-slate-50/70 border-slate-200 hover:bg-slate-100 hover:border-slate-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-slate-900 text-xs truncate">{p.userName}</span>
                          <span className="text-[9px] px-1 py-0.2 rounded font-mono bg-slate-200/80 text-slate-700">
                            {p.tenantId}
                          </span>
                        </div>
                        <p className="text-[10px] text-sky-700 font-semibold mt-0.5">{p.roleLabel}</p>
                        <p className="text-[10px] text-slate-500 truncate mt-0.5">{p.tenantName}</p>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Modal Footer */}
              <div className="pt-3 flex items-center justify-between border-t border-slate-100">
                <span className="text-[11px] text-slate-500">
                  Active: <strong className="text-slate-800">{tenantId}</strong> • {userRole}
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setShowAuthModal(false)}
                    className="px-3.5 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium text-xs transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSwitchSession(modalTenant, modalRole)}
                    className="px-4 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg font-semibold text-xs shadow-xs transition-all"
                  >
                    Apply Session
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
