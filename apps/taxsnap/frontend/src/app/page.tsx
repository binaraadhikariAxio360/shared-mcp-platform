'use client';

import React, { useState, useEffect } from 'react';
import {
  LayoutDashboard,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Receipt,
  FileText,
  Building2,
  ShieldCheck,
  AlertTriangle,
  AlertCircle,
  CheckCircle2,
  Clock,
  Calendar,
  ChevronRight,
  ChevronDown,
  Plus,
  Pencil,
  Trash2,
  Search,
  Filter,
  Sparkles,
  Bot,
  Send,
  RefreshCw,
  X,
  ExternalLink,
  Check,
  Layers,
  PieChart,
  Tag,
  ArrowRight,
  Lock,
  LogOut,
  LogIn,
  Shield,
} from 'lucide-react';

// -----------------------------------------------------------------------------
// Interfaces
// -----------------------------------------------------------------------------
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
    tenantName: 'Vanguard Global Consulting LLC',
    userRole: 'FINANCE_DIRECTOR',
    userId: 'user-dir-001',
    userName: 'Marcus Reynolds',
    roleLabel: 'Finance Director (Admin)',
    description: 'Full CRUD on income, expenses, tax profiles, corporate rate, and filings.',
  },
  {
    tenantId: 'tenant-001',
    tenantName: 'Vanguard Global Consulting LLC',
    userRole: 'SENIOR_CPA',
    userId: 'user-cpa-001',
    userName: 'Elena Rostova, CPA',
    roleLabel: 'Senior CPA (Accountant)',
    description: 'Full CRUD on expenses (write-offs); verify tax docs; read-only profile.',
  },
  {
    tenantId: 'tenant-001',
    tenantName: 'Vanguard Global Consulting LLC',
    userRole: 'BOOKKEEPER',
    userId: 'user-bk-001',
    userName: 'Jason Myers',
    roleLabel: 'Bookkeeper (Data Entry)',
    description: 'Create/edit income & expenses; cannot verify docs or delete records.',
  },
  {
    tenantId: 'tenant-001',
    tenantName: 'Vanguard Global Consulting LLC',
    userRole: 'AUDITOR_STAKEHOLDER',
    userId: 'user-audit-001',
    userName: 'Arthur Pendelton',
    roleLabel: 'Auditor Stakeholder (Viewer)',
    description: 'Read-only across all tabs; cannot create, edit, or delete any records.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'Horizon Capital Partners LLC',
    userRole: 'FINANCE_DIRECTOR',
    userId: 'user-dir-002',
    userName: 'Samantha Cole',
    roleLabel: 'Finance Director (Admin)',
    description: 'Full CRUD for Horizon Capital tax strategy and corporate filings.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'Horizon Capital Partners LLC',
    userRole: 'SENIOR_CPA',
    userId: 'user-cpa-002',
    userName: 'Nathaniel Vance, CPA',
    roleLabel: 'Senior CPA (Accountant)',
    description: 'Audit deductions and verify documentation for Horizon Capital.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'Horizon Capital Partners LLC',
    userRole: 'BOOKKEEPER',
    userId: 'user-bk-002',
    userName: 'Chloe Bennett',
    roleLabel: 'Bookkeeper (Data Entry)',
    description: 'Record new ledger receipts; cannot verify docs or delete entries.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'Horizon Capital Partners LLC',
    userRole: 'AUDITOR_STAKEHOLDER',
    userId: 'user-audit-002',
    userName: 'Victor Zhang',
    roleLabel: 'Auditor Stakeholder (Viewer)',
    description: 'Read-only financial audits and reporting oversight for Horizon Capital.',
  },
];

interface TaxProfile {
  id: string;
  tenant_id: string;
  business_name: string;
  tin_number: string;
  fiscal_year: string;
  corporate_tax_rate: number;
}

interface IncomeRecord {
  id: string;
  profile_id: string;
  tenant_id: string;
  source: string;
  amount: number;
  date: string;
  status: string; // Received, Pending, Invoiced
}

interface ExpenseRecord {
  id: string;
  profile_id: string;
  tenant_id: string;
  vendor: string;
  category: string;
  amount: number;
  is_deductible: boolean;
  date: string;
  receipt_url?: string;
}

interface TaxDocument {
  id: string;
  profile_id: string;
  tenant_id: string;
  document_type: string;
  status: string; // VERIFIED, PENDING_UPLOAD, MISSING, OVERDUE
  deadline: string;
  assigned_cpa?: string;
}

interface DashboardSummary {
  tenant_id: string;
  business_name: string;
  tin_number: string;
  fiscal_year: string;
  gross_income: number;
  total_expenses: number;
  total_deductible_expenses: number;
  non_deductible_expenses: number;
  net_taxable_income: number;
  corporate_tax_rate: number;
  estimated_tax_liability: number;
  missing_documents_count: number;
  overdue_filings_count: number;
  total_documents_count: number;
  income_count: number;
  expense_count: number;
  expense_by_category: Record<string, number>;
}

interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  toolCall?: {
    toolName: string;
    executionTimeMs: number;
    status: 'SUCCESS' | 'ERROR';
    requestPayload: any;
    responsePayload: any;
  };
}

export default function TaxSnapApp() {
  // Multi-Tenant & RBAC Session State
  const [tenantId, setTenantId] = useState('tenant-001');
  const [userRole, setUserRole] = useState('FINANCE_DIRECTOR');
  const [userId, setUserId] = useState('user-dir-001');
  const [userName, setUserName] = useState('Eleanor Sterling');
  const [companyName, setCompanyName] = useState('Vanguard Global Consulting LLC');
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isSessionChecked, setIsSessionChecked] = useState(false);

  // Dedicated SaaS Auth Portal State
  const [authTab, setAuthTab] = useState<'signin' | 'signup'>('signin');
  const [loginEmail, setLoginEmail] = useState('director@vanguardtax.com');
  const [loginPassword, setLoginPassword] = useState('password123');
  const [registerFullName, setRegisterFullName] = useState('');
  const [registerEmail, setRegisterEmail] = useState('');
  const [registerPassword, setRegisterPassword] = useState('');
  const [registerCompany, setRegisterCompany] = useState('');
  const [registerRole, setRegisterRole] = useState('FINANCE_DIRECTOR');
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(false);

  // Profile Switcher Modal State
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [modalTenant, setModalTenant] = useState('tenant-001');
  const [modalRole, setModalRole] = useState('FINANCE_DIRECTOR');

  const apiBase = 'http://localhost:5002';

  // Navigation state
  type TabType = 'dashboard' | 'income' | 'expenses' | 'documents' | 'profile';
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');

  // Core Data
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [profile, setProfile] = useState<TaxProfile | null>(null);
  const [incomes, setIncomes] = useState<IncomeRecord[]>([]);
  const [expenses, setExpenses] = useState<ExpenseRecord[]>([]);
  const [documents, setDocuments] = useState<TaxDocument[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Filters
  const [incomeStatusFilter, setIncomeStatusFilter] = useState('ALL');
  const [expenseCategoryFilter, setExpenseCategoryFilter] = useState('ALL');
  const [documentStatusFilter, setDocumentStatusFilter] = useState('ALL');

  // Modals
  const [showIncomeModal, setShowIncomeModal] = useState(false);
  const [editingIncome, setEditingIncome] = useState<IncomeRecord | null>(null);
  const [incomeForm, setIncomeForm] = useState({
    source: '',
    amount: '',
    date: '2026-10-15',
    status: 'Received',
  });

  const [showExpenseModal, setShowExpenseModal] = useState(false);
  const [editingExpense, setEditingExpense] = useState<ExpenseRecord | null>(null);
  const [expenseForm, setExpenseForm] = useState({
    vendor: '',
    category: 'Cloud Infrastructure',
    amount: '',
    is_deductible: true,
    date: '2026-10-15',
    receipt_url: '',
  });

  const [showDocModal, setShowDocModal] = useState(false);
  const [editingDoc, setEditingDoc] = useState<TaxDocument | null>(null);
  const [docForm, setDocForm] = useState({
    document_type: 'Form 1099-NEC',
    status: 'PENDING_UPLOAD',
    deadline: '2026-11-15',
    assigned_cpa: 'Elena Rostova, CPA',
  });

  const [showProfileModal, setShowProfileModal] = useState(false);
  const [profileForm, setProfileForm] = useState({
    business_name: 'Vanguard Global Consulting LLC',
    tin_number: 'XX-XXX9821',
    fiscal_year: '2026',
    corporate_tax_rate: 0.21,
  });

  // Toast Notification
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'info' } | null>(null);
  const showToast = (text: string, type: 'success' | 'info' = 'success') => {
    setToastMessage({ text, type });
    setTimeout(() => setToastMessage(null), 3200);
  };

  // Dynamic Request Headers Helper
  const getHeaders = (extraHeaders: Record<string, string> = {}) => ({
    'x-tenant-id': tenantId,
    'x-user-role': userRole,
    'x-user-id': userId,
    ...extraHeaders,
  });

  // Copilot State
  const [isCopilotOpen, setIsCopilotOpen] = useState(true);
  const [chatInput, setChatInput] = useState('');
  const [isCallingTool, setIsCallingTool] = useState(false);
  const [securityChipExpanded, setSecurityChipExpanded] = useState(false);
  const [expandedTraceId, setExpandedTraceId] = useState<string | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'msg-init',
      sender: 'assistant',
      text: "Good morning. TaxSnap Intelligence is active and synchronized with PostgreSQL 16. How can I assist with corporate deduction write-offs, estimated liabilities, or missing compliance filings today?",
      timestamp: '09:00 AM',
    },
  ]);

  // Initial Data Fetching with Tenant & Role Isolation
  const fetchDataFor = async (tId: string, uRole: string, uId: string) => {
    setIsLoading(true);
    const headers = { 'x-tenant-id': tId, 'x-user-role': uRole, 'x-user-id': uId };

    try {
      const [sumRes, profRes, incRes, expRes, docRes] = await Promise.all([
        fetch(`${apiBase}/api/v1/dashboard/summary`, { headers }).then((r) => r.json()).catch(() => null),
        fetch(`${apiBase}/api/v1/profile`, { headers }).then((r) => r.json()).catch(() => null),
        fetch(`${apiBase}/api/v1/income`, { headers }).then((r) => r.json()).catch(() => []),
        fetch(`${apiBase}/api/v1/expenses`, { headers }).then((r) => r.json()).catch(() => []),
        fetch(`${apiBase}/api/v1/documents`, { headers }).then((r) => r.json()).catch(() => []),
      ]);

      if (sumRes && !sumRes.detail) setSummary(sumRes);
      if (profRes && !profRes.detail) {
        setProfile(profRes);
        setProfileForm({
          business_name: profRes.business_name,
          tin_number: profRes.tin_number,
          fiscal_year: profRes.fiscal_year,
          corporate_tax_rate: profRes.corporate_tax_rate,
        });
      }
      if (Array.isArray(incRes)) setIncomes(incRes);
      if (Array.isArray(expRes)) setExpenses(expRes);
      if (Array.isArray(docRes)) setDocuments(docRes);
    } catch (e) {
      console.error('Failed to load TaxSnap data:', e);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchData = () => fetchDataFor(tenantId, userRole, userId);

  // Mount Session Restoration
  useEffect(() => {
    try {
      const saved = localStorage.getItem('taxsnap_auth_session');
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
      const res = await fetch(`${apiBase}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: emailToUse, password: passToUse }),
      });
      const data = await res.json();
      if (!res.ok) {
        setAuthError(data.detail || 'Login failed. Please check credentials.');
        showToast(data.detail || 'Login failed', 'info');
      } else {
        localStorage.setItem('taxsnap_auth_session', JSON.stringify({ token: data.access_token, user: data.user }));
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
      const res = await fetch(`${apiBase}/api/v1/auth/register`, {
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
        showToast(data.detail || 'Registration failed', 'info');
      } else {
        localStorage.setItem('taxsnap_auth_session', JSON.stringify({ token: data.access_token, user: data.user }));
        setTenantId(data.user.tenant_id);
        setUserRole(data.user.role);
        setUserId(data.user.id);
        setUserName(data.user.name);
        setCompanyName(data.user.company_name || data.user.tenant_id);
        setIsLoggedIn(true);
        setShowAuthModal(false);
        fetchDataFor(data.user.tenant_id, data.user.role, data.user.id);
        showToast(`Corporate entity created for ${data.user.company_name}!`);
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
      tenantName: targetTenant === 'tenant-001' ? 'Vanguard Global Consulting LLC' : 'Horizon Capital Partners LLC',
      userRole: targetRole,
      userId: `user-${targetRole.toLowerCase()}-${targetTenant}`,
      userName: `User (${targetRole})`,
      roleLabel: targetRole,
      description: '',
    };

    setSummary(null);
    setProfile(null);
    setIncomes([]);
    setExpenses([]);
    setDocuments([]);

    setTenantId(targetTenant);
    setUserRole(targetRole);
    setUserId(profileMatch.userId);
    setUserName(profileMatch.userName);
    setCompanyName(profileMatch.tenantName);
    setIsLoggedIn(true);
    setShowAuthModal(false);

    localStorage.setItem('taxsnap_auth_session', JSON.stringify({
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
    localStorage.removeItem('taxsnap_auth_session');
    setSummary(null);
    setProfile(null);
    setIncomes([]);
    setExpenses([]);
    setDocuments([]);
    setIsLoggedIn(false);
    setUserRole('AUDITOR_STAKEHOLDER');
    setUserName('Guest Auditor');
    setCompanyName('');
    showToast('Signed out of session. Session purged.', 'info');
  };

  // ---------------------------------------------------------------------------
  // Income CRUD Handlers
  // ---------------------------------------------------------------------------
  const handleOpenCreateIncome = () => {
    setEditingIncome(null);
    setIncomeForm({
      source: '',
      amount: '',
      date: '2026-10-15',
      status: 'Received',
    });
    setShowIncomeModal(true);
  };

  const handleOpenEditIncome = (item: IncomeRecord) => {
    setEditingIncome(item);
    setIncomeForm({
      source: item.source,
      amount: item.amount.toString(),
      date: item.date,
      status: item.status,
    });
    setShowIncomeModal(true);
  };

  const handleSaveIncome = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!incomeForm.source || !incomeForm.amount) return;

    const payload = {
      source: incomeForm.source,
      amount: parseFloat(incomeForm.amount),
      date: incomeForm.date,
      status: incomeForm.status,
    };

    try {
      let res;
      if (editingIncome) {
        res = await fetch(`${apiBase}/api/v1/income/${editingIncome.id}`, {
          method: 'PUT',
          headers: getHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
      } else {
        res = await fetch(`${apiBase}/api/v1/income`, {
          method: 'POST',
          headers: getHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || `Action failed (${res.status} Forbidden)`, 'info');
        return;
      }

      showToast(editingIncome ? `Income updated: ${payload.source}` : `New income recorded: $${payload.amount.toLocaleString()}`);
      setShowIncomeModal(false);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteIncome = async (id: string) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/income/${id}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Delete failed (Permission Denied)', 'info');
        return;
      }

      setIncomes((prev) => prev.filter((i) => i.id !== id));
      showToast('Income record removed');
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  // ---------------------------------------------------------------------------
  // Expense CRUD Handlers
  // ---------------------------------------------------------------------------
  const handleOpenCreateExpense = () => {
    setEditingExpense(null);
    setExpenseForm({
      vendor: '',
      category: 'Cloud Infrastructure',
      amount: '',
      is_deductible: true,
      date: '2026-10-15',
      receipt_url: '',
    });
    setShowExpenseModal(true);
  };

  const handleOpenEditExpense = (item: ExpenseRecord) => {
    setEditingExpense(item);
    setExpenseForm({
      vendor: item.vendor,
      category: item.category,
      amount: item.amount.toString(),
      is_deductible: item.is_deductible,
      date: item.date,
      receipt_url: item.receipt_url || '',
    });
    setShowExpenseModal(true);
  };

  const handleSaveExpense = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!expenseForm.vendor || !expenseForm.amount) return;

    const payload = {
      vendor: expenseForm.vendor,
      category: expenseForm.category,
      amount: parseFloat(expenseForm.amount),
      is_deductible: expenseForm.is_deductible,
      date: expenseForm.date,
      receipt_url: expenseForm.receipt_url || null,
    };

    try {
      let res;
      if (editingExpense) {
        res = await fetch(`${apiBase}/api/v1/expenses/${editingExpense.id}`, {
          method: 'PUT',
          headers: getHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
      } else {
        res = await fetch(`${apiBase}/api/v1/expenses`, {
          method: 'POST',
          headers: getHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || `Action failed (${res.status} Forbidden)`, 'info');
        return;
      }

      showToast(editingExpense ? `Expense updated: ${payload.vendor}` : `Expense recorded: $${payload.amount.toLocaleString()}`);
      setShowExpenseModal(false);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleToggleExpenseDeductible = async (item: ExpenseRecord) => {
    const nextVal = !item.is_deductible;
    try {
      const res = await fetch(`${apiBase}/api/v1/expenses/${item.id}`, {
        method: 'PUT',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ is_deductible: nextVal }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission Denied: Cannot modify deductible classification', 'info');
        return;
      }

      setExpenses((prev) =>
        prev.map((e) => (e.id === item.id ? { ...e, is_deductible: nextVal } : e))
      );
      showToast(nextVal ? 'Classified as Deductible Write-Off' : 'Classified as Non-Deductible');
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteExpense = async (id: string) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/expenses/${id}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Delete failed (Permission Denied)', 'info');
        return;
      }

      setExpenses((prev) => prev.filter((e) => e.id !== id));
      showToast('Expense record deleted');
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  // ---------------------------------------------------------------------------
  // Document CRUD Handlers
  // ---------------------------------------------------------------------------
  const handleOpenCreateDoc = () => {
    setEditingDoc(null);
    setDocForm({
      document_type: 'Form 1099-NEC',
      status: 'PENDING_UPLOAD',
      deadline: '2026-11-15',
      assigned_cpa: 'Elena Rostova, CPA',
    });
    setShowDocModal(true);
  };

  const handleOpenEditDoc = (item: TaxDocument) => {
    setEditingDoc(item);
    setDocForm({
      document_type: item.document_type,
      status: item.status,
      deadline: item.deadline,
      assigned_cpa: item.assigned_cpa || 'Elena Rostova, CPA',
    });
    setShowDocModal(true);
  };

  const handleSaveDoc = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload = {
      document_type: docForm.document_type,
      status: docForm.status,
      deadline: docForm.deadline,
      assigned_cpa: docForm.assigned_cpa,
    };

    try {
      let res;
      if (editingDoc) {
        res = await fetch(`${apiBase}/api/v1/documents/${editingDoc.id}`, {
          method: 'PUT',
          headers: getHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
      } else {
        res = await fetch(`${apiBase}/api/v1/documents`, {
          method: 'POST',
          headers: getHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || `Action failed (${res.status} Forbidden)`, 'info');
        return;
      }

      showToast(editingDoc ? `Document updated: ${payload.document_type}` : `Compliance document registered`);
      setShowDocModal(false);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleQuickVerifyDoc = async (item: TaxDocument) => {
    const nextStatus = item.status === 'VERIFIED' ? 'PENDING_UPLOAD' : 'VERIFIED';
    try {
      const res = await fetch(`${apiBase}/api/v1/documents/${item.id}`, {
        method: 'PUT',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ status: nextStatus }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission Denied: Cannot audit tax document', 'info');
        return;
      }

      setDocuments((prev) =>
        prev.map((d) => (d.id === item.id ? { ...d, status: nextStatus } : d))
      );
      showToast(nextStatus === 'VERIFIED' ? 'Document verified by CPA' : 'Status moved to Pending');
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteDoc = async (id: string) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/documents/${id}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Delete failed (Permission Denied)', 'info');
        return;
      }

      setDocuments((prev) => prev.filter((d) => d.id !== id));
      showToast('Document record deleted');
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  // ---------------------------------------------------------------------------
  // Profile Update
  // ---------------------------------------------------------------------------
  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${apiBase}/api/v1/profile`, {
        method: 'PUT',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(profileForm),
      });
      if (res.ok) {
        const updated = await res.json();
        setProfile(updated);
        showToast('Corporate tax profile updated');
        setShowProfileModal(false);
        fetchData();
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission Denied: Cannot update tax profile', 'info');
      }
    } catch (err) {
      console.error(err);
    }
  };

  // ---------------------------------------------------------------------------
  // AI Copilot Execution
  // ---------------------------------------------------------------------------
  const handleTriggerTool = async (toolName: string, promptText: string, payload: any = {}) => {
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text: promptText,
      timestamp: '10:00 AM',
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsCallingTool(true);

    const startTime = performance.now();
    try {
      const res = await fetch(`${apiBase}/internal/tools/${toolName}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-tenant-id': tenantId,
          'x-user-id': userId,
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      const durationMs = Math.round(performance.now() - startTime);

      let reply = '';
      if (toolName === 'taxsnap.get_tax_summary') {
        reply = `Analysis Complete: Vanguard Global Consulting has generated $${data.gross_income.toLocaleString()} gross revenue with $${data.deductible_expenses.toLocaleString()} in deductible write-offs. Net taxable income is $${data.net_taxable_income.toLocaleString()}, producing an estimated federal corporate tax liability of $${data.estimated_tax_liability.toLocaleString()} (at ${data.tax_rate * 100}%).`;
      } else if (toolName === 'taxsnap.list_expenses') {
        reply = `Retrieved ${data.count} expense records totaling $${data.total_amount.toLocaleString()}. Top write-offs include AWS GPU Compute and WeWork HQ facilities.`;
      } else if (toolName === 'taxsnap.list_missing_documents') {
        reply = `Compliance Audit Alert: ${data.count} filings require immediate attention. Found ${data.missing_documents.filter((d: any) => d.status === 'OVERDUE').length} overdue filing(s) and pending 1099 verification items.`;
      }

      const asstMsg: ChatMessage = {
        id: `asst-${Date.now()}`,
        sender: 'assistant',
        text: reply,
        timestamp: '10:01 AM',
        toolCall: {
          toolName,
          executionTimeMs: durationMs,
          status: 'SUCCESS',
          requestPayload: payload,
          responsePayload: data,
        },
      };
      setMessages((prev) => [...prev, asstMsg]);
    } catch (err: any) {
      const durationMs = Math.round(performance.now() - startTime);
      const errorMsg: ChatMessage = {
        id: `asst-${Date.now()}`,
        sender: 'assistant',
        text: `Error executing ${toolName}: ${err.message}`,
        timestamp: '10:01 AM',
        toolCall: {
          toolName,
          executionTimeMs: durationMs,
          status: 'ERROR',
          requestPayload: payload,
          responsePayload: { error: err.message },
        },
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsCallingTool(false);
    }
  };

  const handleSendChat = (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    const txt = chatInput.trim();
    setChatInput('');

    if (txt.toLowerCase().includes('tax') || txt.toLowerCase().includes('liability') || txt.toLowerCase().includes('summary')) {
      handleTriggerTool('taxsnap.get_tax_summary', txt);
    } else if (txt.toLowerCase().includes('expense') || txt.toLowerCase().includes('deductible') || txt.toLowerCase().includes('write')) {
      handleTriggerTool('taxsnap.list_expenses', txt, { only_deductible: true });
    } else if (txt.toLowerCase().includes('document') || txt.toLowerCase().includes('missing') || txt.toLowerCase().includes('filing')) {
      handleTriggerTool('taxsnap.list_missing_documents', txt);
    } else {
      // General response
      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        sender: 'user',
        text: txt,
        timestamp: '10:05 AM',
      };
      const asstMsg: ChatMessage = {
        id: `asst-${Date.now()}`,
        sender: 'assistant',
        text: `I've analyzed your inquiry regarding "${txt}". You can use the quick chips below to audit corporate tax liability, review deductible expenses, or inspect missing compliance forms.`,
        timestamp: '10:05 AM',
      };
      setMessages((prev) => [...prev, userMsg, asstMsg]);
    }
  };

  // Nav Items
  const navItems = [
    { id: 'dashboard', label: 'Executive Dashboard', icon: LayoutDashboard },
    { id: 'income', label: 'Income Ledger', icon: TrendingUp, badge: incomes.length },
    { id: 'expenses', label: 'Expense Ledger', icon: Receipt, badge: expenses.length },
    { id: 'documents', label: 'Tax Documents & Compliance', icon: FileText, badge: summary?.missing_documents_count || documents.length },
    { id: 'profile', label: 'Tax Profile', icon: Building2 },
  ];

  if (!isSessionChecked) {
    return (
      <div className="min-h-screen w-screen flex items-center justify-center bg-slate-950 text-indigo-400">
        <RefreshCw className="w-8 h-8 animate-spin" />
      </div>
    );
  }

  if (isSessionChecked && !isLoggedIn) {
    return (
      <div className="min-h-screen w-screen flex flex-col items-center justify-center bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 text-slate-100 p-6 relative overflow-y-auto">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col items-center mb-6 text-center z-10">
          <div className="h-14 w-14 rounded-2xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-blue-600 flex items-center justify-center text-white shadow-xl shadow-indigo-500/25 mb-3 border border-indigo-400/30">
            <Receipt className="w-7 h-7" />
          </div>
          <h1 className="text-2xl font-black tracking-tight text-white flex items-center gap-2">
            TaxSnap <span className="text-indigo-400 font-medium text-xs px-2 py-0.5 rounded-full bg-indigo-950/80 border border-indigo-500/30">Corporate Intelligence</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1 max-w-sm">
            Enterprise Tax Ledger, Deduction Compliance & Real-Time Filings with PostgreSQL 16 Multi-Tenant Isolation
          </p>
        </div>

        <div className="w-full max-w-md bg-slate-900/80 border border-slate-800 rounded-2xl shadow-2xl backdrop-blur-xl p-6 z-10">
          <div className="flex p-1 bg-slate-800/80 rounded-xl mb-5 border border-slate-700/60">
            <button
              onClick={() => { setAuthTab('signin'); setAuthError(null); }}
              className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
                authTab === 'signin'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setAuthTab('signup'); setAuthError(null); }}
              className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
                authTab === 'signup'
                  ? 'bg-indigo-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Register Company
            </button>
          </div>

          {authError && (
            <div className="mb-4 p-3 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2 animate-in fade-in">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
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
                  placeholder="director@vanguardtax.com"
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
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
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <button
                type="submit"
                disabled={isAuthLoading}
                className="w-full mt-2 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold text-xs rounded-xl shadow-lg shadow-indigo-600/30 transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                {isAuthLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
                <span>{isAuthLoading ? 'Authenticating...' : 'Sign In to Workspace'}</span>
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
                  placeholder="Eleanor Sterling"
                  className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-300 mb-1">Company / Entity Name</label>
                <input
                  type="text"
                  value={registerCompany}
                  onChange={(e) => setRegisterCompany(e.target.value)}
                  placeholder="Apex Global Holdings LLC"
                  className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
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
                    placeholder="director@apex.com"
                    className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
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
                    className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-300 mb-1">Corporate Role</label>
                <select
                  value={registerRole}
                  onChange={(e) => setRegisterRole(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-white focus:outline-none focus:border-indigo-500"
                >
                  <option value="FINANCE_DIRECTOR">Finance Director (Admin)</option>
                  <option value="SENIOR_CPA">Senior CPA (Accountant)</option>
                  <option value="BOOKKEEPER">Corporate Bookkeeper (Staff)</option>
                  <option value="AUDITOR_STAKEHOLDER">Auditor & Stakeholder (Viewer)</option>
                </select>
              </div>

              <button
                type="submit"
                disabled={isAuthLoading}
                className="w-full mt-2 py-2.5 px-4 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold text-xs rounded-xl shadow-lg shadow-blue-600/30 transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                {isAuthLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                <span>{isAuthLoading ? 'Provisioning Tenant...' : 'Create Company & Account'}</span>
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
                onClick={() => handleAuthLogin(undefined, 'director@vanguardtax.com', 'password123')}
                className="w-full p-2 rounded-xl bg-slate-800/70 hover:bg-indigo-950/40 hover:border-indigo-500/50 border border-slate-700/60 text-left transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="text-xs font-bold text-white group-hover:text-indigo-300">Eleanor Sterling (Finance Director)</p>
                  <p className="text-[10px] text-slate-400">Vanguard Global Consulting • <span className="font-mono text-indigo-400">tenant-001</span></p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-medium">Quick Login</span>
              </button>

              <button
                type="button"
                onClick={() => handleAuthLogin(undefined, 'cpa@vanguardtax.com', 'password123')}
                className="w-full p-2 rounded-xl bg-slate-800/70 hover:bg-blue-950/40 hover:border-blue-500/50 border border-slate-700/60 text-left transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="text-xs font-bold text-white group-hover:text-blue-300">Marcus Vance, CPA (Senior CPA)</p>
                  <p className="text-[10px] text-slate-400">Vanguard Global Consulting • <span className="font-mono text-blue-400">tenant-001</span></p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 font-medium">Quick Login</span>
              </button>

              <button
                type="button"
                onClick={() => handleAuthLogin(undefined, 'director@horizoncap.com', 'password123')}
                className="w-full p-2 rounded-xl bg-slate-800/70 hover:bg-purple-950/40 hover:border-purple-500/50 border border-slate-700/60 text-left transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="text-xs font-bold text-white group-hover:text-purple-300">Julian Thorne (Finance Director)</p>
                  <p className="text-[10px] text-slate-400">Horizon Capital Partners • <span className="font-mono text-purple-400">tenant-002</span></p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 font-medium">Quick Login</span>
              </button>
            </div>
          </div>
        </div>

        <div className="mt-5 text-center text-[11px] text-slate-500 flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-indigo-500" />
          <span>Strict Multi-Tenant Row Partitioning • PostgreSQL 16 • All passwords: <strong className="text-slate-400 font-mono">password123</strong></span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen bg-slate-50 text-slate-900 font-sans overflow-hidden">
      {/* =====================================================================
          1. LEFT PERSISTENT SIDEBAR (~260px)
      ====================================================================== */}
      <aside className="w-64 bg-white border-r border-slate-200/90 flex flex-col shrink-0 select-none">
        {/* Brand Header */}
        <div className="p-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-700 via-indigo-600 to-blue-600 flex items-center justify-center text-white shadow-xs">
              <Receipt className="w-5 h-5" />
            </div>
            <div>
              <h1 className="font-bold text-sm tracking-tight text-slate-900 leading-tight">TaxSnap</h1>
              <span className="text-[10px] font-semibold tracking-wide text-indigo-600 uppercase">
                Corporate Intelligence
              </span>
            </div>
          </div>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold font-mono bg-indigo-50 text-indigo-700 border border-indigo-200">
            v2.0
          </span>
        </div>

        {/* Entity Banner */}
        <div className="px-4 py-2.5 bg-slate-50/70 border-b border-slate-100">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Tax Entity</p>
          <p className="font-semibold text-xs text-slate-800 truncate mt-0.5">
            {profile?.business_name || 'Vanguard Global Consulting LLC'}
          </p>
          <p className="text-[11px] font-mono text-slate-500">TIN: {profile?.tin_number || 'XX-XXX9821'}</p>
        </div>

        {/* Nav Links */}
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id as TabType)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-slate-400'}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge !== undefined && (
                  <span
                    className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                      isActive ? 'bg-indigo-700 text-white' : 'bg-slate-200/70 text-slate-600'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Multi-App Hub Switcher */}
        <div className="p-3 border-t border-slate-100 bg-slate-50/40">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2 px-1">
            Axio360 Ecosystem
          </p>
          <div className="grid grid-cols-3 gap-1.5 text-center text-[10px] font-semibold">
            <a
              href="http://localhost:3001"
              target="_blank"
              rel="noreferrer"
              className="p-1.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 transition-colors flex flex-col items-center gap-0.5"
            >
              <span>PractiCare</span>
              <span className="text-[8px] opacity-75 font-mono">:3001</span>
            </a>
            <a
              href="http://localhost:3003"
              target="_blank"
              rel="noreferrer"
              className="p-1.5 rounded-md bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100 transition-colors flex flex-col items-center gap-0.5"
            >
              <span>PropSights</span>
              <span className="text-[8px] opacity-75 font-mono">:3003</span>
            </a>
            <a
              href="http://localhost:3004"
              target="_blank"
              rel="noreferrer"
              className="p-1.5 rounded-md bg-sky-50 text-sky-700 border border-sky-200 hover:bg-sky-100 transition-colors flex flex-col items-center gap-0.5"
            >
              <span>OnScribe</span>
              <span className="text-[8px] opacity-75 font-mono">:3004</span>
            </a>
          </div>
        </div>

        {/* User Profile Card & Tenant Switcher Footer */}
        <div className="p-3 border-t border-slate-200/80 bg-slate-50/70">
          {isLoggedIn ? (
            <div className="space-y-2">
              <div
                onClick={() => setShowAuthModal(true)}
                className="group p-2.5 rounded-xl border border-slate-200 bg-white hover:border-indigo-300 hover:shadow-xs transition-all cursor-pointer"
              >
                <div className="flex items-center gap-2.5">
                  <div className="relative">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-600 to-indigo-500 text-white font-bold text-xs flex items-center justify-center shadow-xs">
                      {userName.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()}
                    </div>
                    <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-white" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-bold text-slate-800 truncate group-hover:text-indigo-600 transition-colors">
                      {userName}
                    </p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[9px] font-bold tracking-tight uppercase bg-indigo-50 text-indigo-700 border border-indigo-200">
                        {userRole}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="mt-2 pt-1.5 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-500">
                  <span className="truncate max-w-[140px] font-medium text-slate-600">
                    {companyName || (tenantId === 'tenant-001' ? 'Vanguard Global' : 'Horizon Capital')} • {tenantId}
                  </span>
                  <span className="text-indigo-600 font-semibold group-hover:underline">Switch</span>
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
              className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-xs transition-all"
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
            <button
              onClick={fetchData}
              title="Refresh Data"
              className="p-1 rounded hover:bg-slate-200 text-slate-500 hover:text-slate-800 transition-colors"
            >
              <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </aside>

      {/* =====================================================================
          2. MAIN CONTENT AREA
      ====================================================================== */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden bg-slate-50">
        {/* Top App Bar */}
        <header className="h-14 bg-white border-b border-slate-200/80 px-6 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <h2 className="font-bold text-base text-slate-900 capitalize">
              {activeTab === 'dashboard' ? 'Executive Tax & Financial Overview' : activeTab}
            </h2>
            <span className="text-slate-300">|</span>
            <span className="text-xs text-slate-500 font-medium">
              FY {profile?.fiscal_year || '2026'} Corporate Filing Period
            </span>
            {userRole !== 'FINANCE_DIRECTOR' && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 flex items-center gap-1">
                <Shield className="w-3 h-3 text-indigo-600" />
                <span>Role: {userRole}</span>
              </span>
            )}
            {!isLoggedIn && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-200">
                Read-Only Mode
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => handleTriggerTool('taxsnap.get_tax_summary', 'Audit Corporate Tax Summary')}
              className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-indigo-50 text-indigo-700 border border-indigo-200 hover:bg-indigo-100 transition-colors"
            >
              <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
              <span>Run AI Tax Audit</span>
            </button>
            <button
              onClick={() => setIsCopilotOpen(!isCopilotOpen)}
              className={`p-2 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                isCopilotOpen
                  ? 'bg-slate-100 border-slate-300 text-slate-800'
                  : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
              }`}
            >
              <Bot className="w-4 h-4 text-indigo-600" />
              <span>Copilot</span>
            </button>
          </div>
        </header>

        {/* Scrollable View Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* ===================================================================
              VIEW 1: EXECUTIVE DASHBOARD
          ==================================================================== */}
          {activeTab === 'dashboard' && (
            <div className="space-y-6">
              {/* 4 Key Metric Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Gross Income */}
                <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Gross Revenue</span>
                    <div className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                      <TrendingUp className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="mt-2.5">
                    <div className="text-2xl font-bold text-slate-900 font-mono">
                      ${summary ? summary.gross_income.toLocaleString() : '620,000'}
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-emerald-600 mt-1 font-medium">
                      <span>{incomes.length} billed client milestones</span>
                    </div>
                  </div>
                </div>

                {/* Deductible Write-Offs */}
                <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Deductible Write-Offs</span>
                    <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                      <Receipt className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="mt-2.5">
                    <div className="text-2xl font-bold text-indigo-600 font-mono">
                      ${summary ? summary.total_deductible_expenses.toLocaleString() : '147,500'}
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-slate-500 mt-1 font-medium">
                      <span>Total: ${summary ? summary.total_expenses.toLocaleString() : '156,500'}</span>
                    </div>
                  </div>
                </div>

                {/* Net Taxable Income */}
                <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Taxable Income</span>
                    <div className="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                      <DollarSign className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="mt-2.5">
                    <div className="text-2xl font-bold text-slate-900 font-mono">
                      ${summary ? summary.net_taxable_income.toLocaleString() : '472,500'}
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-slate-500 mt-1 font-medium">
                      <span>After allowable write-offs</span>
                    </div>
                  </div>
                </div>

                {/* Estimated Federal Liability */}
                <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Estimated Tax (21%)</span>
                    <div className="w-7 h-7 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                      <AlertCircle className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="mt-2.5">
                    <div className="text-2xl font-bold text-amber-600 font-mono">
                      ${summary ? summary.estimated_tax_liability.toLocaleString() : '99,225'}
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-amber-700 mt-1 font-medium">
                      <span>Corporate Federal Bracket</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Middle Section: Category Breakdown + Compliance Alerts */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Expense Categories Breakdown */}
                <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs">
                  <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                    <div>
                      <h3 className="font-bold text-sm text-slate-900">Corporate Expense Allocation</h3>
                      <p className="text-xs text-slate-500">Breakdown of operational write-offs & non-deductible costs</p>
                    </div>
                    <button
                      onClick={handleOpenCreateExpense}
                      className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors shadow-xs"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add Expense
                    </button>
                  </div>

                  <div className="mt-4 space-y-3">
                    {summary?.expense_by_category &&
                      Object.entries(summary.expense_by_category).map(([cat, amt]) => {
                        const total = summary.total_expenses || 1;
                        const pct = Math.round((amt / total) * 100);
                        return (
                          <div key={cat} className="space-y-1">
                            <div className="flex items-center justify-between text-xs font-semibold">
                              <span className="text-slate-700">{cat}</span>
                              <div className="flex items-center gap-2">
                                <span className="font-mono text-slate-900">${amt.toLocaleString()}</span>
                                <span className="text-slate-400 font-mono text-[11px]">({pct}%)</span>
                              </div>
                            </div>
                            <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                              <div
                                className="bg-gradient-to-r from-indigo-500 to-blue-500 h-full rounded-full"
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                  </div>
                </div>

                {/* Compliance & Deadlines */}
                <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                      <div>
                        <h3 className="font-bold text-sm text-slate-900">Compliance Filings</h3>
                        <p className="text-xs text-slate-500">Upcoming IRS & State deadlines</p>
                      </div>
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
                        {summary?.missing_documents_count || 0} Action Req.
                      </span>
                    </div>

                    <div className="mt-3.5 space-y-2.5">
                      {documents.slice(0, 4).map((doc) => (
                        <div
                          key={doc.id}
                          className="p-2.5 rounded-lg border border-slate-100 bg-slate-50/60 flex items-start justify-between gap-2"
                        >
                          <div>
                            <p className="font-semibold text-xs text-slate-800">{doc.document_type}</p>
                            <p className="text-[10px] text-slate-500 mt-0.5 flex items-center gap-1 font-mono">
                              <Calendar className="w-3 h-3 text-slate-400" />
                              Due {doc.deadline}
                            </p>
                          </div>
                          <span
                            className={`text-[9px] font-bold px-2 py-0.5 rounded-full uppercase shrink-0 ${
                              doc.status === 'VERIFIED'
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                : doc.status === 'OVERDUE'
                                ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                : 'bg-amber-50 text-amber-700 border border-amber-200'
                            }`}
                          >
                            {doc.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <button
                    onClick={() => setActiveTab('documents')}
                    className="mt-4 w-full py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1"
                  >
                    <span>View All Compliance Documents</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ===================================================================
              VIEW 2: INCOME LEDGER
          ==================================================================== */}
          {activeTab === 'income' && (
            <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
                <div>
                  <h3 className="font-bold text-base text-slate-900">Corporate Income Ledger</h3>
                  <p className="text-xs text-slate-500">
                    Gross receipts, advisory retainers, and milestone billings
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={incomeStatusFilter}
                    onChange={(e) => setIncomeStatusFilter(e.target.value)}
                    className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-slate-50 text-slate-700 font-medium"
                  >
                    <option value="ALL">All Statuses</option>
                    <option value="Received">Received</option>
                    <option value="Invoiced">Invoiced</option>
                    <option value="Pending">Pending</option>
                  </select>
                  <button
                    onClick={handleOpenCreateIncome}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors shadow-xs"
                  >
                    <Plus className="w-4 h-4" />
                    Record Income
                  </button>
                </div>
              </div>

              {/* Income Table */}
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                    <tr>
                      <th className="p-3">Source & Client</th>
                      <th className="p-3">Date</th>
                      <th className="p-3">Amount</th>
                      <th className="p-3">Status</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {incomes
                      .filter((i) => incomeStatusFilter === 'ALL' || i.status.toLowerCase() === incomeStatusFilter.toLowerCase())
                      .map((item) => (
                        <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="p-3 font-semibold text-slate-900">{item.source}</td>
                          <td className="p-3 text-slate-500 font-mono text-[11px]">{item.date}</td>
                          <td className="p-3 font-mono font-bold text-emerald-600 text-sm">
                            +${item.amount.toLocaleString()}
                          </td>
                          <td className="p-3">
                            <span
                              className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full ${
                                item.status === 'Received'
                                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                  : item.status === 'Invoiced'
                                  ? 'bg-blue-50 text-blue-700 border border-blue-200'
                                  : 'bg-amber-50 text-amber-700 border border-amber-200'
                              }`}
                            >
                              {item.status}
                            </span>
                          </td>
                          <td className="p-3 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                onClick={() => handleOpenEditIncome(item)}
                                className="p-1.5 hover:bg-slate-100 text-slate-400 hover:text-slate-700 rounded transition-colors"
                                title="Edit Income"
                              >
                                <Pencil className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => handleDeleteIncome(item.id)}
                                className="p-1.5 hover:bg-rose-50 text-slate-400 hover:text-rose-600 rounded transition-colors"
                                title="Delete Income"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ===================================================================
              VIEW 3: EXPENSE LEDGER
          ==================================================================== */}
          {activeTab === 'expenses' && (
            <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
                <div>
                  <h3 className="font-bold text-base text-slate-900">Corporate Expense Ledger</h3>
                  <p className="text-xs text-slate-500">
                    Track vendor costs, cloud infrastructure, and deductible business write-offs
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={expenseCategoryFilter}
                    onChange={(e) => setExpenseCategoryFilter(e.target.value)}
                    className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-slate-50 text-slate-700 font-medium"
                  >
                    <option value="ALL">All Categories</option>
                    <option value="Cloud Infrastructure">Cloud Infrastructure</option>
                    <option value="Office Lease">Office Lease</option>
                    <option value="Legal Advisory">Legal Advisory</option>
                    <option value="Software">Software</option>
                    <option value="Travel">Travel</option>
                    <option value="Dining">Dining</option>
                  </select>
                  <button
                    onClick={handleOpenCreateExpense}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors shadow-xs"
                  >
                    <Plus className="w-4 h-4" />
                    Record Expense
                  </button>
                </div>
              </div>

              {/* Expense Table */}
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                    <tr>
                      <th className="p-3">Vendor / Payee</th>
                      <th className="p-3">Category</th>
                      <th className="p-3">Date</th>
                      <th className="p-3">Amount</th>
                      <th className="p-3">Deductible Write-Off</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {expenses
                      .filter(
                        (e) =>
                          expenseCategoryFilter === 'ALL' ||
                          e.category.toLowerCase().includes(expenseCategoryFilter.toLowerCase())
                      )
                      .map((item) => (
                        <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="p-3">
                            <span className="font-semibold text-slate-900">{item.vendor}</span>
                            {item.receipt_url && (
                              <span className="block text-[10px] text-indigo-600 truncate mt-0.5">
                                [Receipt Attached]
                              </span>
                            )}
                          </td>
                          <td className="p-3">
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-700">
                              {item.category}
                            </span>
                          </td>
                          <td className="p-3 text-slate-500 font-mono text-[11px]">{item.date}</td>
                          <td className="p-3 font-mono font-bold text-slate-900 text-sm">
                            ${item.amount.toLocaleString()}
                          </td>
                          <td className="p-3">
                            <button
                              onClick={() => handleToggleExpenseDeductible(item)}
                              className={`inline-flex items-center gap-1 text-[10px] font-bold px-2.5 py-1 rounded-full transition-all border ${
                                item.is_deductible
                                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
                                  : 'bg-slate-100 text-slate-500 border-slate-200 hover:bg-slate-200'
                              }`}
                              title="Click to toggle tax write-off eligibility"
                            >
                              <Check className={`w-3 h-3 ${item.is_deductible ? 'opacity-100' : 'opacity-20'}`} />
                              <span>{item.is_deductible ? 'Deductible (100%)' : 'Non-Deductible'}</span>
                            </button>
                          </td>
                          <td className="p-3 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                onClick={() => handleOpenEditExpense(item)}
                                className="p-1.5 hover:bg-slate-100 text-slate-400 hover:text-slate-700 rounded transition-colors"
                                title="Edit Expense"
                              >
                                <Pencil className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => handleDeleteExpense(item.id)}
                                className="p-1.5 hover:bg-rose-50 text-slate-400 hover:text-rose-600 rounded transition-colors"
                                title="Delete Expense"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ===================================================================
              VIEW 4: COMPLIANCE & TAX DOCUMENTS
          ==================================================================== */}
          {activeTab === 'documents' && (
            <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
                <div>
                  <h3 className="font-bold text-base text-slate-900">Tax Documents & Compliance Audit</h3>
                  <p className="text-xs text-slate-500">
                    IRS form verification, state filings, and CPA assigned workflows
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={documentStatusFilter}
                    onChange={(e) => setDocumentStatusFilter(e.target.value)}
                    className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-slate-50 text-slate-700 font-medium"
                  >
                    <option value="ALL">All Statuses</option>
                    <option value="VERIFIED">Verified</option>
                    <option value="PENDING_UPLOAD">Pending Upload</option>
                    <option value="MISSING">Missing</option>
                    <option value="OVERDUE">Overdue</option>
                  </select>
                  <button
                    onClick={handleOpenCreateDoc}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors shadow-xs"
                  >
                    <Plus className="w-4 h-4" />
                    Register Document
                  </button>
                </div>
              </div>

              {/* Document Table */}
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                    <tr>
                      <th className="p-3">Document Title / IRS Form</th>
                      <th className="p-3">Status</th>
                      <th className="p-3">Filing Deadline</th>
                      <th className="p-3">Assigned CPA</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {documents
                      .filter(
                        (d) =>
                          documentStatusFilter === 'ALL' ||
                          d.status.toUpperCase() === documentStatusFilter.toUpperCase()
                      )
                      .map((item) => (
                        <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="p-3 font-semibold text-slate-900">{item.document_type}</td>
                          <td className="p-3">
                            <button
                              onClick={() => handleQuickVerifyDoc(item)}
                              className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full uppercase transition-all ${
                                item.status === 'VERIFIED'
                                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                  : item.status === 'OVERDUE'
                                  ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                  : 'bg-amber-50 text-amber-700 border border-amber-200'
                              }`}
                              title="Click to toggle CPA verification"
                            >
                              {item.status}
                            </button>
                          </td>
                          <td className="p-3 text-slate-500 font-mono text-[11px]">{item.deadline}</td>
                          <td className="p-3 text-slate-700 font-medium">{item.assigned_cpa || 'Unassigned'}</td>
                          <td className="p-3 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                onClick={() => handleOpenEditDoc(item)}
                                className="p-1.5 hover:bg-slate-100 text-slate-400 hover:text-slate-700 rounded transition-colors"
                                title="Edit Document"
                              >
                                <Pencil className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => handleDeleteDoc(item.id)}
                                className="p-1.5 hover:bg-rose-50 text-slate-400 hover:text-rose-600 rounded transition-colors"
                                title="Delete Document"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ===================================================================
              VIEW 5: TAX PROFILE
          ==================================================================== */}
          {activeTab === 'profile' && (
            <div className="max-w-2xl bg-white rounded-xl border border-slate-200/90 p-6 shadow-xs space-y-6">
              <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                <div>
                  <h3 className="font-bold text-base text-slate-900">Corporate Tax Entity Profile</h3>
                  <p className="text-xs text-slate-500">Legal entity registration, TIN, and bracket configurations</p>
                </div>
                <button
                  onClick={() => setShowProfileModal(true)}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors shadow-xs"
                >
                  <Pencil className="w-3.5 h-3.5" />
                  Edit Profile
                </button>
              </div>

              <div className="grid grid-cols-2 gap-4 text-xs">
                <div className="p-3.5 bg-slate-50 rounded-lg border border-slate-100">
                  <span className="text-slate-400 font-semibold uppercase text-[10px]">Legal Entity Name</span>
                  <p className="font-bold text-slate-800 text-sm mt-1">{profile?.business_name}</p>
                </div>

                <div className="p-3.5 bg-slate-50 rounded-lg border border-slate-100">
                  <span className="text-slate-400 font-semibold uppercase text-[10px]">Federal TIN / EIN</span>
                  <p className="font-mono font-bold text-slate-800 text-sm mt-1">{profile?.tin_number}</p>
                </div>

                <div className="p-3.5 bg-slate-50 rounded-lg border border-slate-100">
                  <span className="text-slate-400 font-semibold uppercase text-[10px]">Fiscal Year</span>
                  <p className="font-bold text-slate-800 text-sm mt-1">{profile?.fiscal_year}</p>
                </div>

                <div className="p-3.5 bg-slate-50 rounded-lg border border-slate-100">
                  <span className="text-slate-400 font-semibold uppercase text-[10px]">Corporate Tax Rate</span>
                  <p className="font-mono font-bold text-indigo-600 text-sm mt-1">
                    {profile ? `${profile.corporate_tax_rate * 100}%` : '21%'}
                  </p>
                </div>
              </div>

              <div className="p-4 rounded-lg bg-indigo-50/60 border border-indigo-100 text-xs text-indigo-900 flex items-start gap-2.5">
                <ShieldCheck className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                <div>
                  <p className="font-bold">PostgreSQL Multi-Tenant Storage Active</p>
                  <p className="text-[11px] text-indigo-700 mt-0.5">
                    Records are isolated under tenant <span className="font-mono font-bold">{tenantId}</span> with
                    relational foreign-key constraints on PostgreSQL 16.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* =====================================================================
          3. RIGHT PERSISTENT AI COPILOT DRAWER (~410px)
      ====================================================================== */}
      {isCopilotOpen && (
        <aside className="w-[410px] bg-white border-l border-slate-200/90 flex flex-col shrink-0">
          {/* Copilot Header */}
          <div className="p-4 border-b border-slate-100 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-xs">
                <Bot className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-bold text-xs text-slate-900">TaxSnap Intelligence Agent</h3>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="text-[10px] text-emerald-600 font-semibold">PostgreSQL Synchronized</span>
                </div>
              </div>
            </div>
            <button
              onClick={() => setIsCopilotOpen(false)}
              className="text-slate-400 hover:text-slate-600 p-1 rounded"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Security Context Chip */}
          <div className="px-4 py-2 bg-slate-50 border-b border-slate-100 flex items-center justify-between text-[11px]">
            <div className="flex items-center gap-1.5 text-slate-600 font-mono">
              <ShieldCheck className="w-3.5 h-3.5 text-indigo-600" />
              <span>x-tenant-id: {tenantId}</span>
            </div>
            <button
              onClick={() => setSecurityChipExpanded(!securityChipExpanded)}
              className="text-slate-400 hover:text-slate-600"
            >
              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${securityChipExpanded ? 'rotate-180' : ''}`} />
            </button>
          </div>

          {securityChipExpanded && (
            <div className="px-4 py-2.5 bg-slate-100/70 border-b border-slate-200 text-[10px] font-mono text-slate-600 space-y-1">
              <div>user_id: {userId}</div>
              <div>role: Lead Corporate Tax CPA</div>
              <div>database: PostgreSQL 16 (practicare_db/tax_profiles)</div>
            </div>
          )}

          {/* Messages Stream */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3.5">
            {messages.map((m) => (
              <div key={m.id} className="space-y-1.5">
                <div className={`flex items-start gap-2 ${m.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {m.sender === 'assistant' && (
                    <div className="w-6 h-6 rounded-md bg-indigo-100 text-indigo-700 flex items-center justify-center shrink-0 mt-0.5">
                      <Sparkles className="w-3.5 h-3.5" />
                    </div>
                  )}
                  <div
                    className={`max-w-[85%] rounded-xl p-3 text-xs leading-relaxed shadow-xs ${
                      m.sender === 'user'
                        ? 'bg-indigo-600 text-white font-medium'
                        : 'bg-slate-50 text-slate-800 border border-slate-200/80'
                    }`}
                  >
                    <p>{m.text}</p>
                    <span
                      className={`block text-[9px] mt-1.5 ${
                        m.sender === 'user' ? 'text-indigo-200' : 'text-slate-400'
                      }`}
                    >
                      {m.timestamp}
                    </span>
                  </div>
                </div>

                {/* Tool Execution Card */}
                {m.toolCall && (
                  <div className="ml-8 rounded-lg border border-indigo-100 bg-indigo-50/40 p-2.5 text-[11px] space-y-1.5 shadow-2xs">
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-indigo-700 text-[10px]">
                        {m.toolCall.toolName}
                      </span>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[9px] font-mono text-slate-500">
                          {m.toolCall.executionTimeMs}ms
                        </span>
                        <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-emerald-100 text-emerald-800">
                          {m.toolCall.status}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() =>
                        setExpandedTraceId(expandedTraceId === m.id ? null : m.id)
                      }
                      className="text-[10px] text-indigo-600 hover:underline flex items-center gap-1 font-semibold"
                    >
                      <span>{expandedTraceId === m.id ? 'Hide Trace Payload' : 'View Execution Trace'}</span>
                      <ChevronRight className={`w-3 h-3 transition-transform ${expandedTraceId === m.id ? 'rotate-90' : ''}`} />
                    </button>

                    {expandedTraceId === m.id && (
                      <div className="mt-1 pt-1 border-t border-indigo-100 space-y-1 text-[9px] font-mono">
                        <div>
                          <span className="text-slate-500">Request:</span>
                          <pre className="bg-white p-1 rounded border border-slate-200 overflow-x-auto text-slate-800 mt-0.5">
                            {JSON.stringify(m.toolCall.requestPayload, null, 2)}
                          </pre>
                        </div>
                        <div>
                          <span className="text-slate-500">Response:</span>
                          <pre className="bg-white p-1 rounded border border-slate-200 overflow-x-auto text-slate-800 mt-0.5 max-h-40">
                            {JSON.stringify(m.toolCall.responsePayload, null, 2)}
                          </pre>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Quick Query Suggestion Chips */}
          <div className="p-3 border-t border-slate-100 bg-slate-50/50 space-y-1.5">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Quick Financial Actions
            </p>
            <div className="flex flex-wrap gap-1.5">
              <button
                onClick={() => handleTriggerTool('taxsnap.get_tax_summary', 'Summarize federal tax liability')}
                className="text-[10px] font-semibold px-2 py-1 bg-white border border-slate-200 hover:border-indigo-300 hover:text-indigo-600 rounded-md transition-colors shadow-2xs"
              >
                Summarize tax liability
              </button>
              <button
                onClick={() => handleTriggerTool('taxsnap.list_expenses', 'List all deductible write-offs', { only_deductible: true })}
                className="text-[10px] font-semibold px-2 py-1 bg-white border border-slate-200 hover:border-indigo-300 hover:text-indigo-600 rounded-md transition-colors shadow-2xs"
              >
                List deductible write-offs
              </button>
              <button
                onClick={() => handleTriggerTool('taxsnap.list_missing_documents', 'Audit missing compliance filings')}
                className="text-[10px] font-semibold px-2 py-1 bg-white border border-slate-200 hover:border-indigo-300 hover:text-indigo-600 rounded-md transition-colors shadow-2xs"
              >
                Audit missing filings
              </button>
            </div>
          </div>

          {/* Chat Input */}
          <form onSubmit={handleSendChat} className="p-3 border-t border-slate-200 bg-white flex items-center gap-2">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Ask Tax Copilot or audit finances..."
              className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs focus:bg-white focus:outline-none focus:border-indigo-600"
            />
            <button
              type="submit"
              disabled={isCallingTool}
              className="p-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </form>
        </aside>
      )}

      {/* =====================================================================
          4. MODAL DIALOGS FOR CRUD
      ====================================================================== */}
      {/* MODAL 1: INCOME */}
      {showIncomeModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-sm text-slate-900">
                {editingIncome ? 'Edit Income Record' : 'Record New Income'}
              </h3>
              <button onClick={() => setShowIncomeModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveIncome} className="mt-4 space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Source / Client Name *</label>
                <input
                  type="text"
                  required
                  value={incomeForm.source}
                  onChange={(e) => setIncomeForm({ ...incomeForm, source: e.target.value })}
                  placeholder="e.g. Enterprise AI Retainer (Fintech Corp)"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-indigo-600"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Amount ($ USD) *</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={incomeForm.amount}
                    onChange={(e) => setIncomeForm({ ...incomeForm, amount: e.target.value })}
                    placeholder="95000"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-indigo-600"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Date *</label>
                  <input
                    type="date"
                    required
                    value={incomeForm.date}
                    onChange={(e) => setIncomeForm({ ...incomeForm, date: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-indigo-600"
                  />
                </div>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Payment Status</label>
                <select
                  value={incomeForm.status}
                  onChange={(e) => setIncomeForm({ ...incomeForm, status: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                >
                  <option value="Received">Received</option>
                  <option value="Invoiced">Invoiced</option>
                  <option value="Pending">Pending</option>
                </select>
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowIncomeModal(false)}
                  className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Save Income
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: EXPENSE */}
      {showExpenseModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-sm text-slate-900">
                {editingExpense ? 'Edit Expense Record' : 'Record Corporate Expense'}
              </h3>
              <button onClick={() => setShowExpenseModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveExpense} className="mt-4 space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Vendor / Payee *</label>
                <input
                  type="text"
                  required
                  value={expenseForm.vendor}
                  onChange={(e) => setExpenseForm({ ...expenseForm, vendor: e.target.value })}
                  placeholder="e.g. Amazon Web Services & GPU Compute"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-indigo-600"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Category *</label>
                  <select
                    value={expenseForm.category}
                    onChange={(e) => setExpenseForm({ ...expenseForm, category: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                  >
                    <option value="Cloud Infrastructure">Cloud Infrastructure</option>
                    <option value="Office Lease">Office Lease</option>
                    <option value="Legal Advisory">Legal Advisory</option>
                    <option value="Software">Software</option>
                    <option value="Travel">Travel</option>
                    <option value="Dining">Dining</option>
                  </select>
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Amount ($ USD) *</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={expenseForm.amount}
                    onChange={(e) => setExpenseForm({ ...expenseForm, amount: e.target.value })}
                    placeholder="48500"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-indigo-600"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Date *</label>
                  <input
                    type="date"
                    required
                    value={expenseForm.date}
                    onChange={(e) => setExpenseForm({ ...expenseForm, date: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-indigo-600"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Receipt URL (Optional)</label>
                  <input
                    type="text"
                    value={expenseForm.receipt_url}
                    onChange={(e) => setExpenseForm({ ...expenseForm, receipt_url: e.target.value })}
                    placeholder="https://..."
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                  />
                </div>
              </div>

              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 flex items-center justify-between">
                <div>
                  <span className="font-bold text-slate-800">Deductible Tax Write-Off</span>
                  <p className="text-[10px] text-slate-500">Qualifies as allowable business expense deduction</p>
                </div>
                <input
                  type="checkbox"
                  checked={expenseForm.is_deductible}
                  onChange={(e) => setExpenseForm({ ...expenseForm, is_deductible: e.target.checked })}
                  className="w-4 h-4 text-indigo-600 rounded focus:ring-indigo-500"
                />
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowExpenseModal(false)}
                  className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Save Expense
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: TAX DOCUMENT */}
      {showDocModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-sm text-slate-900">
                {editingDoc ? 'Edit Compliance Document' : 'Register Tax Document'}
              </h3>
              <button onClick={() => setShowDocModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveDoc} className="mt-4 space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Document Type / IRS Form *</label>
                <input
                  type="text"
                  required
                  value={docForm.document_type}
                  onChange={(e) => setDocForm({ ...docForm, document_type: e.target.value })}
                  placeholder="e.g. Form 1099-NEC, Q3 Sales Tax Return"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-indigo-600"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Status</label>
                  <select
                    value={docForm.status}
                    onChange={(e) => setDocForm({ ...docForm, status: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                  >
                    <option value="VERIFIED">Verified</option>
                    <option value="PENDING_UPLOAD">Pending Upload</option>
                    <option value="MISSING">Missing</option>
                    <option value="OVERDUE">Overdue</option>
                  </select>
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Filing Deadline *</label>
                  <input
                    type="date"
                    required
                    value={docForm.deadline}
                    onChange={(e) => setDocForm({ ...docForm, deadline: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Assigned CPA</label>
                <input
                  type="text"
                  value={docForm.assigned_cpa}
                  onChange={(e) => setDocForm({ ...docForm, assigned_cpa: e.target.value })}
                  placeholder="e.g. Elena Rostova, CPA"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                />
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowDocModal(false)}
                  className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Save Document
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 4: PROFILE */}
      {showProfileModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-sm text-slate-900">Edit Corporate Tax Profile</h3>
              <button onClick={() => setShowProfileModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveProfile} className="mt-4 space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Business Name *</label>
                <input
                  type="text"
                  required
                  value={profileForm.business_name}
                  onChange={(e) => setProfileForm({ ...profileForm, business_name: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">TIN / EIN Number *</label>
                <input
                  type="text"
                  required
                  value={profileForm.tin_number}
                  onChange={(e) => setProfileForm({ ...profileForm, tin_number: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white font-mono"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Fiscal Year</label>
                  <input
                    type="text"
                    required
                    value={profileForm.fiscal_year}
                    onChange={(e) => setProfileForm({ ...profileForm, fiscal_year: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Corporate Tax Rate</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="1"
                    required
                    value={profileForm.corporate_tax_rate}
                    onChange={(e) =>
                      setProfileForm({ ...profileForm, corporate_tax_rate: parseFloat(e.target.value) || 0.21 })
                    }
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white font-mono"
                  />
                </div>
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowProfileModal(false)}
                  className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Save Profile
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
                <div className="w-8 h-8 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold">
                  <ShieldCheck className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900">Switch Company & User Role</h3>
                  <p className="text-[11px] text-slate-500">Corporate Multi-Tenant Partitioning & RBAC</p>
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
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-medium text-slate-800 focus:bg-white focus:outline-none focus:border-indigo-600"
                  >
                    <option value="tenant-001">Vanguard Global (tenant-001)</option>
                    <option value="tenant-002">Horizon Capital (tenant-002)</option>
                  </select>
                </div>

                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Assigned Role</label>
                  <select
                    value={modalRole}
                    onChange={(e) => setModalRole(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-medium text-slate-800 focus:bg-white focus:outline-none focus:border-indigo-600"
                  >
                    <option value="FINANCE_DIRECTOR">Finance Director (Admin)</option>
                    <option value="SENIOR_CPA">Senior CPA (Accountant)</option>
                    <option value="BOOKKEEPER">Bookkeeper (Data Entry)</option>
                    <option value="AUDITOR_STAKEHOLDER">Auditor Stakeholder (Viewer)</option>
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
                            ? 'bg-indigo-50 border-indigo-400 ring-2 ring-indigo-500/20'
                            : 'bg-slate-50/70 border-slate-200 hover:bg-slate-100 hover:border-slate-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-slate-900 text-xs truncate">{p.userName}</span>
                          <span className="text-[9px] px-1 py-0.2 rounded font-mono bg-slate-200/80 text-slate-700">
                            {p.tenantId}
                          </span>
                        </div>
                        <p className="text-[10px] text-indigo-700 font-semibold mt-0.5">{p.roleLabel}</p>
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
                    className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold text-xs shadow-xs transition-all"
                  >
                    Apply Session
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Floating Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 bg-slate-900 text-white text-xs px-4 py-2.5 rounded-lg shadow-lg border border-slate-700 animate-in fade-in slide-in-from-bottom-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{toastMessage.text}</span>
        </div>
      )}
    </div>
  );
}
