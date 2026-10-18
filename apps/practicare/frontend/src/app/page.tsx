'use client';

import React, { useState, useEffect } from 'react';
import InventoryImportModal from './InventoryImportModal';
import { AdjustStockModal, EditInventoryModal } from './InventoryEditModals';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  BadgeAlert,
  Bot,
  Building2,
  Calendar,
  Check,
  CheckCircle2,
  CheckSquare,
  ChevronDown,
  ChevronRight,
  Clock,
  DoorClosed,
  DoorOpen,
  Filter,
  Flame,
  FolderKanban,
  HeartPulse,
  History,
  Layers,
  LayoutDashboard,
  ListChecks,
  ListTodo,
  Copy,
  Key,
  Lock,
  LogIn,
  LogOut,
  Mail,
  MapPin,
  MessageSquare,
  Package,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Send,
  Shield,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  Trash2,
  TrendingDown,
  TrendingUp,
  Upload,
  User,
  UserCheck,
  UserPlus,
  Users,
  X,
} from 'lucide-react';

interface PracticeItem {
  id: string;
  name: string;
  location: string;
  room_count: number;
  tenant_id: string;
}

interface DashboardSummary {
  tenant_id: string;
  practice_name: string;
  total_staff: number;
  active_staff_count: number;
  total_rooms: number;
  room_occupancy: Record<string, number>;
  tasks_total: number;
  tasks_completed: number;
  tasks_pending: number;
  checklists_total: number;
  checklists_completed: number;
  low_stock_count: number;
  expiring_soon_count: number;
  on_shift_count?: number;
}

interface TaskItem {
  id: string;
  title: string;
  description?: string;
  priority: string;
  status: string;
  due_date: string;
  assigned_staff_id?: string;
  room_id?: string;
  assigned_staff_name?: string;
  room_name?: string;
  // Caller-specific permissions computed by the backend policy
  can_complete?: boolean | null;
  can_edit?: boolean | null;
  can_delete?: boolean | null;
}

interface ChecklistItem {
  id: string;
  title: string;
  category: string;
  is_completed: boolean;
  frequency: string;
  assigned_staff_id?: string;
  assigned_staff_name?: string;
  // Caller-specific permissions computed by the backend policy
  can_toggle?: boolean | null;
  can_edit?: boolean | null;
  can_delete?: boolean | null;
}

interface InventoryItem {
  id: string;
  item_name: string;
  current_stock: number;
  min_threshold: number;
  unit: string;
  expiry_date?: string;
  room_id?: string;
  room_name?: string;
  supplier?: string | null;
  batch_number?: string | null;
  purchase_price?: number | null;
  is_low_stock: boolean;
  is_expiring_soon: boolean;
  // Server-computed (inventory_service.expiry_info); the UI never re-implements date rules
  is_expired?: boolean;
  days_to_expiry?: number | null;
  expiry_status?: 'expired' | 'within_7' | 'within_30' | 'within_90' | 'later' | 'none';
  // Independent server statuses: stock level vs expiry (an item can be In Stock and Expiring Soon)
  stock_status?: 'In Stock' | 'Low Stock' | 'Out of Stock';
  expiry_state?: 'Expired' | 'Expiring Soon' | 'Valid' | 'No Expiry Date';
  shortfall?: number;
  // Caller permission from the backend policy (Owner / Inventory Manager)
  can_manage?: boolean;
}

const STOCK_BADGE: Record<string, string> = {
  'In Stock': 'bg-emerald-50 text-emerald-700 border border-emerald-200',
  'Low Stock': 'bg-amber-50 text-amber-800 border border-amber-300',
  'Out of Stock': 'bg-rose-600 text-white',
};
const EXPIRY_BADGE: Record<string, string> = {
  Expired: 'bg-rose-600 text-white',
  'Expiring Soon': 'bg-amber-50 text-amber-800 border border-amber-300',
  Valid: 'bg-slate-50 text-slate-600 border border-slate-200',
  'No Expiry Date': 'bg-slate-50 text-slate-400 border border-dashed border-slate-300',
};

type InventoryExpiryFilter = 'all' | 'expired' | 'within_7' | 'within_30' | 'within_90' | 'none';
type InventorySort = 'stock' | 'expiry' | 'name';

const INVENTORY_EXPIRY_FILTERS: { id: InventoryExpiryFilter; label: string }[] = [
  { id: 'all', label: 'All items' },
  { id: 'expired', label: 'Already expired' },
  { id: 'within_7', label: 'Expiring ≤ 7 days' },
  { id: 'within_30', label: 'Expiring ≤ 30 days' },
  { id: 'within_90', label: 'Expiring ≤ 90 days' },
  { id: 'none', label: 'No expiry date' },
];

// Counts per filter from server-computed expiry_status (windows are cumulative, like the backend filter)
const countForExpiryFilter = (items: InventoryItem[], f: InventoryExpiryFilter) => {
  const windows: Record<string, string[]> = {
    within_7: ['within_7'],
    within_30: ['within_7', 'within_30'],
    within_90: ['within_7', 'within_30', 'within_90'],
  };
  if (f === 'all') return items.length;
  if (f === 'expired' || f === 'none') return items.filter((i) => i.expiry_status === f).length;
  return items.filter((i) => windows[f].includes(i.expiry_status || '')).length;
};

const expiryLabel = (inv: InventoryItem) => {
  const days = inv.days_to_expiry;
  if (days === null || days === undefined) return null;
  if (days < 0) return `Expired ${-days}d ago`;
  if (days === 0) return 'Expires today';
  return `in ${days}d`;
};

interface RoomItem {
  id: string;
  room_number: string;
  name: string;
  room_type: string;
  status: string;
}

interface StaffItem {
  id: string;
  name: string;
  role: string;
  is_active: boolean;
  on_shift?: boolean;
  user_id?: string;
  email?: string;
  department?: string;
  practice_name?: string;
  membership_status?: string;
  created_at?: string;
}

interface CompanySettings {
  company_name: string;
  tenant_id: string;
  active_invitations_count: number;
  pending_requests_count: number;
  total_staff_count: number;
}

interface PendingMember {
  id: string;
  user_id?: string;
  name: string;
  email: string;
  role: string;
  membership_status: string;
  tenant_id: string;
  company_name?: string;
  created_at: string;
}

interface InvitationItem {
  id: string;
  code: string;
  role: string;
  tenant_id: string;
  max_uses: number;
  use_count: number;
  expires_at: string;
  is_revoked: boolean;
  is_active?: boolean;
  created_at: string;
}

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
    tenantName: 'Apex Health Medical Center',
    userRole: 'CLINIC_OWNER',
    userId: 'user-owner-001',
    userName: 'Dr. Liam Vance',
    roleLabel: 'Clinic Owner (Admin)',
    description: 'Full access to all operations within their own company.',
  },
  {
    tenantId: 'tenant-001',
    tenantName: 'Apex Health Medical Center',
    userRole: 'INVENTORY_MANAGER',
    userId: 'user-inv-001',
    userName: 'David Miller',
    roleLabel: 'Operations & Inventory Manager',
    description: 'Manage tasks, checklists, staff assignments, inventory, and rooms. Cannot delete self-assigned tasks.',
  },
  {
    tenantId: 'tenant-001',
    tenantName: 'Apex Health Medical Center',
    userRole: 'ATTENDING_PHYSICIAN',
    userId: 'user-doc-001',
    userName: 'Dr. Rachel Kim',
    roleLabel: 'Attending Physician (Doctor)',
    description: 'Manage tasks/checklists in scope; assign to Nurses; monitor nurse tasks; update room status; read-only inventory.',
  },
  {
    tenantId: 'tenant-001',
    tenantName: 'Apex Health Medical Center',
    userRole: 'NURSE_STAFF',
    userId: 'user-nurse-001',
    userName: 'Nurse Sarah Jenkins',
    roleLabel: 'Nurse Staff (Caregiver)',
    description: 'Complete assigned tasks; view company checklists; fill self-assigned checklists; read-only rooms and inventory.',
  },
  // Company B: tenant-002
  {
    tenantId: 'tenant-002',
    tenantName: 'Metro Health Urgent Care',
    userRole: 'CLINIC_OWNER',
    userId: 'user-owner-002',
    userName: 'Dr. Robert Hayes',
    roleLabel: 'Clinic Owner (Admin)',
    description: 'Full access to all operations within their own company.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'Metro Health Urgent Care',
    userRole: 'INVENTORY_MANAGER',
    userId: 'user-inv-002',
    userName: 'Jessica Clarke',
    roleLabel: 'Operations & Inventory Manager',
    description: 'Manage tasks, checklists, staff assignments, inventory, and rooms. Cannot delete self-assigned tasks.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'Metro Health Urgent Care',
    userRole: 'ATTENDING_PHYSICIAN',
    userId: 'user-doc-002',
    userName: 'Dr. Alicia Patel',
    roleLabel: 'Attending Physician (Doctor)',
    description: 'Manage tasks/checklists in scope; assign to Nurses; monitor nurse tasks; update room status; read-only inventory.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'Metro Health Urgent Care',
    userRole: 'NURSE_STAFF',
    userId: 'user-nurse-002',
    userName: 'Nurse Tom Bradley',
    roleLabel: 'Nurse Staff (Caregiver)',
    description: 'Complete assigned tasks; view company checklists; fill self-assigned checklists; read-only rooms and inventory.',
  },
];

export default function PractiCareEnterpriseApp() {
  const apiBase = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:5001';

  // Multi-Tenant & RBAC Session State
  const [tenantId, setTenantId] = useState<string>('tenant-001');
  const [userRole, setUserRole] = useState<string>('CLINIC_OWNER');
  const [userId, setUserId] = useState<string>('user-owner-001');
  const [userName, setUserName] = useState<string>('Dr. Liam Vance');
  const [companyName, setCompanyName] = useState<string>('Vanguard Comprehensive Health Center');
  const [isLoggedIn, setIsLoggedIn] = useState<boolean>(false);
  const [isSessionChecked, setIsSessionChecked] = useState<boolean>(false);
  const [showAuthModal, setShowAuthModal] = useState<boolean>(false);

  // Dedicated SaaS Auth Portal State
  const [authTab, setAuthTab] = useState<'signin' | 'signup'>('signin');
  const [loginEmail, setLoginEmail] = useState('owner@vanguardclinic.com');
  const [loginPassword, setLoginPassword] = useState('password123');
  const [registerFullName, setRegisterFullName] = useState('');
  const [registerEmail, setRegisterEmail] = useState('');
  const [registerPassword, setRegisterPassword] = useState('');
  const [registerCompany, setRegisterCompany] = useState('');
  const [registerRole, setRegisterRole] = useState('CLINIC_OWNER');
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(false);

  // Registration Dual-Path State (Create New Company vs Join Existing Company)
  const [signupPath, setSignupPath] = useState<'create_company' | 'join_company'>('create_company');
  const [joinInviteCode, setJoinInviteCode] = useState<string>('');
  const [joinValidationResult, setJoinValidationResult] = useState<{ valid: boolean; company_name?: string; role?: string; detail?: string } | null>(null);
  const [isValidatingCode, setIsValidatingCode] = useState<boolean>(false);
  const [joinNotice, setJoinNotice] = useState<string | null>(null);

  // Company Settings & Invitations State (Owner Only)
  const [companySettings, setCompanySettings] = useState<CompanySettings | null>(null);
  const [pendingMembers, setPendingMembers] = useState<PendingMember[]>([]);
  const [invitations, setInvitations] = useState<InvitationItem[]>([]);
  const [showInviteModal, setShowInviteModal] = useState<boolean>(false);
  const [inviteRole, setInviteRole] = useState<string>('ATTENDING_PHYSICIAN');
  const [inviteMaxUses, setInviteMaxUses] = useState<number>(5);
  const [inviteExpiresDays, setInviteExpiresDays] = useState<number>(7);
  const [generatedInvite, setGeneratedInvite] = useState<InvitationItem | null>(null);
  const [copiedTenantId, setCopiedTenantId] = useState<boolean>(false);
  const [copiedCodeId, setCopiedCodeId] = useState<string | null>(null);

  // Selected values inside Modal
  const [modalTenant, setModalTenant] = useState<string>('tenant-001');
  const [modalRole, setModalRole] = useState<string>('CLINIC_OWNER');

  // Navigation tab
  type TabType = 'dashboard' | 'tasks' | 'checklists' | 'inventory' | 'rooms' | 'staff';
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');

  // Loading & State
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [checklists, setChecklists] = useState<ChecklistItem[]>([]);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [rooms, setRooms] = useState<RoomItem[]>([]);
  const [staff, setStaff] = useState<StaffItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Modals
  const [showTaskModal, setShowTaskModal] = useState(false);
  const [showEditTaskModal, setShowEditTaskModal] = useState(false);
  const [showChecklistModal, setShowChecklistModal] = useState(false);
  const [showInventoryModal, setShowInventoryModal] = useState(false);
  const [showInventoryImportModal, setShowInventoryImportModal] = useState(false);
  const [inventoryExpiryFilter, setInventoryExpiryFilter] = useState<InventoryExpiryFilter>('all');
  const [inventorySort, setInventorySort] = useState<InventorySort>('stock');
  const [inventoryView, setInventoryView] = useState<InventoryItem[] | null>(null);
  const [inventoryViewError, setInventoryViewError] = useState('');
  const [inventorySearch, setInventorySearch] = useState('');
  const [inventorySearchApplied, setInventorySearchApplied] = useState('');
  const [editingInventory, setEditingInventory] = useState<InventoryItem | null>(null);
  const [adjustingInventory, setAdjustingInventory] = useState<InventoryItem | null>(null);
  const [showRoomModal, setShowRoomModal] = useState(false);
  const [showPracticeModal, setShowPracticeModal] = useState(false);
  const [selectedStaffProfile, setSelectedStaffProfile] = useState<StaffItem | null>(null);
  const [showStaffProfileModal, setShowStaffProfileModal] = useState(false);

  // Practice & Location Context
  const [practice, setPractice] = useState<PracticeItem | null>(null);
  const [practiceForm, setPracticeForm] = useState({
    name: '',
    location: '',
    room_count: 0,
  });

  // Task Editing & Forms
  const [editingTask, setEditingTask] = useState<TaskItem | null>(null);
  const [editTaskForm, setEditTaskForm] = useState({
    title: '',
    description: '',
    priority: 'Medium',
    status: 'Pending',
    due_date: '2026-10-10 12:00',
    assigned_staff_id: '',
    room_id: '',
  });

  // Checklist Editing & Forms
  const [showEditChecklistModal, setShowEditChecklistModal] = useState(false);
  const [editingChecklist, setEditingChecklist] = useState<ChecklistItem | null>(null);
  const [editChecklistForm, setEditChecklistForm] = useState({
    title: '',
    category: 'Sterilization',
    frequency: 'Daily',
    assigned_staff_id: '',
  });

  // Dynamic RBAC Permission Flags & Normalized Role Hierarchy: OWNER > MANAGER > DOCTOR > NURSE
  const normalizedRole = (() => {
    const r = (userRole || '').toUpperCase();
    if (r === 'CLINIC_OWNER' || r === 'OWNER') return 'OWNER';
    if (r === 'INVENTORY_MANAGER' || r === 'MANAGER') return 'MANAGER';
    if (r === 'ATTENDING_PHYSICIAN' || r === 'DOCTOR' || r === 'PHYSICIAN') return 'DOCTOR';
    if (r === 'NURSE_STAFF' || r === 'NURSE') return 'NURSE';
    return r;
  })();

  const isOwner = isLoggedIn && normalizedRole === 'OWNER';
  const isManager = isLoggedIn && (normalizedRole === 'OWNER' || normalizedRole === 'MANAGER');
  const isDoctor = isLoggedIn && normalizedRole === 'DOCTOR';
  const isNurse = isLoggedIn && normalizedRole === 'NURSE';

  // Assignments reference staff ids, not user ids; resolve the logged-in user's linked staff records.
  const myStaffIds = new Set(staff.filter((s) => s.user_id && s.user_id === userId).map((s) => s.id));
  const isAssignedToMe = (assignedStaffId?: string | null) =>
    !!assignedStaffId && (assignedStaffId === userId || myStaffIds.has(assignedStaffId));

  // Tasks:
  const canCreateTask = isLoggedIn && (normalizedRole === 'OWNER' || normalizedRole === 'MANAGER' || normalizedRole === 'DOCTOR');
  const canEditTask = isLoggedIn && (normalizedRole === 'OWNER' || normalizedRole === 'MANAGER' || normalizedRole === 'DOCTOR');
  const canDeleteTask = isLoggedIn && (normalizedRole === 'OWNER' || normalizedRole === 'MANAGER' || normalizedRole === 'DOCTOR');
  // Per-record flags from the backend are authoritative; role checks below are only a fallback.
  const canEditTaskItem = (t: TaskItem) => (isLoggedIn ? t.can_edit ?? canEditTask : false);
  const canDeleteTaskItem = (t: TaskItem) => {
    if (!isLoggedIn) return false;
    if (typeof t.can_delete === 'boolean') return t.can_delete;
    if (normalizedRole === 'OWNER') return true;
    if (normalizedRole === 'MANAGER' || normalizedRole === 'DOCTOR') {
      return !isAssignedToMe(t.assigned_staff_id);
    }
    return false;
  };
  const canToggleTaskItem = (t: TaskItem) => {
    if (!isLoggedIn) return false;
    if (typeof t.can_complete === 'boolean') return t.can_complete;
    if (normalizedRole === 'OWNER' || normalizedRole === 'MANAGER' || normalizedRole === 'DOCTOR') return true;
    if (normalizedRole === 'NURSE') {
      return isAssignedToMe(t.assigned_staff_id);
    }
    return false;
  };

  // Checklists:
  const canCreateChecklist = isLoggedIn && (normalizedRole === 'OWNER' || normalizedRole === 'MANAGER' || normalizedRole === 'DOCTOR');
  const canEditChecklist = isLoggedIn && (normalizedRole === 'OWNER' || normalizedRole === 'MANAGER' || normalizedRole === 'DOCTOR');
  const canDeleteChecklist = isLoggedIn && (normalizedRole === 'OWNER' || normalizedRole === 'MANAGER' || normalizedRole === 'DOCTOR');
  const canEditChecklistItem = (c: ChecklistItem) => (isLoggedIn ? c.can_edit ?? canEditChecklist : false);
  const canDeleteChecklistItem = (c: ChecklistItem) => (isLoggedIn ? c.can_delete ?? canDeleteChecklist : false);
  const canToggleChecklistItem = (c: ChecklistItem) => {
    if (!isLoggedIn) return false;
    if (typeof c.can_toggle === 'boolean') return c.can_toggle;
    if (normalizedRole === 'OWNER' || normalizedRole === 'MANAGER' || normalizedRole === 'DOCTOR') return true;
    if (normalizedRole === 'NURSE') {
      return isAssignedToMe(c.assigned_staff_id);
    }
    return false;
  };

  // Inventory:
  const canManageInventory = isLoggedIn && (normalizedRole === 'OWNER' || normalizedRole === 'MANAGER');

  // Rooms:
  const canAddRoom = isLoggedIn && (normalizedRole === 'OWNER' || normalizedRole === 'MANAGER');
  const canUpdateRoomStatus = isLoggedIn && (normalizedRole === 'OWNER' || normalizedRole === 'MANAGER' || normalizedRole === 'DOCTOR');

  // Toast Notification
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'info' | 'error' } | null>(null);
  const showToast = (text: string, type: 'success' | 'info' | 'error' = 'success') => {
    setToastMessage({ text, type });
    setTimeout(() => {
      setToastMessage(null);
    }, 3200);
  };

  // ---------------------------------------------------------------------------
  // LangGraph Autonomous AI Operations Agent State & Handlers
  // ---------------------------------------------------------------------------
  interface AIMessage {
    role: 'user' | 'assistant';
    content: string;
    toolCalls?: { tool: string; status: string }[];
    metrics?: {
      total_latency_ms?: number;
      total_duration_ms?: number;
      tool_calls_count?: number;
      agent_mode?: string;
      model_name?: string;
      total_tokens?: number;
    };
    approvalPending?: {
      approval_id: string;
      tool_name: string;
      description: string;
      arguments: Record<string, any>;
    };
  }

  interface AIConversationItem {
    id: string;
    title: string;
    created_at: string;
    updated_at: string;
  }

  const defaultWelcomeMessage: AIMessage = {
    role: 'assistant',
    content:
      "👋 Welcome to **PractiCare's LangGraph Clinical AI Agent**.\n\nI can autonomously analyze team performance, identify overdue bottlenecks, monitor exam room turnover, search staff, and assist with clinical operations strictly bounded by your multi-tenant role.\n\nTry asking:\n* **I want to know how my team is performing the tasks.**\n* **Check our overdue tasks and identify the responsible staff.**\n* **Search for staff member Dr. Sarah**\n* **Which medical supplies or inventory items are running low?**",
  };

  const [showAICopilot, setShowAICopilot] = useState(false);
  const [aiInput, setAiInput] = useState('');
  const [aiMessages, setAiMessages] = useState<AIMessage[]>([defaultWelcomeMessage]);
  const [conversations, setConversations] = useState<AIConversationItem[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [showConversationList, setShowConversationList] = useState(false);
  const [isAILoading, setIsAILoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const fetchConversations = async () => {
    try {
      const res = await fetch(`${apiBase}/api/v1/ai/conversations`, {
        headers: getHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setConversations(data);
        }
      }
    } catch (e) {
      console.error('Failed to load private conversations:', e);
    }
  };

  useEffect(() => {
    if (showAICopilot && isLoggedIn) {
      fetchConversations();
    }
  }, [showAICopilot, isLoggedIn, tenantId, userId]);

  const handleSelectConversation = async (convId: string) => {
    setIsAILoading(true);
    setAiError(null);
    try {
      const res = await fetch(`${apiBase}/api/v1/ai/conversations/${convId}`, {
        headers: getHeaders(),
      });
      if (!res.ok) throw new Error('Failed to load conversation history');
      const data = await res.json();
      setActiveConversationId(data.id);
      if (data.messages && data.messages.length > 0) {
        setAiMessages(
          data.messages.map((m: any) => ({
            role: m.role,
            content: m.content,
            toolCalls: m.tool_calls || [],
            metrics: m.metrics || undefined,
            approvalPending: m.approval_pending || undefined,
          }))
        );
      } else {
        setAiMessages([defaultWelcomeMessage]);
      }
      setShowConversationList(false);
    } catch (err: any) {
      setAiError(err.message || 'Error opening conversation');
      showToast(err.message || 'Error opening conversation', 'info');
    } finally {
      setIsAILoading(false);
    }
  };

  const handleNewChat = () => {
    setActiveConversationId(null);
    setAiMessages([defaultWelcomeMessage]);
    setAiInput('');
    setAiError(null);
    setShowConversationList(false);
  };

  const handleDeleteConversation = async (convId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const res = await fetch(`${apiBase}/api/v1/ai/conversations/${convId}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });
      if (res.ok) {
        setConversations((prev) => prev.filter((c) => c.id !== convId));
        if (activeConversationId === convId) {
          handleNewChat();
        }
        showToast('Conversation deleted', 'success');
      }
    } catch (err) {
      showToast('Failed to delete conversation', 'info');
    }
  };

  const handleSendAIMessage = async (textToSend?: string) => {
    const prompt = (textToSend || aiInput).trim();
    if (!prompt || isAILoading) return;

    setAiInput('');
    setAiError(null);
    setIsAILoading(true);

    const userMsg: AIMessage = { role: 'user', content: prompt };
    setAiMessages((prev) => [...prev, userMsg]);

    try {
      const res = await fetch(`${apiBase}/api/v1/ai/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getHeaders(),
        },
        body: JSON.stringify({
          message: prompt,
          conversation_id: activeConversationId || undefined,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error (${res.status})`);
      }

      const data = await res.json();
      if (data.conversation_id) {
        setActiveConversationId(data.conversation_id);
        fetchConversations();
      }

      const assistantMsg: AIMessage = {
        role: 'assistant',
        content: data.reply,
        toolCalls: data.tool_calls_executed,
        metrics: data.metrics,
        approvalPending: data.approval_pending,
      };

      setAiMessages((prev) => [...prev, assistantMsg]);

      // If tools performed mutations (tasks, checklists), refresh live UI data
      if (data.tool_calls_executed && data.tool_calls_executed.length > 0) {
        fetchData();
      }
    } catch (err: any) {
      setAiError(err.message || 'Failed to communicate with LangGraph AI agent.');
      setAiMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `⚠️ **AI Service Error**: ${err.message || 'An unexpected error occurred while communicating with the LangGraph agent.'}`,
        },
      ]);
    } finally {
      setIsAILoading(false);
    }
  };

  const handleResolveApproval = async (approvalId: string, action: 'approve' | 'reject') => {
    setIsAILoading(true);
    try {
      const res = await fetch(`${apiBase}/api/v1/ai/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getHeaders(),
        },
        body: JSON.stringify({
          approval_id: approvalId,
          action,
        }),
      });

      const data = await res.json();
      if (!res.ok || data.success === false) {
        throw new Error(data.detail || 'Approval request failed.');
      }

      setAiMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            action === 'approve'
              ? `✅ **Approval Executed**: ${data.reply || data.detail}`
              : `❌ **Action Cancelled**: Operation rejected by user.`,
        },
      ]);

      showToast(action === 'approve' ? 'Action successfully executed' : 'Action cancelled', 'success');
      fetchData();
    } catch (err: any) {
      showToast(err.message || 'Approval resolution failed', 'info');
      setAiMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `⚠️ **Approval Error**: ${err.message}`,
        },
      ]);
    } finally {
      setIsAILoading(false);
    }
  };

  const renderFormattedInline = (text: string) => {
    const parts = text.split(/(\*\*.*?\*\*|`.*?`)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="font-semibold text-slate-900">{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith('`') && part.endsWith('`')) {
        return <code key={i} className="px-1 py-0.5 rounded bg-slate-100 text-slate-800 font-mono text-[11px]">{part.slice(1, -1)}</code>;
      }
      return part;
    });
  };

  const renderAIMarkdown = (text: string) => {
    return text.split('\n').map((line, idx) => {
      if (line.startsWith('### ')) {
        return <h4 key={idx} className="font-bold text-xs text-slate-800 mt-2 mb-1">{line.replace('### ', '')}</h4>;
      }
      if (line.startsWith('## ')) {
        return <h3 key={idx} className="font-bold text-sm text-slate-900 mt-2.5 mb-1 pb-1 border-b border-slate-100">{line.replace('## ', '')}</h3>;
      }
      if (line.startsWith('# ')) {
        return <h2 key={idx} className="font-bold text-base text-slate-900 mt-3 mb-1.5">{line.replace('# ', '')}</h2>;
      }
      if (line.startsWith('- ') || line.startsWith('* ')) {
        const item = line.replace(/^[-*]\s+/, '');
        return (
          <div key={idx} className="flex items-start gap-1.5 text-xs text-slate-700 my-0.5 pl-1">
            <span className="text-emerald-500 font-bold shrink-0">•</span>
            <span>{renderFormattedInline(item)}</span>
          </div>
        );
      }
      if (line.trim() === '') {
        return <div key={idx} className="h-1.5" />;
      }
      return <p key={idx} className="text-xs text-slate-700 my-0.5 leading-relaxed">{renderFormattedInline(line)}</p>;
    });
  };

  // Helper for dynamic headers
  const getHeaders = () => {
    let token = '';
    try {
      const sess = localStorage.getItem('practicare_auth_session');
      if (sess) {
        const parsed = JSON.parse(sess);
        token = parsed.token || '';
      }
    } catch (e) {}

    const headers: Record<string, string> = {};
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    return headers;
  };

  // Forms
  const [taskForm, setTaskForm] = useState({
    title: '',
    description: '',
    priority: 'Medium',
    due_date: '2026-10-10 12:00',
    assigned_staff_id: '',
    room_id: '',
  });

  const [checklistForm, setChecklistForm] = useState({
    title: '',
    category: 'Sterilization',
    frequency: 'Daily',
    assigned_staff_id: '',
  });

  const [inventoryForm, setInventoryForm] = useState({
    item_name: '',
    current_stock: 10,
    min_threshold: 20,
    unit: 'boxes',
    expiry_date: '2027-12-31',
    room_id: '',
    supplier: '',
    batch_number: '',
    purchase_price: '',
  });

  const [roomForm, setRoomForm] = useState({
    room_number: '',
    name: '',
    room_type: 'Exam',
    status: 'Available',
  });

  // Mount Session Restoration
  useEffect(() => {
    const timer = setTimeout(() => {
      setIsSessionChecked(true);
    }, 2000);

    try {
      const saved = localStorage.getItem('practicare_auth_session');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed?.user) {
          setTenantId(parsed.user.tenant_id);
          setUserRole(parsed.user.role);
          setUserId(parsed.user.id);
          setUserName(parsed.user.name);
          setCompanyName(parsed.user.company_name || parsed.user.tenant_id);
          setIsLoggedIn(true);
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
      clearTimeout(timer);
    }

    return () => clearTimeout(timer);
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
        localStorage.setItem('practicare_auth_session', JSON.stringify({ token: data.access_token, user: data.user }));
        // Purge any prior tenant data immediately to prevent cross-tenant UI leakage
        setSummary(null);
        setTasks([]);
        setChecklists([]);
        setInventory([]);
        setRooms([]);
        setStaff([]);
        setPractice(null);
        setCompanySettings(null);
        setPendingMembers([]);
        setInvitations([]);
        setSelectedStaffProfile(null);

        setTenantId(data.user.tenant_id);
        setUserRole(data.user.role);
        setUserId(data.user.id);
        setUserName(data.user.name);
        setCompanyName(data.user.company_name || data.user.tenant_id);
        setIsLoggedIn(true);
        setShowAuthModal(false);
        showToast(`Welcome back, ${data.user.name}!`, 'success');
      }
    } catch (err: any) {
      setAuthError('Unable to connect to authentication backend.');
    } finally {
      setIsAuthLoading(false);
    }
  };

  const handleAuthRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError(null);

    if (signupPath === 'join_company') {
      // Path B: Join Existing Practice via Invitation Code
      if (!joinInviteCode.trim() || !registerFullName.trim() || !registerEmail.trim() || !registerPassword.trim()) {
        setAuthError('Please fill in all fields including a valid Invitation Code.');
        return;
      }
      setIsAuthLoading(true);
      try {
        const res = await fetch(`${apiBase}/api/v1/auth/join`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            full_name: registerFullName.trim(),
            email: registerEmail.trim(),
            password: registerPassword,
            invitation_code: joinInviteCode.trim().toUpperCase(),
          }),
        });
        const data = await res.json();
        if (!res.ok) {
          setAuthError(data.detail || 'Registration failed.');
          showToast(data.detail || 'Registration failed', 'info');
        } else {
          setJoinNotice(data.detail || 'Registration submitted! Your membership is pending Owner approval.');
          setLoginEmail(registerEmail.trim());
          setLoginPassword('');
          setAuthTab('signin');
          showToast('Join request submitted! Awaiting clinic Owner approval.', 'success');
        }
      } catch (err: any) {
        setAuthError('Unable to connect to authentication backend.');
      } finally {
        setIsAuthLoading(false);
      }
    } else {
      // Path A: Register New Practice & Owner Account
      if (!registerFullName.trim() || !registerEmail.trim() || !registerPassword.trim() || !registerCompany.trim()) {
        setAuthError('Please provide your Full Name, Clinic / Company Name, Email, and Password.');
        return;
      }
      setIsAuthLoading(true);
      try {
        const res = await fetch(`${apiBase}/api/v1/auth/register-company`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            full_name: registerFullName.trim(),
            email: registerEmail.trim(),
            password: registerPassword,
            company_name: registerCompany.trim(),
          }),
        });
        const data = await res.json();
        if (!res.ok) {
          setAuthError(data.detail || 'Company registration failed.');
          showToast(data.detail || 'Registration failed', 'info');
        } else {
          localStorage.setItem('practicare_auth_session', JSON.stringify({ token: data.access_token, user: data.user }));
          // Purge any prior tenant data immediately to prevent cross-tenant UI leakage
          setSummary(null);
          setTasks([]);
          setChecklists([]);
          setInventory([]);
          setRooms([]);
          setStaff([]);
          setPractice(null);
          setCompanySettings(null);
          setPendingMembers([]);
          setInvitations([]);
          setSelectedStaffProfile(null);

          setTenantId(data.user.tenant_id);
          setUserRole(data.user.role);
          setUserId(data.user.id);
          setUserName(data.user.name);
          setCompanyName(data.user.company_name || data.user.tenant_id);
          setIsLoggedIn(true);
          setShowAuthModal(false);
          showToast(`Practice created: ${data.user.company_name}!`, 'success');
        }
      } catch (err: any) {
        setAuthError('Unable to connect to authentication backend.');
      } finally {
        setIsAuthLoading(false);
      }
    }
  };

  const handleValidateCode = async (codeToCheck?: string) => {
    const code = (codeToCheck || joinInviteCode).trim().toUpperCase();
    if (!code) {
      showToast('Please enter an invitation code to validate.', 'info');
      return;
    }
    setIsValidatingCode(true);
    try {
      const res = await fetch(`${apiBase}/api/v1/invitations/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      });
      const data = await res.json();
      setJoinValidationResult(data);
      if (data.valid) {
        showToast(`Verified! Practice: ${data.company_name} (${data.role})`, 'success');
      } else {
        showToast(data.detail || 'Invalid or expired invitation code.', 'info');
      }
    } catch (e: any) {
      showToast('Network error validating invitation code.', 'info');
    } finally {
      setIsValidatingCode(false);
    }
  };

  const handleApproveMember = async (targetUserId: string) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/company/pending-members/${targetUserId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getHeaders() },
        body: JSON.stringify({ action: 'APPROVE' }),
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.detail || 'Approval failed.', 'info');
      } else {
        showToast(data.detail || 'Staff member approved and onboarded!', 'success');
        fetchData();
      }
    } catch (e: any) {
      showToast('Network error approving member.', 'info');
    }
  };

  const handleRejectMember = async (targetUserId: string) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/company/pending-members/${targetUserId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getHeaders() },
        body: JSON.stringify({ action: 'REJECT' }),
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.detail || 'Rejection failed.', 'info');
      } else {
        showToast(data.detail || 'Join request rejected.', 'success');
        fetchData();
      }
    } catch (e: any) {
      showToast('Network error rejecting member.', 'info');
    }
  };

  const handleCreateInvitation = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${apiBase}/api/v1/company/invitations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getHeaders() },
        body: JSON.stringify({
          role: inviteRole,
          max_uses: Number(inviteMaxUses),
          expires_in_days: Number(inviteExpiresDays),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.detail || 'Failed to create invitation.', 'info');
      } else {
        setGeneratedInvite(data);
        showToast(`Invitation code created: ${data.code}`, 'success');
        fetchData();
      }
    } catch (e: any) {
      showToast('Network error creating invitation.', 'info');
    }
  };

  const handleRevokeInvitation = async (invId: string) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/company/invitations/${invId}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.detail || 'Failed to revoke invitation.', 'info');
      } else {
        showToast(data.message || 'Invitation revoked.', 'success');
        fetchData();
      }
    } catch (e: any) {
      showToast('Network error revoking invitation.', 'info');
    }
  };

  // Session Switching with Complete Privacy State Isolation
  const handleSwitchSession = async (newTenant: string, newRole: string) => {
    // 1. Immediately purge all in-memory AI conversation state to prevent cross-account leakage
    setAiMessages([defaultWelcomeMessage]);
    setConversations([]);
    setActiveConversationId(null);
    setAiInput('');
    setAiError(null);

    setSummary(null);
    setTasks([]);
    setChecklists([]);
    setInventory([]);
    setRooms([]);
    setStaff([]);
    setPractice(null);

    // Map profiles to seeded demo accounts. No fallback: an unmapped profile must never
    // sign in as a different user (previously tenant-002 Manager became the tenant-001 Owner).
    const DEMO_ACCOUNTS: Record<string, Record<string, string>> = {
      'tenant-001': {
        CLINIC_OWNER: 'owner@vanguardclinic.com',
        ATTENDING_PHYSICIAN: 'doctor@vanguardclinic.com',
        NURSE_STAFF: 'nurse@vanguardclinic.com',
        INVENTORY_MANAGER: 'inv@vanguardclinic.com',
      },
      'tenant-002': {
        CLINIC_OWNER: 'owner@metrohealth.com',
        ATTENDING_PHYSICIAN: 'doctor@metrohealth.com',
        NURSE_STAFF: 'nurse@metrohealth.com',
      },
    };
    const email = DEMO_ACCOUNTS[newTenant]?.[newRole];
    if (!email) {
      handleSignOut();
      setShowAuthModal(true);
      showToast('No demo account is configured for this profile. Please sign in with real credentials.', 'error');
      return;
    }

    try {
      const res = await fetch(`${apiBase}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: 'password123' }),
      });
      if (res.ok) {
        const data = await res.json();
        localStorage.setItem('practicare_auth_session', JSON.stringify({ token: data.access_token, user: data.user }));
        setTenantId(data.user.tenant_id);
        setUserRole(data.user.role);
        setUserId(data.user.id);
        setUserName(data.user.name);
        setCompanyName(data.user.company_name || data.user.tenant_id);
        setIsLoggedIn(true);
        setShowAuthModal(false);
        showToast(`Switched to ${data.user.name} (${data.user.role}) at ${data.user.company_name}`, 'success');
        return;
      }
    } catch (e) {
      console.warn('Backend login fallback on switch:', e);
    }

    handleSignOut();
    setShowAuthModal(true);
    showToast('Unable to authenticate the selected profile.', 'info');
  };

  const handleSignOut = () => {
    localStorage.removeItem('practicare_auth_session');
    // Clear all private AI conversation data
    setAiMessages([defaultWelcomeMessage]);
    setConversations([]);
    setActiveConversationId(null);
    setAiInput('');
    setAiError(null);

    setSummary(null);
    setTasks([]);
    setChecklists([]);
    setInventory([]);
    setRooms([]);
    setStaff([]);
    setPractice(null);
    setIsLoggedIn(false);
    setUserRole('GUEST');
    setUserName('Guest User');
    setCompanyName('');
    showToast('Signed out of session. Session and AI conversation data purged.', 'info');
  };

  // Initial & Reactive Fetch
  const fetchData = async () => {
    setIsLoading(true);
    const headers = getHeaders();

    try {
      const [sumRes, taskRes, chkRes, invRes, rmRes, stfRes, pracRes] = await Promise.all([
        fetch(`${apiBase}/api/v1/dashboard/summary`, { headers }).then((r) => r.json()).catch(() => null),
        fetch(`${apiBase}/api/v1/tasks`, { headers }).then((r) => r.json()).catch(() => []),
        fetch(`${apiBase}/api/v1/checklists`, { headers }).then((r) => r.json()).catch(() => []),
        fetch(`${apiBase}/api/v1/inventory`, { headers }).then((r) => r.json()).catch(() => []),
        fetch(`${apiBase}/api/v1/rooms`, { headers }).then((r) => r.json()).catch(() => []),
        fetch(`${apiBase}/api/v1/staff`, { headers }).then((r) => r.json()).catch(() => []),
        fetch(`${apiBase}/api/v1/practice`, { headers }).then((r) => r.json()).catch(() => null),
      ]);

      setSummary(sumRes && !sumRes.detail ? sumRes : null);
      if (Array.isArray(taskRes)) setTasks(taskRes);
      else setTasks([]);
      if (Array.isArray(chkRes)) setChecklists(chkRes);
      else setChecklists([]);
      if (Array.isArray(invRes)) setInventory(invRes);
      else setInventory([]);
      if (Array.isArray(rmRes)) setRooms(rmRes);
      else setRooms([]);
      if (Array.isArray(stfRes)) {
        setStaff(stfRes);
        setSelectedStaffProfile((prev) => {
          if (!prev) return null;
          const updated = stfRes.find((s: StaffItem) => s.id === prev.id);
          return updated || prev;
        });
      } else {
        setStaff([]);
      }
      if (pracRes && !pracRes.detail) {
        setPractice(pracRes);
        setPracticeForm({
          name: pracRes.name,
          location: pracRes.location,
          room_count: pracRes.room_count,
        });
      } else {
        setPractice(null);
      }
      if (userRole === 'CLINIC_OWNER') {
        const [settingsRes, pendingRes, invsRes] = await Promise.all([
          fetch(`${apiBase}/api/v1/company/settings`, { headers }).then((r) => r.json()).catch(() => null),
          fetch(`${apiBase}/api/v1/company/pending-members`, { headers }).then((r) => r.json()).catch(() => []),
          fetch(`${apiBase}/api/v1/company/invitations`, { headers }).then((r) => r.json()).catch(() => []),
        ]);
        setCompanySettings(settingsRes && !settingsRes.detail ? settingsRes : null);
        setPendingMembers(Array.isArray(pendingRes) ? pendingRes : []);
        setInvitations(Array.isArray(invsRes) ? invsRes : []);
      } else {
        setCompanySettings(null);
        setPendingMembers([]);
        setInvitations([]);
      }
    } catch (e) {
      console.error('Failed to load clinic data:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isLoggedIn) {
      fetchData();
    }
  }, [tenantId, userRole, isLoggedIn]);

  // Inventory tab: the backend applies the expiry filter and sort to real data. Re-runs after every
  // fetchData() (the `inventory` dependency), so creates and imports show up immediately.
  useEffect(() => {
    if (!isLoggedIn || activeTab !== 'inventory') return;
    let cancelled = false;
    const params = new URLSearchParams({ expiry: inventoryExpiryFilter, sort: inventorySort });
    if (inventorySearchApplied.trim()) params.set('search', inventorySearchApplied.trim());
    fetch(`${apiBase}/api/v1/inventory?${params.toString()}`, { headers: getHeaders() })
      .then(async (r) => {
        const data = await r.json().catch(() => null);
        if (cancelled) return;
        if (r.ok && Array.isArray(data)) {
          setInventoryView(data);
          setInventoryViewError('');
        } else {
          setInventoryView(null);
          setInventoryViewError((data && typeof data.detail === 'string' && data.detail) || 'Could not load filtered inventory.');
        }
      })
      .catch(() => {
        if (!cancelled) setInventoryViewError('Could not load filtered inventory.');
      });
    return () => {
      cancelled = true;
    };
  }, [isLoggedIn, activeTab, inventoryExpiryFilter, inventorySort, inventorySearchApplied, inventory]);

  // Debounce the inventory search box so each keystroke does not hit the API
  useEffect(() => {
    const t = setTimeout(() => setInventorySearchApplied(inventorySearch), 300);
    return () => clearTimeout(t);
  }, [inventorySearch]);

  // Backend flag first; role check only as a fallback for older responses (backend enforces either way)
  const canManageInventoryItem = (inv: InventoryItem) => (typeof inv.can_manage === 'boolean' ? inv.can_manage : canManageInventory);

  // Task Actions
  const handleToggleTask = async (task: TaskItem) => {
    if (!isLoggedIn) {
      showToast('Please sign in to update tasks.', 'info');
      setShowAuthModal(true);
      return;
    }
    if (!canToggleTaskItem(task)) {
      showToast('Permission denied: You can only complete tasks assigned to yourself.', 'error');
      return;
    }
    const nextStatus = task.status.toLowerCase() === 'completed' ? 'Pending' : 'Completed';
    // Optimistic
    setTasks((prev) =>
      prev.map((t) => (t.id === task.id ? { ...t, status: nextStatus } : t))
    );

    try {
      const res = await fetch(`${apiBase}/api/v1/tasks/${task.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...getHeaders(),
        },
        body: JSON.stringify({ status: nextStatus }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission denied', 'info');
      }
      fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!taskForm.title) return;
    if (!isLoggedIn) {
      showToast('Please sign in to create tasks.', 'info');
      setShowAuthModal(true);
      return;
    }
    if (!canCreateTask) {
      showToast('Permission denied: You do not have permission to create tasks.', 'error');
      return;
    }

    try {
      const res = await fetch(`${apiBase}/api/v1/tasks`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getHeaders(),
        },
        body: JSON.stringify({
          ...taskForm,
          status: 'Pending',
          assigned_staff_id: taskForm.assigned_staff_id || null,
          room_id: taskForm.room_id || null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Operation not permitted', 'info');
      } else {
        setShowTaskModal(false);
        setTaskForm({
          title: '',
          description: '',
          priority: 'Medium',
          due_date: '2026-10-10 12:00',
          assigned_staff_id: '',
          room_id: '',
        });
        showToast('Task added successfully', 'success');
      }
      fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteTask = async (id: string) => {
    if (!isLoggedIn) {
      showToast('Please sign in to delete tasks.', 'info');
      setShowAuthModal(true);
      return;
    }
    const targetTask = tasks.find((t) => t.id === id);
    if (targetTask && !canDeleteTaskItem(targetTask)) {
      showToast('Permission denied: You cannot delete a task assigned to yourself.', 'error');
      return;
    }
    if (!canDeleteTask) {
      showToast('Permission denied: You do not have permission to delete tasks.', 'error');
      return;
    }
    try {
      const res = await fetch(`${apiBase}/api/v1/tasks/${id}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission denied: Cannot delete task', 'info');
      } else {
        setTasks((prev) => prev.filter((t) => t.id !== id));
        showToast('Task deleted successfully', 'success');
      }
      fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  const handleOpenEditTask = (task: TaskItem) => {
    if (!canEditTaskItem(task)) {
      showToast('Permission denied: You do not have permission to edit tasks.', 'error');
      return;
    }
    setEditingTask(task);
    setEditTaskForm({
      title: task.title,
      description: task.description || '',
      priority: task.priority || 'Medium',
      status: task.status || 'Pending',
      due_date: task.due_date || '',
      assigned_staff_id: task.assigned_staff_id || '',
      room_id: task.room_id || '',
    });
    setShowEditTaskModal(true);
  };

  const handleUpdateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingTask || !editTaskForm.title) return;
    try {
      const res = await fetch(`${apiBase}/api/v1/tasks/${editingTask.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...getHeaders(),
        },
        body: JSON.stringify({
          title: editTaskForm.title,
          description: editTaskForm.description,
          priority: editTaskForm.priority,
          status: editTaskForm.status,
          due_date: editTaskForm.due_date,
          assigned_staff_id: editTaskForm.assigned_staff_id || null,
          room_id: editTaskForm.room_id || null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission denied: Cannot edit task', 'info');
      } else {
        setShowEditTaskModal(false);
        setEditingTask(null);
        showToast('Task updated successfully', 'success');
        fetchData();
      }
    } catch (e) {
      console.error(e);
      showToast('Error updating task', 'info');
    }
  };

  // Checklist Actions
  const handleToggleChecklist = async (chk: ChecklistItem) => {
    if (!isLoggedIn) {
      showToast('Please sign in to update checklists.', 'info');
      setShowAuthModal(true);
      return;
    }
    if (!canToggleChecklistItem(chk)) {
      showToast('Permission denied: Nurses can only fill or complete checklists assigned to themselves.', 'error');
      return;
    }
    const nextVal = !chk.is_completed;
    setChecklists((prev) =>
      prev.map((c) => (c.id === chk.id ? { ...c, is_completed: nextVal } : c))
    );

    try {
      const res = await fetch(`${apiBase}/api/v1/checklists/${chk.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...getHeaders(),
        },
        body: JSON.stringify({ is_completed: nextVal }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission denied: Cannot modify checklist', 'error');
      }
      fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  const handleCreateChecklist = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!checklistForm.title) return;
    if (!canCreateChecklist) {
      showToast('Permission denied: You do not have permission to create checklists.', 'error');
      return;
    }

    try {
      const res = await fetch(`${apiBase}/api/v1/checklists`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getHeaders(),
        },
        body: JSON.stringify({
          ...checklistForm,
          is_completed: false,
          assigned_staff_id: checklistForm.assigned_staff_id || null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Operation not permitted', 'info');
      } else {
        setShowChecklistModal(false);
        setChecklistForm({
          title: '',
          category: 'Sterilization',
          frequency: 'Daily',
          assigned_staff_id: '',
        });
        showToast('Checklist created successfully', 'success');
        fetchData();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleOpenEditChecklist = (chk: ChecklistItem) => {
    if (!canEditChecklistItem(chk)) {
      showToast('Permission denied: You cannot edit checklist definitions.', 'error');
      return;
    }
    setEditingChecklist(chk);
    setEditChecklistForm({
      title: chk.title,
      category: chk.category || 'Sterilization',
      frequency: chk.frequency || 'Daily',
      assigned_staff_id: chk.assigned_staff_id || '',
    });
    setShowEditChecklistModal(true);
  };

  const handleUpdateChecklist = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingChecklist || !editChecklistForm.title) return;
    try {
      const res = await fetch(`${apiBase}/api/v1/checklists/${editingChecklist.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...getHeaders(),
        },
        body: JSON.stringify({
          title: editChecklistForm.title,
          category: editChecklistForm.category,
          frequency: editChecklistForm.frequency,
          assigned_staff_id: editChecklistForm.assigned_staff_id || null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission denied: Cannot edit checklist', 'info');
      } else {
        setShowEditChecklistModal(false);
        setEditingChecklist(null);
        showToast('Checklist updated successfully', 'success');
        fetchData();
      }
    } catch (e) {
      console.error(e);
      showToast('Error updating checklist', 'info');
    }
  };

  const handleDeleteChecklist = async (id: string) => {
    if (!isLoggedIn) {
      showToast('Please sign in to delete checklists.', 'info');
      setShowAuthModal(true);
      return;
    }
    const targetChecklist = checklists.find((c) => c.id === id);
    if (targetChecklist ? !canDeleteChecklistItem(targetChecklist) : !canDeleteChecklist) {
      showToast('Permission denied: You do not have permission to delete checklists.', 'error');
      return;
    }
    if (!window.confirm('Are you sure you want to delete this safety checklist item?')) {
      return;
    }
    try {
      const res = await fetch(`${apiBase}/api/v1/checklists/${id}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission denied: Cannot delete checklist', 'info');
      } else {
        setChecklists((prev) => prev.filter((c) => c.id !== id));
        showToast('Checklist item deleted successfully', 'success');
        fetchData();
      }
    } catch (e) {
      console.error(e);
      showToast('Error deleting checklist', 'info');
    }
  };

  // Inventory Actions
  const handleCreateInventory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inventoryForm.item_name) return;
    if (!canManageInventory) {
      showToast('Permission denied: Only Owner or Manager can manage inventory.', 'error');
      return;
    }

    try {
      const res = await fetch(`${apiBase}/api/v1/inventory`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getHeaders() },
        body: JSON.stringify({
          ...inventoryForm,
          room_id: inventoryForm.room_id || null,
          expiry_date: inventoryForm.expiry_date || null,
          supplier: inventoryForm.supplier.trim() || null,
          batch_number: inventoryForm.batch_number.trim() || null,
          purchase_price: inventoryForm.purchase_price.trim() || null,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const detail = Array.isArray(err.detail) ? err.detail.map((d: { msg?: string }) => d.msg).join('; ') : err.detail;
        showToast(detail || 'Inventory item was not saved.', 'error');
        return;
      }
      setShowInventoryModal(false);
      setInventoryForm({
        item_name: '',
        current_stock: 10,
        min_threshold: 20,
        unit: 'boxes',
        expiry_date: '2027-12-31',
        room_id: '',
        supplier: '',
        batch_number: '',
        purchase_price: '',
      });
      showToast('Inventory item added', 'success');
      fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  // Room Status Quick Update
  const handleUpdateRoomStatus = async (roomId: string, newStatus: string) => {
    if (!canUpdateRoomStatus) {
      showToast('Permission denied: Nurse staff have read-only room access.', 'error');
      return;
    }
    setRooms((prev) =>
      prev.map((r) => (r.id === roomId ? { ...r, status: newStatus } : r))
    );

    try {
      await fetch(`${apiBase}/api/v1/rooms/${roomId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...getHeaders() },
        body: JSON.stringify({ status: newStatus }),
      });
      fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  const handleCreateRoom = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!roomForm.room_number) return;
    if (!canAddRoom) {
      showToast('Permission denied: Only Owner or Manager can add rooms.', 'error');
      return;
    }

    try {
      await fetch(`${apiBase}/api/v1/rooms`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getHeaders() },
        body: JSON.stringify(roomForm),
      });
      setShowRoomModal(false);
      setRoomForm({
        room_number: '',
        name: '',
        room_type: 'Exam',
        status: 'Available',
      });
      fetchData();
    } catch (e) {
      console.error(e);
    }
  };

  const handleToggleStaffStatus = async (staffId: string, currentActive: boolean) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/staff/${staffId}/status`, {
        method: 'PUT',
        headers: {
          ...getHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ is_active: !currentActive }),
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.detail || 'Failed to update staff account status.', 'error');
        return;
      }
      showToast(`Staff account status updated to ${!currentActive ? 'Active' : 'Inactive'}.`, 'success');
      setSelectedStaffProfile((prev) => (prev && prev.id === staffId ? { ...prev, is_active: !currentActive } : prev));
      fetchData();
    } catch (e) {
      showToast('Error updating staff account status.', 'error');
    }
  };

  const handleToggleStaffShift = async (staffId: string, currentShift: boolean) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/staff/${staffId}/shift`, {
        method: 'PUT',
        headers: {
          ...getHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ on_shift: !currentShift }),
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.detail || 'Failed to update shift status.', 'error');
        return;
      }
      showToast(`Shift status updated to ${!currentShift ? 'On Shift' : 'Off Duty'}.`, 'success');
      setSelectedStaffProfile((prev) => (prev && prev.id === staffId ? { ...prev, on_shift: !currentShift } : prev));
      fetchData();
    } catch (e) {
      showToast('Error updating shift status.', 'error');
    }
  };

  const handleSelfShiftToggle = async (currentShift: boolean) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/staff/me/shift`, {
        method: 'POST',
        headers: {
          ...getHeaders(),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ on_shift: !currentShift }),
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.detail || 'Failed to update shift status.', 'error');
        return;
      }
      showToast(`Your shift status is now ${!currentShift ? 'On Shift' : 'Off Duty'}.`, 'success');
      setSelectedStaffProfile((prev) => (prev ? { ...prev, on_shift: !currentShift } : prev));
      fetchData();
    } catch (e) {
      showToast('Error updating your shift status.', 'error');
    }
  };

  if (!isSessionChecked) {
    return (
      <div className="min-h-screen w-screen flex flex-col items-center justify-center bg-slate-950 text-emerald-400 gap-3 p-4">
        <RefreshCw className="w-8 h-8 animate-spin" />
        <p className="text-xs text-slate-400 font-medium">Initializing PractiCare Clinical SaaS...</p>
        <button
          type="button"
          onClick={() => setIsSessionChecked(true)}
          className="mt-2 text-xs px-3.5 py-1.5 rounded-lg bg-slate-900 text-slate-300 hover:text-white hover:bg-slate-800 border border-slate-800 transition"
        >
          Continue to Portal
        </button>
      </div>
    );
  }

  if (isSessionChecked && !isLoggedIn) {
    return (
      <div className="min-h-screen w-screen flex flex-col items-center justify-center bg-gradient-to-br from-slate-950 via-slate-900 to-teal-950 text-slate-100 p-6 relative overflow-y-auto">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-teal-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col items-center mb-6 text-center z-10">
          <div className="h-14 w-14 rounded-2xl bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center text-white shadow-xl shadow-emerald-500/25 mb-3 border border-emerald-400/30">
            <Stethoscope className="w-7 h-7" />
          </div>
          <h1 className="text-2xl font-black tracking-tight text-white flex items-center gap-2">
            PractiCare <span className="text-emerald-400 font-medium text-xs px-2 py-0.5 rounded-full bg-emerald-950/80 border border-emerald-500/30">Clinical SaaS</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1 max-w-sm">
            Enterprise Clinical Operations, Staff Scheduling & Inventory Suite with Strict PostgreSQL 16 Multi-Tenant Isolation
          </p>
        </div>

        <div className="w-full max-w-md bg-slate-900/80 border border-slate-800 rounded-2xl shadow-2xl backdrop-blur-xl p-6 z-10">
          <div className="flex p-1 bg-slate-800/80 rounded-xl mb-5 border border-slate-700/60">
            <button
              onClick={() => { setAuthTab('signin'); setAuthError(null); }}
              className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
                authTab === 'signin'
                  ? 'bg-emerald-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setAuthTab('signup'); setAuthError(null); }}
              className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
                authTab === 'signup'
                  ? 'bg-emerald-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Sign Up
            </button>
          </div>

          {joinNotice && (
            <div className="mb-4 p-3 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-xs flex items-start gap-2 animate-in fade-in">
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400 mt-0.5" />
              <span>{joinNotice}</span>
            </div>
          )}

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
                  placeholder="doctor@vanguardclinic.com"
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
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
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                />
              </div>

              <button
                type="submit"
                disabled={isAuthLoading}
                className="w-full mt-2 py-2.5 px-4 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold text-xs rounded-xl shadow-lg shadow-emerald-600/30 transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                {isAuthLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
                <span>{isAuthLoading ? 'Authenticating...' : 'Sign In to Workspace'}</span>
              </button>
            </form>
          ) : (
            <div className="space-y-3.5">
              {/* Dual-Path Registration Selector */}
              <div className="grid grid-cols-2 gap-2 p-1 bg-slate-950/60 rounded-xl border border-slate-800">
                <button
                  type="button"
                  onClick={() => { setSignupPath('create_company'); setAuthError(null); }}
                  className={`py-1.5 px-2 text-[11px] font-semibold rounded-lg transition-all ${
                    signupPath === 'create_company'
                      ? 'bg-slate-800 text-emerald-400 border border-emerald-500/30 shadow-xs'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Create New Practice
                </button>
                <button
                  type="button"
                  onClick={() => { setSignupPath('join_company'); setAuthError(null); }}
                  className={`py-1.5 px-2 text-[11px] font-semibold rounded-lg transition-all ${
                    signupPath === 'join_company'
                      ? 'bg-slate-800 text-teal-400 border border-teal-500/30 shadow-xs'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Join via Invitation
                </button>
              </div>

              {signupPath === 'create_company' ? (
                /* PATH A: Register New Practice & Owner */
                <form onSubmit={handleAuthRegister} className="space-y-3">
                  <div>
                    <label className="block text-[11px] font-medium text-slate-300 mb-1">Clinic / Practice Name *</label>
                    <input
                      type="text"
                      required
                      value={registerCompany}
                      onChange={(e) => setRegisterCompany(e.target.value)}
                      placeholder="e.g. Apex Medical Associates"
                      className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                    />
                    <p className="text-[10px] text-slate-400 mt-0.5">A unique server-side Tenant ID will be generated automatically.</p>
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-slate-300 mb-1">Owner Full Name *</label>
                    <input
                      type="text"
                      required
                      value={registerFullName}
                      onChange={(e) => setRegisterFullName(e.target.value)}
                      placeholder="e.g. Dr. Sarah Chen"
                      className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[11px] font-medium text-slate-300 mb-1">Email *</label>
                      <input
                        type="email"
                        required
                        value={registerEmail}
                        onChange={(e) => setRegisterEmail(e.target.value)}
                        placeholder="sarah@apex.org"
                        className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-slate-300 mb-1">Password *</label>
                      <input
                        type="password"
                        required
                        value={registerPassword}
                        onChange={(e) => setRegisterPassword(e.target.value)}
                        placeholder="••••••••"
                        className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                      />
                    </div>
                  </div>

                  <div className="p-2.5 rounded-xl bg-slate-800/50 border border-slate-700/60 flex items-center justify-between text-xs text-slate-300">
                    <span>Role Assignment:</span>
                    <span className="font-bold text-emerald-400 font-mono text-[11px] bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-500/30">
                      CLINIC_OWNER (Admin)
                    </span>
                  </div>

                  <button
                    type="submit"
                    disabled={isAuthLoading}
                    className="w-full mt-2 py-2.5 px-4 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold text-xs rounded-xl shadow-lg shadow-emerald-600/30 transition-all flex items-center justify-center gap-2 cursor-pointer"
                  >
                    {isAuthLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                    <span>{isAuthLoading ? 'Creating Practice...' : 'Create Practice & Owner Account'}</span>
                  </button>
                </form>
              ) : (
                /* PATH B: Join Existing Practice via Invitation */
                <form onSubmit={handleAuthRegister} className="space-y-3">
                  <div>
                    <label className="block text-[11px] font-medium text-slate-300 mb-1">Invitation Code *</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        required
                        value={joinInviteCode}
                        onChange={(e) => {
                          setJoinInviteCode(e.target.value.toUpperCase());
                          setJoinValidationResult(null);
                        }}
                        placeholder="INV-XXXX-XXXX"
                        className="flex-1 px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white font-mono placeholder-slate-500 uppercase tracking-wider focus:outline-none focus:border-teal-500"
                      />
                      <button
                        type="button"
                        onClick={() => handleValidateCode()}
                        disabled={isValidatingCode || !joinInviteCode.trim()}
                        className="px-3 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white text-xs font-semibold rounded-xl transition-colors cursor-pointer shrink-0"
                      >
                        {isValidatingCode ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : 'Validate'}
                      </button>
                    </div>

                    {joinValidationResult && (
                      <div className={`mt-2 p-2 rounded-lg text-[11px] border ${
                        joinValidationResult.valid
                          ? 'bg-teal-950/60 border-teal-500/40 text-teal-300'
                          : 'bg-rose-950/60 border-rose-500/40 text-rose-300'
                      }`}>
                        {joinValidationResult.valid ? (
                          <div className="flex items-center justify-between">
                            <span>Practice: <strong>{joinValidationResult.company_name}</strong></span>
                            <span className="font-mono text-[10px] bg-teal-900/80 px-1.5 py-0.5 rounded text-teal-200">
                              {joinValidationResult.role}
                            </span>
                          </div>
                        ) : (
                          <span>{joinValidationResult.detail || 'Invalid or expired invitation code.'}</span>
                        )}
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-slate-300 mb-1">Full Name *</label>
                    <input
                      type="text"
                      required
                      value={registerFullName}
                      onChange={(e) => setRegisterFullName(e.target.value)}
                      placeholder="e.g. Dr. Gregory House"
                      className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-teal-500"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[11px] font-medium text-slate-300 mb-1">Email *</label>
                      <input
                        type="email"
                        required
                        value={registerEmail}
                        onChange={(e) => setRegisterEmail(e.target.value)}
                        placeholder="house@clinic.org"
                        className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-teal-500"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-slate-300 mb-1">Password *</label>
                      <input
                        type="password"
                        required
                        value={registerPassword}
                        onChange={(e) => setRegisterPassword(e.target.value)}
                        placeholder="••••••••"
                        className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-teal-500"
                      />
                    </div>
                  </div>

                  <div className="p-2.5 rounded-xl bg-slate-900/70 border border-slate-800 text-[11px] text-slate-400">
                    <p>🔒 Joining will register your account in <strong>Pending</strong> status. The clinic Owner must approve your request before you can sign in.</p>
                  </div>

                  <button
                    type="submit"
                    disabled={isAuthLoading}
                    className="w-full mt-2 py-2.5 px-4 bg-teal-600 hover:bg-teal-500 disabled:opacity-50 text-white font-semibold text-xs rounded-xl shadow-lg shadow-teal-600/30 transition-all flex items-center justify-center gap-2 cursor-pointer"
                  >
                    {isAuthLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />}
                    <span>{isAuthLoading ? 'Submitting Application...' : 'Submit Join Request (Pending Approval)'}</span>
                  </button>
                </form>
              )}
            </div>
          )}

          <div className="mt-5 pt-4 border-t border-slate-800">
            <p className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase text-center mb-2.5">
              1-Click Demo Evaluation Personas
            </p>
            <div className="space-y-1.5">
              <button
                type="button"
                onClick={() => handleAuthLogin(undefined, 'owner@vanguardclinic.com', 'password123')}
                className="w-full p-2 rounded-xl bg-slate-800/70 hover:bg-emerald-950/40 hover:border-emerald-500/50 border border-slate-700/60 text-left transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="text-xs font-bold text-white group-hover:text-emerald-300">Dr. Liam Vance (Clinic Owner)</p>
                  <p className="text-[10px] text-slate-400">Apex Health Medical Center • <span className="font-mono text-emerald-400">tenant-001</span></p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-medium">Quick Login</span>
              </button>

              <button
                type="button"
                onClick={() => handleAuthLogin(undefined, 'doctor@vanguardclinic.com', 'password123')}
                className="w-full p-2 rounded-xl bg-slate-800/70 hover:bg-blue-950/40 hover:border-blue-500/50 border border-slate-700/60 text-left transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="text-xs font-bold text-white group-hover:text-blue-300">Dr. Rachel Kim (Attending Physician)</p>
                  <p className="text-[10px] text-slate-400">Apex Health Medical Center • <span className="font-mono text-blue-400">tenant-001</span></p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 font-medium">Quick Login</span>
              </button>

              <button
                type="button"
                onClick={() => handleAuthLogin(undefined, 'owner@metrohealth.com', 'password123')}
                className="w-full p-2 rounded-xl bg-slate-800/70 hover:bg-purple-950/40 hover:border-purple-500/50 border border-slate-700/60 text-left transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="text-xs font-bold text-white group-hover:text-purple-300">Dr. Robert Hayes (Clinic Owner)</p>
                  <p className="text-[10px] text-slate-400">Metro Health Urgent Care • <span className="font-mono text-purple-400">tenant-002</span></p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 font-medium">Quick Login</span>
              </button>
            </div>
          </div>
        </div>

        <div className="mt-5 text-center text-[11px] text-slate-500 flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-emerald-500" />
          <span>Strict Multi-Tenant Row Partitioning • PostgreSQL 16 • All passwords: <strong className="text-slate-400 font-mono">password123</strong></span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50 text-slate-800 font-sans">
      {/* =========================================================================
          1. LEFT PERSISTENT NAVIGATION SIDEBAR (Width: 260px)
      ========================================================================== */}
      <aside className="w-64 shrink-0 h-full border-r border-slate-200/90 bg-white flex flex-col justify-between shadow-sm z-10">
        <div>
          {/* Clinic Brand */}
          <div className="p-5 border-b border-slate-100 flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center text-white shadow-md shadow-emerald-500/20">
              <Stethoscope className="w-5 h-5" />
            </div>
            <div>
              <h1 className="font-bold text-base text-slate-900 tracking-tight leading-tight">
                PractiCare
              </h1>
              <p className="text-[11px] font-medium text-emerald-600">Clinical Suite</p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="p-3 space-y-1">
            <button
              onClick={() => setShowAICopilot(true)}
              className="w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-semibold bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white shadow-xs transition-all cursor-pointer mb-2"
            >
              <div className="flex items-center gap-2">
                <Bot className="w-4 h-4 text-emerald-100" />
                <span>AI Operations Agent</span>
              </div>
              <span className="text-[9px] px-1.5 py-0.5 rounded font-mono font-bold bg-white/20 text-white">LangGraph</span>
            </button>
            {[
              { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
              { id: 'tasks', label: 'Tasks & Rounds', icon: ListTodo, badge: tasks.filter((t) => t.status.toLowerCase() !== 'completed').length },
              { id: 'checklists', label: 'Checklists', icon: CheckSquare, badge: `${checklists.filter((c) => c.is_completed).length}/${checklists.length}` },
              { id: 'inventory', label: 'Inventory & Supplies', icon: Package, badge: summary?.low_stock_count },
              { id: 'rooms', label: 'Exam Rooms', icon: Building2 },
              { id: 'staff', label: 'Staff on Shift', icon: Users, badge: `${staff.filter((s) => s.is_active).length}` },
            ].map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setActiveTab(item.id as TabType)}
                  className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-lg text-xs font-medium transition-all ${
                    isActive
                      ? 'bg-emerald-50 text-emerald-800 font-semibold shadow-xs'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <Icon className={`w-4 h-4 ${isActive ? 'text-emerald-600' : 'text-slate-400'}`} />
                    <span>{item.label}</span>
                  </div>
                  {item.badge !== undefined && (
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                        isActive
                          ? 'bg-emerald-600 text-white'
                          : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      {item.badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Bottom User Profile Widget & Session Switcher */}
        <div className="p-3 border-t border-slate-200/90 bg-slate-50/90 text-xs">
          {isLoggedIn ? (
            <div className="space-y-2">
              <div className="p-2.5 rounded-xl bg-white border border-slate-200 shadow-xs">
                <div className="flex items-center gap-2.5">
                  <div className="relative shrink-0">
                    <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-emerald-600 to-teal-500 text-white font-bold text-xs flex items-center justify-center shadow-xs">
                      {userName.split(' ').map((n) => n[0]).filter(Boolean).slice(0, 2).join('')}
                    </div>
                    <span className="absolute bottom-0 right-0 w-2.5 h-2.5 bg-emerald-500 border-2 border-white rounded-full"></span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-slate-900 text-xs truncate">
                      {userName}
                    </p>
                    <div className="flex items-center gap-1 mt-0.5">
                      <span className={`text-[9px] px-1.5 py-0.2 rounded font-semibold tracking-wide uppercase ${
                        userRole === 'CLINIC_OWNER' ? 'bg-emerald-100 text-emerald-800' :
                        userRole === 'ATTENDING_PHYSICIAN' ? 'bg-blue-100 text-blue-800' :
                        userRole === 'NURSE_STAFF' ? 'bg-purple-100 text-purple-800' :
                        'bg-amber-100 text-amber-800'
                      }`}>
                        {userRole.replace('_', ' ')}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="mt-2 pt-1.5 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-500">
                  <span className="truncate max-w-[200px] font-medium text-slate-600" title={companyName || (tenantId === 'tenant-001' ? 'Vanguard Comprehensive Health Center' : 'Metro Health Urgent Care')}>
                    {companyName || (tenantId === 'tenant-001' ? 'Vanguard Comprehensive Health Center' : 'Metro Health Urgent Care')} • {tenantId}
                  </span>
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
              className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs shadow-xs transition-all"
            >
              <LogIn className="w-4 h-4" />
              <span>Sign In / Switch Profile</span>
            </button>
          )}

          {/* Quick Ecosystem switcher */}
          <div className="mt-2.5 pt-2 border-t border-slate-200/60 flex items-center justify-between text-[11px] text-slate-400">
            <span>Ecosystem:</span>
            <div className="flex gap-1.5 font-medium">
              <a href="http://localhost:3002" className="text-amber-600 hover:underline">Tax</a>
              <span>•</span>
              <a href="http://localhost:3003" className="text-rose-600 hover:underline">Prop</a>
              <span>•</span>
              <a href="http://localhost:3004" className="text-sky-600 hover:underline">Ops</a>
            </div>
          </div>
        </div>
      </aside>

      {/* =========================================================================
          2. MAIN WORKSPACE AREA (Middle Flexible Column)
      ========================================================================== */}
      <div className="flex flex-col flex-1 h-full overflow-hidden bg-[#f8fafc]">
        {/* TOP HEADER */}
        <header className="h-16 px-6 bg-white border-b border-slate-200/80 flex items-center justify-between shrink-0 shadow-2xs">
          <div className="flex items-center gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-bold text-lg text-slate-900 capitalize tracking-tight">
                  {activeTab === 'dashboard' ? 'Clinic Executive Overview' : activeTab}
                </h2>
                {userRole !== 'CLINIC_OWNER' && (
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 flex items-center gap-1">
                    <Shield className="w-3 h-3 text-emerald-600" />
                    <span>Role: {userRole}</span>
                  </span>
                )}
                {!isLoggedIn && (
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-200">
                    Read-Only Mode
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500 font-medium">
                {companyName || summary?.practice_name || (tenantId === 'tenant-001' ? 'Vanguard Comprehensive Health Center' : 'Metro Health Urgent Care')} • {tenantId}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            {/* LangGraph AI Operations Agent trigger */}
            <button
              onClick={() => setShowAICopilot(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white text-xs font-semibold shadow-xs transition-all cursor-pointer"
            >
              <Bot className="w-3.5 h-3.5" />
              <span>AI Agent</span>
            </button>
          </div>
        </header>

        {/* SCROLLABLE MAIN VIEW */}
        <main className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* =====================================================================
              VIEW A: DASHBOARD OVERVIEW
          ====================================================================== */}
          {activeTab === 'dashboard' && (
            <div className="space-y-6">
              {/* EMPTY PRACTICE ONBOARDING BANNER */}
              {summary && summary.total_rooms === 0 && summary.tasks_total === 0 && summary.low_stock_count === 0 && (
                <div className="p-5 rounded-2xl bg-gradient-to-r from-teal-50 via-emerald-50 to-white border border-teal-200/80 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="flex items-center gap-3.5">
                    <div className="w-10 h-10 rounded-xl bg-teal-600 text-white flex items-center justify-center shrink-0 shadow-xs">
                      <Building2 className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="font-bold text-sm text-slate-900">Your practice is ready. Start by adding rooms, staff, and clinical tasks.</h4>
                      <p className="text-xs text-slate-600 mt-0.5">
                        Operational metrics and provider workloads will update automatically as records are created.
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {canAddRoom && (
                      <button
                        onClick={() => setShowRoomModal(true)}
                        className="px-3 py-1.5 bg-teal-700 hover:bg-teal-800 text-white rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer shadow-xs"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span>Add Room</span>
                      </button>
                    )}
                    {canCreateTask && (
                      <button
                        onClick={() => setShowTaskModal(true)}
                        className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 cursor-pointer shadow-xs"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span>Create Task</span>
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* TOP METRIC CARDS */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                {/* 1. Rooms Occupancy */}
                <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-xs flex items-center justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Exam Rooms
                    </p>
                    <div className="flex items-baseline gap-2 mt-1">
                      <h3 className="text-2xl font-bold text-slate-900">{summary?.total_rooms ?? 0}</h3>
                      <span className="text-xs text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded-md">
                        {summary?.room_occupancy?.['Available'] ?? 0} Available
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      {summary?.room_occupancy?.['Occupied'] ?? 0} Occupied • {summary?.room_occupancy?.['Turnover'] ?? 0} Turnover
                    </p>
                  </div>
                  <div className="h-11 w-11 rounded-lg bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-600">
                    <Building2 className="w-5 h-5" />
                  </div>
                </div>

                {/* 2. Active Staff */}
                <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-xs flex items-center justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Staff on Duty
                    </p>
                    <div className="flex items-baseline gap-2 mt-1">
                      <h3 className="text-2xl font-bold text-slate-900">
                        {summary?.on_shift_count ?? summary?.active_staff_count ?? 0}
                      </h3>
                      <span className="text-xs text-teal-700 font-semibold bg-teal-50 px-2 py-0.5 rounded-md">
                        Shift Active
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      {summary?.total_staff ?? 0} Registered Providers
                    </p>
                  </div>
                  <div className="h-11 w-11 rounded-lg bg-teal-50 border border-teal-100 flex items-center justify-center text-teal-600">
                    <Users className="w-5 h-5" />
                  </div>
                </div>

                {/* 3. Pending Tasks */}
                <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-xs flex items-center justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Rounds & Tasks
                    </p>
                    <div className="flex items-baseline gap-2 mt-1">
                      <h3 className="text-2xl font-bold text-slate-900">
                        {summary?.tasks_pending ?? 0}
                      </h3>
                      <span className="text-xs text-amber-700 font-semibold bg-amber-50 px-2 py-0.5 rounded-md">
                        Pending
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      {summary?.tasks_completed ?? 0} Completed today
                    </p>
                  </div>
                  <div className="h-11 w-11 rounded-lg bg-amber-50 border border-amber-100 flex items-center justify-center text-amber-600">
                    <ListTodo className="w-5 h-5" />
                  </div>
                </div>

                {/* 4. Critical Stock & Expiry */}
                <div className="p-4 rounded-xl bg-white border border-slate-200/80 shadow-xs flex items-center justify-between">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                      Inventory Alerts
                    </p>
                    <div className="flex items-baseline gap-2 mt-1">
                      <h3 className="text-2xl font-bold text-rose-600">
                        {summary?.low_stock_count ?? 0}
                      </h3>
                      <span className="text-xs text-rose-700 font-semibold bg-rose-50 px-2 py-0.5 rounded-md">
                        Low Stock
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      {summary?.expiring_soon_count ?? 0} Expiring in 30d
                    </p>
                  </div>
                  <div className="h-11 w-11 rounded-lg bg-rose-50 border border-rose-100 flex items-center justify-center text-rose-600">
                    <AlertTriangle className="w-5 h-5" />
                  </div>
                </div>
              </div>

              {/* TWO COLUMN SUMMARY: Tasks Quick Table & Rooms Board */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Immediate Tasks (7 Cols) */}
                <div className="lg:col-span-7 bg-white rounded-xl border border-slate-200/80 p-5 shadow-xs">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <ListTodo className="w-5 h-5 text-emerald-600" />
                      <h3 className="font-bold text-sm text-slate-900">Urgent Clinical Tasks</h3>
                    </div>
                    <button
                      onClick={() => setActiveTab('tasks')}
                      className="text-xs font-semibold text-emerald-600 hover:text-emerald-700 flex items-center gap-1"
                    >
                      <span>View All ({tasks.length})</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {tasks.length === 0 ? (
                    <div className="py-10 text-center flex flex-col items-center justify-center bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                      <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-2">
                        <ListTodo className="w-5 h-5" />
                      </div>
                      <p className="text-xs font-semibold text-slate-700">No tasks yet. Create your first clinical task.</p>
                      <p className="text-[11px] text-slate-400 mt-0.5">Assign clinical rounds, room sanitization, and team duties.</p>
                      {canCreateTask && (
                        <button
                          onClick={() => setShowTaskModal(true)}
                          className="mt-3 px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold transition-colors flex items-center gap-1 cursor-pointer"
                        >
                          <Plus className="w-3.5 h-3.5" />
                          <span>Add Task</span>
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-100">
                      {tasks.slice(0, 5).map((t) => (
                        <div
                          key={t.id}
                          className="py-3 flex items-center justify-between gap-3 hover:bg-slate-50/80 px-2 rounded-lg transition-colors"
                        >
                          <div className="flex items-center gap-3">
                            <button
                              onClick={() => handleToggleTask(t)}
                              disabled={!canToggleTaskItem(t)}
                              title={canToggleTaskItem(t) ? 'Toggle task completion' : 'Only assigned staff can complete this task'}
                              className={`w-5 h-5 rounded border flex items-center justify-center transition-colors ${
                                !canToggleTaskItem(t)
                                  ? 'opacity-40 cursor-not-allowed border-slate-200'
                                  : t.status.toLowerCase() === 'completed'
                                  ? 'bg-emerald-600 border-emerald-600 text-white'
                                  : 'border-slate-300 hover:border-emerald-600'
                              }`}
                            >
                              {t.status.toLowerCase() === 'completed' && <Check className="w-3.5 h-3.5" />}
                            </button>
                            <div>
                              <p
                                className={`text-xs font-semibold ${
                                  t.status.toLowerCase() === 'completed'
                                    ? 'line-through text-slate-400'
                                    : 'text-slate-800'
                                }`}
                              >
                                {t.title}
                              </p>
                              <p className="text-[11px] text-slate-400 mt-0.5">
                                {t.room_name} • {t.assigned_staff_name} • {t.due_date}
                              </p>
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                t.priority === 'Critical'
                                  ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                  : t.priority === 'High'
                                  ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                  : 'bg-slate-100 text-slate-600'
                              }`}
                            >
                              {t.priority}
                            </span>
                            {canEditTaskItem(t) && (
                              <button
                                onClick={() => handleOpenEditTask(t)}
                                title="Edit Task"
                                className="p-1 hover:bg-emerald-50 text-slate-400 hover:text-emerald-600 rounded transition-colors"
                              >
                                <Pencil className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Room Occupancy Grid (5 Cols) */}
                <div className="lg:col-span-5 bg-white rounded-xl border border-slate-200/80 p-5 shadow-xs">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <Building2 className="w-5 h-5 text-teal-600" />
                      <h3 className="font-bold text-sm text-slate-900">Room Status Snapshot</h3>
                    </div>
                    <button
                      onClick={() => setActiveTab('rooms')}
                      className="text-xs font-semibold text-teal-600 hover:text-teal-700 flex items-center gap-1"
                    >
                      <span>Manage Rooms</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {rooms.length === 0 ? (
                    <div className="py-10 text-center flex flex-col items-center justify-center bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                      <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-2">
                        <Building2 className="w-5 h-5" />
                      </div>
                      <p className="text-xs font-semibold text-slate-700">No exam rooms configured yet.</p>
                      <p className="text-[11px] text-slate-400 mt-0.5">Set up clinical bays, consultation suites, and surgery rooms.</p>
                      <button
                        onClick={() => setShowRoomModal(true)}
                        className="mt-3 px-3 py-1 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-xs font-semibold transition-colors flex items-center gap-1 cursor-pointer"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span>Add Room</span>
                      </button>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {rooms.map((r) => (
                        <div
                          key={r.id}
                          className="p-3.5 rounded-xl border border-slate-200/90 bg-slate-50/60 flex flex-col justify-between min-h-[110px] hover:border-slate-300 transition-all shadow-xs"
                        >
                          <div>
                            <div className="flex items-center justify-between gap-2">
                              <span className="font-bold text-xs text-slate-900 shrink-0">Room {r.room_number}</span>
                              <span
                                className={`text-[10px] font-bold px-2 py-0.5 rounded-full shrink-0 ${
                                  r.status === 'Available'
                                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                    : r.status === 'Occupied'
                                    ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                    : 'bg-amber-50 text-amber-700 border border-amber-200'
                                }`}
                              >
                                {r.status}
                              </span>
                            </div>
                            <p className="text-[11px] text-slate-500 mt-1 truncate" title={r.name}>{r.name}</p>
                          </div>

                          {/* Quick switch status */}
                          <div className="mt-3 pt-2.5 border-t border-slate-200/70 flex items-center justify-between gap-2 text-[10px]">
                            <span
                              className="text-slate-600 font-medium truncate flex-1 min-w-0"
                              title={r.room_type}
                            >
                              {r.room_type}
                            </span>
                            <select
                              value={r.status}
                              onChange={(e) => handleUpdateRoomStatus(r.id, e.target.value)}
                              className="shrink-0 bg-white border border-slate-200 rounded px-1.5 py-0.5 text-[10px] font-medium text-slate-700 focus:outline-none focus:border-teal-500 cursor-pointer shadow-2xs"
                            >
                              <option value="Available">Available</option>
                              <option value="Occupied">Occupied</option>
                              <option value="Turnover">Turnover</option>
                            </select>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* =====================================================================
              VIEW B: TASKS FULL CRUD TABLE
          ====================================================================== */}
          {activeTab === 'tasks' && (
            <div className="bg-white rounded-xl border border-slate-200/80 p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-base text-slate-900">Clinical Tasks & Shift Rounds</h3>
                  <p className="text-xs text-slate-500">
                    Track pending and completed operational clinical tasks across exam rooms.
                  </p>
                </div>
                {canCreateTask && (
                  <button
                    onClick={() => setShowTaskModal(true)}
                    className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs flex items-center gap-1.5"
                  >
                    <Plus className="w-4 h-4" />
                    <span>Add Task</span>
                  </button>
                )}
              </div>

              {/* Task Table */}
              {tasks.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-400 bg-slate-50/60 rounded-xl border border-dashed border-slate-200">
                  <ListTodo className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                  <p className="font-semibold text-slate-700">No tasks yet.</p>
                  <p className="text-slate-400 mt-0.5">Create your first clinical task.</p>
                </div>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                      <tr>
                        <th className="p-3 w-10">Done</th>
                        <th className="p-3">Title & Description</th>
                        <th className="p-3">Location</th>
                        <th className="p-3">Assigned Staff</th>
                        <th className="p-3">Priority</th>
                        <th className="p-3">Due Date</th>
                        <th className="p-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {tasks.map((t) => (
                        <tr key={t.id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="p-3">
                            <button
                              onClick={() => handleToggleTask(t)}
                              disabled={!canToggleTaskItem(t)}
                              title={canToggleTaskItem(t) ? 'Toggle task completion' : 'Only assigned staff can complete this task'}
                              className={`w-5 h-5 rounded border flex items-center justify-center transition-colors ${
                                !canToggleTaskItem(t)
                                  ? 'opacity-40 cursor-not-allowed border-slate-200'
                                  : t.status.toLowerCase() === 'completed'
                                  ? 'bg-emerald-600 border-emerald-600 text-white'
                                  : 'border-slate-300 hover:border-emerald-600'
                              }`}
                            >
                              {t.status.toLowerCase() === 'completed' && <Check className="w-3.5 h-3.5" />}
                            </button>
                          </td>
                          <td className="p-3">
                            <p className={`font-semibold ${t.status.toLowerCase() === 'completed' ? 'line-through text-slate-400' : 'text-slate-900'}`}>
                              {t.title}
                            </p>
                            {t.description && <p className="text-[11px] text-slate-400 mt-0.5">{t.description}</p>}
                          </td>
                          <td className="p-3 text-slate-600">{t.room_name}</td>
                          <td className="p-3">
                            <span className="font-medium text-slate-800">{t.assigned_staff_name}</span>
                          </td>
                          <td className="p-3">
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                t.priority === 'Critical'
                                  ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                  : t.priority === 'High'
                                  ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                  : 'bg-slate-100 text-slate-600'
                              }`}
                            >
                              {t.priority}
                            </span>
                          </td>
                          <td className="p-3 text-slate-500 font-mono text-[11px]">{t.due_date}</td>
                          <td className="p-3 text-right">
                            <div className="flex items-center justify-end gap-1">
                              {canEditTaskItem(t) && (
                                <button
                                  onClick={() => handleOpenEditTask(t)}
                                  title="Edit Task"
                                  className="p-1 hover:bg-emerald-50 text-slate-400 hover:text-emerald-600 rounded transition-colors"
                                >
                                  <Pencil className="w-4 h-4" />
                                </button>
                              )}
                              {canDeleteTaskItem(t) && (
                                <button
                                  onClick={() => handleDeleteTask(t.id)}
                                  title="Delete Task"
                                  className="p-1 hover:bg-rose-50 text-slate-400 hover:text-rose-600 rounded transition-colors"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* =====================================================================
              VIEW C: CHECKLISTS
          ====================================================================== */}
          {activeTab === 'checklists' && (
            <div className="bg-white rounded-xl border border-slate-200/80 p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-base text-slate-900">Clinical Safety & Quality Checklists</h3>
                  <p className="text-xs text-slate-500">
                    Daily and weekly verified sterilization, hygiene, and emergency equipment checklists.
                  </p>
                </div>
                {canCreateChecklist && (
                  <button
                    onClick={() => setShowChecklistModal(true)}
                    className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs flex items-center gap-1.5"
                  >
                    <Plus className="w-4 h-4" />
                    <span>Add Checklist</span>
                  </button>
                )}
              </div>

              {checklists.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-400 bg-slate-50/60 rounded-xl border border-dashed border-slate-200">
                  <ListChecks className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                  <p className="font-semibold text-slate-700">No checklists created yet.</p>
                  <p className="text-slate-400 mt-0.5">Define safety checklists to track compliance.</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {checklists.map((c) => (
                    <div
                      key={c.id}
                      className={`p-4 rounded-xl border transition-all ${
                        c.is_completed
                          ? 'border-emerald-200 bg-emerald-50/30'
                          : 'border-slate-200 bg-white hover:border-slate-300'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-start gap-2.5 flex-1 min-w-0">
                          <button
                            onClick={() => handleToggleChecklist(c)}
                            disabled={!canToggleChecklistItem(c)}
                            title={canToggleChecklistItem(c) ? 'Toggle checklist completion' : 'Nurses can only fill or complete checklists assigned to themselves'}
                            className={`mt-0.5 w-5 h-5 rounded border flex items-center justify-center shrink-0 transition-colors ${
                              !canToggleChecklistItem(c)
                                ? 'opacity-40 cursor-not-allowed border-slate-200'
                                : c.is_completed
                                ? 'bg-emerald-600 border-emerald-600 text-white'
                                : 'border-slate-300 hover:border-emerald-600'
                            }`}
                          >
                            {c.is_completed && <Check className="w-3.5 h-3.5" />}
                          </button>
                          <div className="min-w-0 flex-1">
                            <h4 className={`text-xs font-bold truncate ${c.is_completed ? 'line-through text-slate-400' : 'text-slate-900'}`}>
                              {c.title}
                            </h4>
                            <span className="inline-block mt-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                              {c.category} • {c.frequency}
                            </span>
                          </div>
                        </div>

                        {/* Checklist Actions: Edit & Delete definitions */}
                        <div className="flex items-center gap-1 shrink-0">
                          {canEditChecklistItem(c) && (
                            <button
                              onClick={() => handleOpenEditChecklist(c)}
                              title="Edit Checklist Definition"
                              className="p-1 hover:bg-emerald-50 text-slate-400 hover:text-emerald-600 rounded transition-colors"
                            >
                              <Pencil className="w-3.5 h-3.5" />
                            </button>
                          )}
                          {canDeleteChecklistItem(c) && (
                            <button
                              onClick={() => handleDeleteChecklist(c.id)}
                              title="Delete Checklist Definition"
                              className="p-1 hover:bg-rose-50 text-slate-400 hover:text-rose-600 rounded transition-colors"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </div>

                      <div className="mt-3 pt-2.5 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
                        <span>Assigned: {c.assigned_staff_name}</span>
                        <span className={c.is_completed ? 'text-emerald-700 font-semibold' : 'text-amber-700 font-medium'}>
                          {c.is_completed ? 'Verified' : 'Pending'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* =====================================================================
              VIEW D: INVENTORY & EXPIRY
          ====================================================================== */}
          {activeTab === 'inventory' && (
            <div className="bg-white rounded-xl border border-slate-200/80 p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-base text-slate-900">Medical Supplies & Expiry Audit</h3>
                  <p className="text-xs text-slate-500">
                    Live stock balances, safety threshold alerts, and batch expiry tracking.
                  </p>
                </div>
                {canManageInventory && (
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setShowInventoryImportModal(true)}
                      className="px-3.5 py-1.5 border border-emerald-600 text-emerald-700 hover:bg-emerald-50 rounded-lg text-xs font-semibold flex items-center gap-1.5"
                    >
                      <Upload className="w-4 h-4" />
                      <span>Import with AI</span>
                    </button>
                    <button
                      onClick={() => setShowInventoryModal(true)}
                      className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs flex items-center gap-1.5"
                    >
                      <Plus className="w-4 h-4" />
                      <span>Add Supply Item</span>
                    </button>
                  </div>
                )}
              </div>

              {inventory.length > 0 && (
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap gap-1.5">
                    {INVENTORY_EXPIRY_FILTERS.map((f) => (
                      <button
                        key={f.id}
                        onClick={() => setInventoryExpiryFilter(f.id)}
                        className={`px-2.5 py-1 rounded-full text-[11px] font-semibold border ${
                          inventoryExpiryFilter === f.id
                            ? f.id === 'expired'
                              ? 'bg-rose-600 border-rose-600 text-white'
                              : 'bg-emerald-600 border-emerald-600 text-white'
                            : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                        }`}
                      >
                        {f.label} <span className="opacity-75">({countForExpiryFilter(inventory, f.id)})</span>
                      </button>
                    ))}
                  </div>
                  <input
                    type="search"
                    value={inventorySearch}
                    onChange={(e) => setInventorySearch(e.target.value)}
                    placeholder="Search name, supplier, batch…"
                    className="border border-slate-200 rounded-lg px-2.5 py-1 text-xs bg-white w-56 focus:outline-none focus:border-emerald-600"
                  />
                  <label className="text-[11px] text-slate-500 flex items-center gap-1.5">
                    Sort
                    <select
                      value={inventorySort}
                      onChange={(e) => setInventorySort(e.target.value as InventorySort)}
                      className="border border-slate-200 rounded-lg p-1 bg-white text-slate-700"
                    >
                      <option value="stock">Lowest stock first</option>
                      <option value="expiry">Nearest expiry first</option>
                      <option value="name">Name (A–Z)</option>
                    </select>
                  </label>
                </div>
              )}
              {inventoryViewError && <p className="text-xs text-rose-600">{inventoryViewError}</p>}

              {inventory.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-400 bg-slate-50/60 rounded-xl border border-dashed border-slate-200">
                  <Package className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                  <p className="font-semibold text-slate-700">No inventory items added yet.</p>
                  <p className="text-slate-400 mt-0.5">Track supplies and expiry dates across bays.</p>
                </div>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                      <tr>
                        <th className="p-3">Supply Item</th>
                        <th className="p-3">Location</th>
                        <th className="p-3">Stock Level</th>
                        <th className="p-3">Min. Threshold</th>
                        <th className="p-3">Expiry Date</th>
                        <th className="p-3">Batch / Supplier</th>
                        <th className="p-3">Stock / Expiry Status</th>
                        {(inventoryView ?? inventory).some(canManageInventoryItem) && <th className="p-3 text-right">Actions</th>}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {(inventoryView ?? inventory).length === 0 && (
                        <tr>
                          <td colSpan={8} className="p-6 text-center text-slate-400">
                            No items match “{INVENTORY_EXPIRY_FILTERS.find((f) => f.id === inventoryExpiryFilter)?.label}”
                            {inventorySearchApplied.trim() ? ` and “${inventorySearchApplied.trim()}”` : ''}.
                          </td>
                        </tr>
                      )}
                      {(inventoryView ?? inventory).map((inv) => {
                        const pct = Math.round((inv.current_stock / inv.min_threshold) * 100);
                        return (
                          <tr key={inv.id} className="hover:bg-slate-50/80 transition-colors">
                            <td className="p-3 font-semibold text-slate-900">{inv.item_name}</td>
                            <td className="p-3 text-slate-600">{inv.room_name}</td>
                            <td className="p-3">
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-slate-900">{inv.current_stock}</span>
                                <span className="text-slate-400">{inv.unit}</span>
                                <div className="w-16 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                                  <div
                                    className={`h-full ${pct <= 40 ? 'bg-rose-500' : pct <= 75 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                                    style={{ width: `${Math.min(pct, 100)}%` }}
                                  />
                                </div>
                              </div>
                            </td>
                            <td className="p-3 text-slate-500">{inv.min_threshold} {inv.unit}</td>
                            <td className="p-3">
                              <span className={`font-mono text-[11px] ${inv.is_expired ? 'text-rose-700 font-bold' : inv.is_expiring_soon ? 'text-rose-600 font-bold' : 'text-slate-600'}`}>
                                {inv.expiry_date || 'N/A'}
                              </span>
                              {expiryLabel(inv) && (
                                <span className={`block text-[10px] ${inv.is_expired ? 'text-rose-600' : 'text-slate-400'}`}>{expiryLabel(inv)}</span>
                              )}
                            </td>
                            <td className="p-3 text-slate-600">
                              <span className="block font-mono text-[11px]">{inv.batch_number || '—'}</span>
                              <span className="block text-[10px] text-slate-400">
                                {inv.supplier || '—'}
                                {inv.purchase_price !== null && inv.purchase_price !== undefined ? ` · ${inv.purchase_price.toFixed(2)}/unit` : ''}
                              </span>
                            </td>
                            <td className="p-3">
                              <div className="flex flex-col items-start gap-1">
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${STOCK_BADGE[inv.stock_status || 'In Stock']}`}>
                                  {inv.stock_status || (inv.is_low_stock ? 'Low Stock' : 'In Stock')}
                                  {inv.stock_status === 'Low Stock' && inv.shortfall ? ` (−${inv.shortfall})` : ''}
                                </span>
                                <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${EXPIRY_BADGE[inv.expiry_state || 'No Expiry Date']}`}>
                                  {inv.expiry_state || 'No Expiry Date'}
                                </span>
                              </div>
                            </td>
                            {(inventoryView ?? inventory).some(canManageInventoryItem) && (
                              <td className="p-3 text-right whitespace-nowrap">
                                {canManageInventoryItem(inv) && (
                                  <div className="flex items-center justify-end gap-1">
                                    <button
                                      onClick={() => setAdjustingInventory(inv)}
                                      title="Restock or reduce stock"
                                      className="px-2 py-1 text-[11px] font-semibold border border-emerald-600 text-emerald-700 rounded hover:bg-emerald-50"
                                    >
                                      ± Stock
                                    </button>
                                    <button
                                      onClick={() => setEditingInventory(inv)}
                                      title="Edit item details"
                                      className="p-1 hover:bg-emerald-50 text-slate-400 hover:text-emerald-600 rounded"
                                    >
                                      <Pencil className="w-4 h-4" />
                                    </button>
                                  </div>
                                )}
                              </td>
                            )}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* =====================================================================
              VIEW E: ROOMS FULL BOARD
          ====================================================================== */}
          {activeTab === 'rooms' && (
            <div className="bg-white rounded-xl border border-slate-200/80 p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-base text-slate-900">Exam Rooms & Surgical Bays</h3>
                  <p className="text-xs text-slate-500">
                    Real-time patient occupancy, turnover sterilization queues, and equipment assignments.
                  </p>
                </div>
                {canAddRoom && (
                  <button
                    onClick={() => setShowRoomModal(true)}
                    className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs flex items-center gap-1.5"
                  >
                    <Plus className="w-4 h-4" />
                    <span>Add Room</span>
                  </button>
                )}
              </div>

              {rooms.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-400 bg-slate-50/60 rounded-xl border border-dashed border-slate-200">
                  <DoorClosed className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                  <p className="font-semibold text-slate-700">No exam rooms configured yet.</p>
                  <p className="text-slate-400 mt-0.5">Add exam rooms and surgical suites to manage occupancy.</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {rooms.map((r) => (
                    <div
                      key={r.id}
                      className="p-4 rounded-xl border border-slate-200 bg-white hover:border-slate-300 shadow-2xs flex flex-col justify-between"
                    >
                      <div>
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-slate-400">BAY #{r.room_number}</span>
                          <span
                            className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                              r.status === 'Available'
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                : r.status === 'Occupied'
                                ? 'bg-rose-50 text-rose-700 border border-rose-200'
                                : 'bg-amber-50 text-amber-700 border border-amber-200'
                            }`}
                          >
                            {r.status}
                          </span>
                        </div>
                        <h4 className="font-bold text-sm text-slate-900 mt-2">{r.name}</h4>
                        <p className="text-xs text-slate-500 mt-0.5">Type: {r.room_type} Suite</p>
                      </div>

                      <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                        <span className="text-[11px] text-slate-500">Status Action:</span>
                        {canUpdateRoomStatus ? (
                          <div className="flex gap-1">
                            {['Available', 'Occupied', 'Turnover'].map((st) => (
                              <button
                                key={st}
                                onClick={() => handleUpdateRoomStatus(r.id, st)}
                                className={`px-2 py-1 rounded text-[10px] font-semibold transition-all ${
                                  r.status === st
                                    ? 'bg-slate-900 text-white'
                                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                }`}
                              >
                                {st}
                              </button>
                            ))}
                          </div>
                        ) : (
                          <span className="text-[10px] text-slate-400 italic">Read-only</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* =====================================================================
              VIEW F: STAFF LIST
          ====================================================================== */}
          {activeTab === 'staff' && (
            <div className="space-y-6">
              {/* OWNER-ONLY SECTION: COMPANY SETTINGS & TENANT OVERVIEW */}
              {userRole === 'CLINIC_OWNER' && (
                <div className="bg-gradient-to-r from-slate-900 via-slate-850 to-teal-950 text-white rounded-2xl border border-slate-800 p-5 shadow-xl space-y-4">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Building2 className="w-5 h-5 text-emerald-400" />
                        <h3 className="font-bold text-base text-white tracking-tight">
                          {companySettings?.company_name || companyName || 'Clinical Practice'}
                        </h3>
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-500/40">
                          Multi-Tenant Partition
                        </span>
                      </div>
                      <div className="flex items-center gap-2 pt-1 text-xs">
                        <span className="text-slate-400 font-medium">Tenant ID:</span>
                        <div className="flex items-center gap-1.5 bg-slate-800/80 px-2.5 py-1 rounded-lg border border-slate-700">
                          <code className="font-mono text-emerald-300 text-xs font-semibold">{tenantId}</code>
                          <button
                            type="button"
                            onClick={() => {
                              navigator.clipboard.writeText(tenantId);
                              setCopiedTenantId(true);
                              setTimeout(() => setCopiedTenantId(false), 2000);
                            }}
                            className="text-slate-400 hover:text-white p-0.5 rounded transition-colors cursor-pointer"
                            title="Copy Tenant ID"
                          >
                            {copiedTenantId ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                        </div>
                        <span className="text-[10px] text-slate-400 italic">
                          (Tenant ID is an identifier, not an authentication credential)
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      <div className="flex items-center gap-2 text-xs">
                        <div className="px-3 py-1.5 rounded-xl bg-slate-800/80 border border-slate-700/80 text-center">
                          <p className="text-[10px] text-slate-400 uppercase font-semibold">Total Staff</p>
                          <p className="font-bold text-white text-sm">{companySettings?.total_staff_count ?? staff.length}</p>
                        </div>
                        <div className="px-3 py-1.5 rounded-xl bg-slate-800/80 border border-slate-700/80 text-center">
                          <p className="text-[10px] text-slate-400 uppercase font-semibold">Active Invites</p>
                          <p className="font-bold text-emerald-400 text-sm">{invitations.filter((i) => !i.is_revoked).length}</p>
                        </div>
                        <div className="px-3 py-1.5 rounded-xl bg-slate-800/80 border border-slate-700/80 text-center">
                          <p className="text-[10px] text-slate-400 uppercase font-semibold">Pending Requests</p>
                          <p className="font-bold text-amber-400 text-sm">{pendingMembers.length}</p>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => {
                          setGeneratedInvite(null);
                          setShowInviteModal(true);
                        }}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-semibold shadow-lg shadow-emerald-600/30 transition-all flex items-center gap-1.5 cursor-pointer"
                      >
                        <UserPlus className="w-4 h-4" />
                        <span>Invite Staff</span>
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* OWNER-ONLY SECTION: PENDING JOIN REQUESTS */}
              {userRole === 'CLINIC_OWNER' && (
                <div className="bg-white rounded-xl border border-slate-200/80 p-5 shadow-xs space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                    <div className="flex items-center gap-2">
                      <Clock className="w-4 h-4 text-amber-600" />
                      <h4 className="font-bold text-sm text-slate-900">Pending Join Requests</h4>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                        {pendingMembers.length} Awaiting Review
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Staff registered using your clinic invitation code require Owner approval before access is granted.
                    </p>
                  </div>

                  {pendingMembers.length === 0 ? (
                    <div className="py-6 text-center text-xs text-slate-400 bg-slate-50/60 rounded-xl border border-dashed border-slate-200">
                      No pending staff requests. Send invitation codes to onboard team members.
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {pendingMembers.map((pm) => (
                        <div
                          key={pm.id}
                          className="p-4 rounded-xl border border-amber-200/80 bg-amber-50/20 flex flex-col justify-between gap-3 shadow-2xs"
                        >
                          <div>
                            <div className="flex items-center justify-between">
                              <h5 className="font-bold text-xs text-slate-900">{pm.name}</h5>
                              <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-amber-100 text-amber-800 border border-amber-300 font-semibold">
                                {pm.role}
                              </span>
                            </div>
                            <p className="text-[11px] text-slate-500 mt-0.5">{pm.email}</p>
                            <p className="text-[10px] text-slate-400 mt-1">
                              Applied: {new Date(pm.created_at).toLocaleDateString()}
                            </p>
                          </div>

                          <div className="pt-2 border-t border-amber-100 flex items-center justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => handleRejectMember(pm.user_id || pm.id)}
                              className="px-2.5 py-1 text-slate-600 hover:text-rose-700 hover:bg-rose-50 rounded-lg text-xs font-semibold transition-colors cursor-pointer"
                            >
                              Reject
                            </button>
                            <button
                              type="button"
                              onClick={() => handleApproveMember(pm.user_id || pm.id)}
                              className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-xs transition-all flex items-center gap-1 cursor-pointer"
                            >
                              <Check className="w-3.5 h-3.5" />
                              <span>Approve</span>
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* OWNER-ONLY SECTION: ACTIVE INVITATIONS */}
              {userRole === 'CLINIC_OWNER' && (
                <div className="bg-white rounded-xl border border-slate-200/80 p-5 shadow-xs space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                    <div className="flex items-center gap-2">
                      <Key className="w-4 h-4 text-emerald-600" />
                      <h4 className="font-bold text-sm text-slate-900">Active Staff Invitations</h4>
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                        {invitations.filter((i) => !i.is_revoked).length} Active
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Secure, cryptographically generated codes. Revoke at any time to prevent further redemptions.
                    </p>
                  </div>

                  {invitations.length === 0 ? (
                    <div className="py-6 text-center text-xs text-slate-400 bg-slate-50/60 rounded-xl border border-dashed border-slate-200">
                      No invitations created yet. Click &apos;Invite Staff&apos; above to generate an invitation code.
                    </div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs text-slate-600">
                        <thead className="text-[11px] uppercase bg-slate-50 text-slate-400 font-semibold border-b border-slate-100">
                          <tr>
                            <th className="py-2.5 px-3">Invitation Code</th>
                            <th className="py-2.5 px-3">Assigned Role</th>
                            <th className="py-2.5 px-3">Usage</th>
                            <th className="py-2.5 px-3">Expires</th>
                            <th className="py-2.5 px-3">Status</th>
                            <th className="py-2.5 px-3 text-right">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {invitations.map((inv) => (
                            <tr key={inv.id} className="hover:bg-slate-50/60 transition-colors">
                              <td className="py-2.5 px-3">
                                <div className="flex items-center gap-1.5 font-mono font-bold text-slate-900">
                                  <span>{inv.code}</span>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      navigator.clipboard.writeText(inv.code);
                                      setCopiedCodeId(inv.id);
                                      setTimeout(() => setCopiedCodeId(null), 2000);
                                    }}
                                    className="text-slate-400 hover:text-slate-600 p-0.5 rounded transition-colors cursor-pointer"
                                    title="Copy Code"
                                  >
                                    {copiedCodeId === inv.id ? (
                                      <Check className="w-3.5 h-3.5 text-emerald-500" />
                                    ) : (
                                      <Copy className="w-3.5 h-3.5" />
                                    )}
                                  </button>
                                </div>
                              </td>
                              <td className="py-2.5 px-3 font-semibold text-slate-800">{inv.role}</td>
                              <td className="py-2.5 px-3">
                                <span className="font-mono text-slate-700">{inv.use_count}</span>
                                <span className="text-slate-400"> / {inv.max_uses} used</span>
                              </td>
                              <td className="py-2.5 px-3 text-slate-500 text-[11px]">
                                {new Date(inv.expires_at).toLocaleDateString()}
                              </td>
                              <td className="py-2.5 px-3">
                                {inv.is_revoked ? (
                                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                                    Revoked
                                  </span>
                                ) : new Date(inv.expires_at) < new Date() ? (
                                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
                                    Expired
                                  </span>
                                ) : inv.use_count >= inv.max_uses ? (
                                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                                    Exhausted
                                  </span>
                                ) : (
                                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                                    Active
                                  </span>
                                )}
                              </td>
                              <td className="py-2.5 px-3 text-right">
                                {!inv.is_revoked && (
                                  <button
                                    type="button"
                                    onClick={() => handleRevokeInvitation(inv.id)}
                                    className="text-rose-600 hover:text-rose-800 text-[11px] font-semibold hover:underline cursor-pointer"
                                  >
                                    Revoke
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}

              {/* SECTION: CLINICAL STAFF DIRECTORY */}
              <div className="bg-white rounded-xl border border-slate-200/80 p-5 shadow-xs space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-bold text-base text-slate-900">Clinical Staff & On-Duty Providers</h3>
                    <p className="text-xs text-slate-500">
                      Approved staff directory with independent Account Status and Shift Status controls.
                    </p>
                  </div>
                </div>

                {staff.length === 0 ? (
                  <div className="py-12 text-center text-xs text-slate-400 bg-slate-50/60 rounded-xl border border-dashed border-slate-200">
                    <Users className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                    <p className="font-semibold text-slate-700">No staff members enrolled yet.</p>
                    <p className="text-slate-400 mt-0.5">Invite team members or register new providers.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {staff.map((s) => {
                      const isCurrentUser = (s.user_id && s.user_id === userId) || s.name === userName;
                      return (
                        <div
                          key={s.id}
                          onClick={() => {
                            setSelectedStaffProfile(s);
                            setShowStaffProfileModal(true);
                          }}
                          className={`p-4 rounded-xl border bg-white flex flex-col justify-between gap-3 transition-all cursor-pointer hover:border-emerald-500 hover:shadow-md ${
                            s.is_active
                              ? 'border-slate-200 shadow-2xs'
                              : 'border-slate-200 bg-slate-50/60 opacity-80'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <div
                                className={`h-10 w-10 rounded-full font-bold flex items-center justify-center text-sm shadow-xs ${
                                  s.is_active
                                    ? 'bg-gradient-to-br from-emerald-100 to-teal-200 text-emerald-900 border border-emerald-300'
                                    : 'bg-slate-200 text-slate-600'
                                }`}
                              >
                                {s.name.split(' ').map((n) => n[0]).join('').slice(0, 2)}
                              </div>
                              <div>
                                <div className="flex items-center gap-1.5">
                                  <h4 className="font-bold text-xs text-slate-900">{s.name}</h4>
                                  {isCurrentUser && (
                                    <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-emerald-600 text-white">
                                      You
                                    </span>
                                  )}
                                </div>
                                <p className="text-[11px] text-slate-500">{s.role}</p>
                              </div>
                            </div>

                            {/* Dual status badges: Account Status and Shift Status */}
                            <div className="flex flex-col items-end gap-1">
                              <span
                                className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                  s.is_active
                                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                    : 'bg-rose-50 text-rose-700 border border-rose-200'
                                }`}
                              >
                                {s.is_active ? 'Active' : 'Inactive'}
                              </span>
                              <span
                                className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                                  s.on_shift !== false
                                    ? 'bg-sky-50 text-sky-700 border border-sky-200'
                                    : 'bg-slate-100 text-slate-500'
                                }`}
                              >
                                {s.on_shift !== false ? 'On Shift' : 'Off Duty'}
                              </span>
                            </div>
                          </div>

                          {/* Card Footer: Clear Call to Action */}
                          <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                            <span className="text-[11px] font-mono text-slate-400">ID: {s.id}</span>
                            <span className="text-[11px] font-semibold text-emerald-600 hover:text-emerald-700 flex items-center gap-0.5">
                              View Profile & Shift Controls <ChevronRight className="w-3.5 h-3.5" />
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}
        </main>
      </div>

      {/* =========================================================================
          4. MODAL DIALOGS FOR CRUD ACTIONS
      ========================================================================== */}
      {/* MODAL 1: ADD TASK */}
      {showTaskModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-sm text-slate-900">New Clinical Task</h3>
              <button onClick={() => setShowTaskModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateTask} className="mt-4 space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Task Title *</label>
                <input
                  type="text"
                  required
                  value={taskForm.title}
                  onChange={(e) => setTaskForm({ ...taskForm, title: e.target.value })}
                  placeholder="e.g. Sanitize ultrasound probe after triage intake"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-emerald-600"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Description / Protocol</label>
                <textarea
                  value={taskForm.description}
                  onChange={(e) => setTaskForm({ ...taskForm, description: e.target.value })}
                  placeholder="Clinical procedures or notes..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-emerald-600 h-16"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Priority</label>
                  <select
                    value={taskForm.priority}
                    onChange={(e) => setTaskForm({ ...taskForm, priority: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  >
                    <option value="Low">Low</option>
                    <option value="Medium">Medium</option>
                    <option value="High">High</option>
                    <option value="Critical">Critical</option>
                  </select>
                </div>

                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Due Date & Time</label>
                  <input
                    type="text"
                    value={taskForm.due_date}
                    onChange={(e) => setTaskForm({ ...taskForm, due_date: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Assigned Staff</label>
                  <select
                    value={taskForm.assigned_staff_id}
                    onChange={(e) => setTaskForm({ ...taskForm, assigned_staff_id: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  >
                    <option value="">-- Unassigned --</option>
                    {staff
                      .filter((s) => s.is_active && (normalizedRole !== 'DOCTOR' || (s.role || '').toLowerCase().includes('nurse') || s.user_id === userId || s.id === userId))
                      .map((s) => (
                        <option key={s.id} value={s.id}>{s.name} ({s.role})</option>
                      ))}
                  </select>
                </div>

                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Room / Suite</label>
                  <select
                    value={taskForm.room_id}
                    onChange={(e) => setTaskForm({ ...taskForm, room_id: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  >
                    <option value="">-- General Clinic --</option>
                    {rooms.map((r) => (
                      <option key={r.id} value={r.id}>Room {r.room_number} ({r.name})</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowTaskModal(false)}
                  className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Save Task
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 1B: EDIT TASK */}
      {showEditTaskModal && editingTask && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Pencil className="w-4 h-4 text-emerald-600" />
                <h3 className="font-bold text-sm text-slate-900">Edit Clinical Task</h3>
              </div>
              <button onClick={() => setShowEditTaskModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleUpdateTask} className="mt-4 space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Task Title *</label>
                <input
                  type="text"
                  required
                  value={editTaskForm.title}
                  onChange={(e) => setEditTaskForm({ ...editTaskForm, title: e.target.value })}
                  placeholder="Task title..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-emerald-600"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Description / Protocol</label>
                <textarea
                  value={editTaskForm.description}
                  onChange={(e) => setEditTaskForm({ ...editTaskForm, description: e.target.value })}
                  placeholder="Clinical procedures or notes..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-emerald-600 h-16"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Priority</label>
                  <select
                    value={editTaskForm.priority}
                    onChange={(e) => setEditTaskForm({ ...editTaskForm, priority: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  >
                    <option value="Low">Low</option>
                    <option value="Medium">Medium</option>
                    <option value="High">High</option>
                    <option value="Critical">Critical</option>
                  </select>
                </div>

                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Status</label>
                  <select
                    value={editTaskForm.status}
                    onChange={(e) => setEditTaskForm({ ...editTaskForm, status: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  >
                    <option value="Pending">Pending</option>
                    <option value="In Progress">In Progress</option>
                    <option value="Completed">Completed</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Due Date & Time</label>
                <input
                  type="text"
                  value={editTaskForm.due_date}
                  onChange={(e) => setEditTaskForm({ ...editTaskForm, due_date: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Assigned Staff</label>
                  <select
                    value={editTaskForm.assigned_staff_id}
                    onChange={(e) => setEditTaskForm({ ...editTaskForm, assigned_staff_id: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  >
                    <option value="">-- Unassigned --</option>
                    {staff
                      .filter((s) => (s.is_active || s.id === editTaskForm.assigned_staff_id) && (normalizedRole !== 'DOCTOR' || (s.role || '').toLowerCase().includes('nurse') || s.user_id === userId || s.id === userId || s.id === editTaskForm.assigned_staff_id))
                      .map((s) => (
                        <option key={s.id} value={s.id}>{s.name} ({s.role}){!s.is_active ? ' [Inactive]' : ''}</option>
                      ))}
                  </select>
                </div>

                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Room / Suite</label>
                  <select
                    value={editTaskForm.room_id}
                    onChange={(e) => setEditTaskForm({ ...editTaskForm, room_id: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  >
                    <option value="">-- General Clinic --</option>
                    {rooms.map((r) => (
                      <option key={r.id} value={r.id}>Room {r.room_number} ({r.name})</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowEditTaskModal(false)}
                  className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: ADD CHECKLIST */}
      {showChecklistModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-sm text-slate-900">New Safety Checklist</h3>
              <button onClick={() => setShowChecklistModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateChecklist} className="mt-4 space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Checklist Title *</label>
                <input
                  type="text"
                  required
                  value={checklistForm.title}
                  onChange={(e) => setChecklistForm({ ...checklistForm, title: e.target.value })}
                  placeholder="e.g. End-of-Day Narcotic Safe Verification"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-emerald-600"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Category</label>
                  <select
                    value={checklistForm.category}
                    onChange={(e) => setChecklistForm({ ...checklistForm, category: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  >
                    <option value="Sterilization">Sterilization</option>
                    <option value="Hygiene">Hygiene</option>
                    <option value="Emergency">Emergency</option>
                    <option value="Pharmacy">Pharmacy</option>
                  </select>
                </div>

                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Frequency</label>
                  <select
                    value={checklistForm.frequency}
                    onChange={(e) => setChecklistForm({ ...checklistForm, frequency: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  >
                    <option value="Daily">Daily</option>
                    <option value="Weekly">Weekly</option>
                    <option value="Monthly">Monthly</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Assigned Staff</label>
                <select
                  value={checklistForm.assigned_staff_id}
                  onChange={(e) => setChecklistForm({ ...checklistForm, assigned_staff_id: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                >
                  <option value="">-- Unassigned --</option>
                  {staff.filter((s) => s.is_active).map((s) => (
                    <option key={s.id} value={s.id}>{s.name} ({s.role})</option>
                  ))}
                </select>
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowChecklistModal(false)}
                  className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Create Checklist
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2B: EDIT CHECKLIST */}
      {showEditChecklistModal && editingChecklist && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Pencil className="w-4 h-4 text-emerald-600" />
                <h3 className="font-bold text-sm text-slate-900">Edit Safety Checklist Item</h3>
              </div>
              <button onClick={() => setShowEditChecklistModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleUpdateChecklist} className="mt-4 space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Checklist Title / Description *</label>
                <input
                  type="text"
                  required
                  value={editChecklistForm.title}
                  onChange={(e) => setEditChecklistForm({ ...editChecklistForm, title: e.target.value })}
                  placeholder="e.g. End-of-Day Narcotic Safe Verification"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-emerald-600"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Category</label>
                  <select
                    value={editChecklistForm.category}
                    onChange={(e) => setEditChecklistForm({ ...editChecklistForm, category: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  >
                    <option value="Sterilization">Sterilization</option>
                    <option value="Hygiene">Hygiene</option>
                    <option value="Emergency">Emergency</option>
                    <option value="Pharmacy">Pharmacy</option>
                    <option value="Safety">Safety</option>
                  </select>
                </div>

                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Frequency</label>
                  <select
                    value={editChecklistForm.frequency}
                    onChange={(e) => setEditChecklistForm({ ...editChecklistForm, frequency: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  >
                    <option value="Daily">Daily</option>
                    <option value="Weekly">Weekly</option>
                    <option value="Monthly">Monthly</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Assigned Staff</label>
                <select
                  value={editChecklistForm.assigned_staff_id}
                  onChange={(e) => setEditChecklistForm({ ...editChecklistForm, assigned_staff_id: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                >
                  <option value="">-- Unassigned --</option>
                  {staff.filter((s) => s.is_active || s.id === editChecklistForm.assigned_staff_id).map((s) => (
                    <option key={s.id} value={s.id}>{s.name} ({s.role}){!s.is_active ? ' [Inactive]' : ''}</option>
                  ))}
                </select>
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowEditChecklistModal(false)}
                  className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: ADD INVENTORY ITEM */}
      {showInventoryModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-sm text-slate-900">Add Supply Inventory</h3>
              <button onClick={() => setShowInventoryModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateInventory} className="mt-4 space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Item Name *</label>
                <input
                  type="text"
                  required
                  value={inventoryForm.item_name}
                  onChange={(e) => setInventoryForm({ ...inventoryForm, item_name: e.target.value })}
                  placeholder="e.g. Sterile Surgical Gauze 4x4"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-emerald-600"
                />
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Current Stock</label>
                  <input
                    type="number"
                    value={inventoryForm.current_stock}
                    onChange={(e) => setInventoryForm({ ...inventoryForm, current_stock: parseInt(e.target.value) || 0 })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Min Threshold</label>
                  <input
                    type="number"
                    value={inventoryForm.min_threshold}
                    onChange={(e) => setInventoryForm({ ...inventoryForm, min_threshold: parseInt(e.target.value) || 0 })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Unit</label>
                  <input
                    type="text"
                    value={inventoryForm.unit}
                    onChange={(e) => setInventoryForm({ ...inventoryForm, unit: e.target.value })}
                    placeholder="boxes"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Expiry Date</label>
                  <input
                    type="date"
                    value={inventoryForm.expiry_date}
                    onChange={(e) => setInventoryForm({ ...inventoryForm, expiry_date: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  />
                </div>

                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Room Location</label>
                  <select
                    value={inventoryForm.room_id}
                    onChange={(e) => setInventoryForm({ ...inventoryForm, room_id: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  >
                    <option value="">Central Supply</option>
                    {rooms.map((r) => (
                      <option key={r.id} value={r.id}>Room {r.room_number}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Batch No.</label>
                  <input
                    type="text"
                    value={inventoryForm.batch_number}
                    onChange={(e) => setInventoryForm({ ...inventoryForm, batch_number: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Supplier</label>
                  <input
                    type="text"
                    value={inventoryForm.supplier}
                    onChange={(e) => setInventoryForm({ ...inventoryForm, supplier: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Unit Price</label>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={inventoryForm.purchase_price}
                    onChange={(e) => setInventoryForm({ ...inventoryForm, purchase_price: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  />
                </div>
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowInventoryModal(false)}
                  className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Save Item
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editingInventory && canManageInventoryItem(editingInventory) && (
        <EditInventoryModal
          item={editingInventory}
          rooms={rooms}
          apiBase={apiBase}
          getHeaders={getHeaders}
          onClose={() => setEditingInventory(null)}
          onSaved={fetchData}
          showToast={showToast}
        />
      )}
      {adjustingInventory && canManageInventoryItem(adjustingInventory) && (
        <AdjustStockModal
          item={adjustingInventory}
          apiBase={apiBase}
          getHeaders={getHeaders}
          onClose={() => setAdjustingInventory(null)}
          onSaved={fetchData}
          showToast={showToast}
        />
      )}

      {showInventoryImportModal && canManageInventory && (
        <InventoryImportModal
          apiBase={apiBase}
          getHeaders={getHeaders}
          rooms={rooms}
          onClose={() => setShowInventoryImportModal(false)}
          onImported={fetchData}
          showToast={showToast}
        />
      )}

      {/* MODAL 4: ADD ROOM */}
      {showRoomModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-sm text-slate-900">Add Clinical Room</h3>
              <button onClick={() => setShowRoomModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateRoom} className="mt-4 space-y-3.5 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Room Number *</label>
                  <input
                    type="text"
                    required
                    value={roomForm.room_number}
                    onChange={(e) => setRoomForm({ ...roomForm, room_number: e.target.value })}
                    placeholder="e.g. 105"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-emerald-600"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Room Type</label>
                  <select
                    value={roomForm.room_type}
                    onChange={(e) => setRoomForm({ ...roomForm, room_type: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                  >
                    <option value="Exam">Exam Suite</option>
                    <option value="Surgery">Procedure / Surgery</option>
                    <option value="Triage">Triage & Trauma</option>
                    <option value="Consultation">Consultation</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Room Name / Label *</label>
                <input
                  type="text"
                  required
                  value={roomForm.name}
                  onChange={(e) => setRoomForm({ ...roomForm, name: e.target.value })}
                  placeholder="e.g. Ultrasound & Cardiac Care Bay"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-emerald-600"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Initial Status</label>
                <select
                  value={roomForm.status}
                  onChange={(e) => setRoomForm({ ...roomForm, status: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                >
                  <option value="Available">Available</option>
                  <option value="Occupied">Occupied</option>
                  <option value="Turnover">Turnover Required</option>
                </select>
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowRoomModal(false)}
                  className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Add Room
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
                <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold">
                  <ShieldCheck className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900">Switch Tenant & User Profile</h3>
                  <p className="text-[11px] text-slate-500">Multi-Tenant Isolation & Role-Based Access Control</p>
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
              {/* Manual Selection */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Company / Tenant</label>
                  <select
                    value={modalTenant}
                    onChange={(e) => setModalTenant(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-medium text-slate-800 focus:bg-white focus:outline-none focus:border-emerald-600"
                  >
                    <option value="tenant-001">Apex Health (tenant-001)</option>
                    <option value="tenant-002">Metro Health (tenant-002)</option>
                  </select>
                </div>

                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Assigned Role</label>
                  <select
                    value={modalRole}
                    onChange={(e) => setModalRole(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-medium text-slate-800 focus:bg-white focus:outline-none focus:border-emerald-600"
                  >
                    <option value="CLINIC_OWNER">Clinic Owner (Admin)</option>
                    <option value="ATTENDING_PHYSICIAN">Attending Physician (Doctor)</option>
                    <option value="NURSE_STAFF">Nurse Staff (Operator)</option>
                    <option value="INVENTORY_MANAGER">Inventory Manager (Staff)</option>
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
                            ? 'bg-emerald-50 border-emerald-400 ring-2 ring-emerald-500/20'
                            : 'bg-slate-50/70 border-slate-200 hover:bg-slate-100 hover:border-slate-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-slate-900 text-xs truncate">{p.userName}</span>
                          <span className="text-[9px] px-1 py-0.2 rounded font-mono bg-slate-200/80 text-slate-700">
                            {p.tenantId}
                          </span>
                        </div>
                        <p className="text-[10px] text-emerald-700 font-semibold mt-0.5">{p.roleLabel}</p>
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
                    className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-semibold text-xs shadow-xs transition-all"
                  >
                    Apply Session
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 6: INVITE STAFF MODAL */}
      {showInviteModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3.5 border-b border-slate-100">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold">
                  <UserPlus className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900">Invite Clinical Staff</h3>
                  <p className="text-[11px] text-slate-500">Generate a cryptographically secure invitation code</p>
                </div>
              </div>
              <button
                onClick={() => setShowInviteModal(false)}
                className="text-slate-400 hover:text-slate-600 rounded-lg p-1 hover:bg-slate-100 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {generatedInvite ? (
              <div className="mt-4 space-y-4">
                <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-center space-y-2">
                  <p className="text-xs font-semibold text-emerald-800">Invitation Code Generated!</p>
                  <div className="flex items-center justify-center gap-2">
                    <span className="font-mono text-xl font-bold tracking-wider text-slate-900 bg-white px-3 py-1.5 rounded-lg border border-emerald-300 shadow-xs">
                      {generatedInvite.code}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(generatedInvite.code);
                        setCopiedCodeId(generatedInvite.id);
                        setTimeout(() => setCopiedCodeId(null), 2000);
                      }}
                      className="p-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg shadow-xs transition-colors cursor-pointer"
                      title="Copy Code"
                    >
                      {copiedCodeId === generatedInvite.id ? <Check className="w-4 h-4 text-white" /> : <Copy className="w-4 h-4 text-white" />}
                    </button>
                  </div>
                  <p className="text-[11px] text-slate-600 pt-1">
                    Role: <strong>{generatedInvite.role}</strong> • Limit: <strong>{generatedInvite.max_uses} use(s)</strong> • Expires in <strong>{inviteExpiresDays} days</strong>
                  </p>
                </div>

                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs text-slate-600 space-y-1">
                  <p className="font-semibold text-slate-800">Onboarding Instructions:</p>
                  <p>1. Send this code to your new staff member.</p>
                  <p>2. They register at PractiCare using <strong>Join via Invitation</strong>.</p>
                  <p>3. Once they register, review and approve their request in <strong>Pending Join Requests</strong>.</p>
                </div>

                <div className="pt-2 flex justify-end">
                  <button
                    type="button"
                    onClick={() => {
                      setGeneratedInvite(null);
                      setShowInviteModal(false);
                    }}
                    className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-semibold shadow-xs cursor-pointer"
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleCreateInvitation} className="mt-4 space-y-3.5 text-xs">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Assigned Clinical Role *</label>
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-medium text-slate-800 focus:bg-white focus:outline-none focus:border-emerald-600"
                  >
                    <option value="ATTENDING_PHYSICIAN">Attending Physician (Doctor)</option>
                    <option value="NURSE_STAFF">Nurse Staff (Operator)</option>
                    <option value="INVENTORY_MANAGER">Inventory Manager (Staff)</option>
                  </select>
                  <p className="text-[10px] text-slate-400 mt-0.5">Staff invitations never grant Owner privileges automatically.</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="font-semibold text-slate-700 block mb-1">Max Uses</label>
                    <select
                      value={inviteMaxUses}
                      onChange={(e) => setInviteMaxUses(Number(e.target.value))}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-medium text-slate-800 focus:bg-white focus:outline-none focus:border-emerald-600"
                    >
                      <option value="1">1 use (Single Applicant)</option>
                      <option value="3">3 uses</option>
                      <option value="5">5 uses</option>
                      <option value="10">10 uses</option>
                      <option value="25">25 uses</option>
                    </select>
                  </div>

                  <div>
                    <label className="font-semibold text-slate-700 block mb-1">Expiration</label>
                    <select
                      value={inviteExpiresDays}
                      onChange={(e) => setInviteExpiresDays(Number(e.target.value))}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-medium text-slate-800 focus:bg-white focus:outline-none focus:border-emerald-600"
                    >
                      <option value="1">24 Hours</option>
                      <option value="3">3 Days</option>
                      <option value="7">7 Days (Standard)</option>
                      <option value="14">14 Days</option>
                      <option value="30">30 Days</option>
                    </select>
                  </div>
                </div>

                <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setShowInviteModal(false)}
                    className="px-3.5 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-semibold shadow-xs flex items-center gap-1.5 cursor-pointer"
                  >
                    <Key className="w-3.5 h-3.5" />
                    <span>Generate Code</span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* MODAL 6: STAFF PROFILE & SHIFT AVAILABILITY */}
      {showStaffProfileModal && selectedStaffProfile && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-xl w-full p-6 animate-in fade-in zoom-in-95 max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="flex items-start justify-between pb-4 border-b border-slate-100">
              <div className="flex items-center gap-3.5">
                <div
                  className={`w-14 h-14 rounded-2xl font-bold flex items-center justify-center text-xl shadow-md ${
                    selectedStaffProfile.is_active
                      ? 'bg-gradient-to-br from-emerald-500 to-teal-700 text-white shadow-emerald-600/20'
                      : 'bg-slate-200 text-slate-600'
                  }`}
                >
                  {selectedStaffProfile.name.split(' ').map((n) => n[0]).join('').slice(0, 2)}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-base text-slate-900">{selectedStaffProfile.name}</h3>
                    {((selectedStaffProfile.user_id && selectedStaffProfile.user_id === userId) || selectedStaffProfile.name === userName) && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-600 text-white shadow-2xs">
                        You
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 font-medium">{selectedStaffProfile.role}</p>
                  
                  {/* Status Badges */}
                  <div className="flex items-center gap-1.5 mt-1.5">
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                        selectedStaffProfile.is_active
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : 'bg-rose-50 text-rose-700 border border-rose-200'
                      }`}
                    >
                      Account: {selectedStaffProfile.is_active ? 'Active' : 'Inactive'}
                    </span>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                        selectedStaffProfile.on_shift !== false
                          ? 'bg-sky-50 text-sky-700 border border-sky-200'
                          : 'bg-slate-100 text-slate-600 border border-slate-200'
                      }`}
                    >
                      Shift: {selectedStaffProfile.on_shift !== false ? 'On Shift' : 'Off Duty'}
                    </span>
                    {selectedStaffProfile.membership_status && (
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200">
                        {selectedStaffProfile.membership_status}
                      </span>
                    )}
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setShowStaffProfileModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Profile Information Sections */}
            <div className="py-4 space-y-5 text-xs">
              {/* Section 1: Verified Professional Details */}
              <div className="space-y-2">
                <h4 className="font-bold text-xs uppercase tracking-wider text-slate-400">
                  Staff Information & Practice Assignment
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 bg-slate-50 p-3.5 rounded-xl border border-slate-200/80">
                  <div>
                    <span className="text-slate-400 block text-[11px]">Staff ID</span>
                    <span className="font-mono font-semibold text-slate-800">{selectedStaffProfile.id}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[11px]">Email Address</span>
                    <span className="font-semibold text-slate-800">{selectedStaffProfile.email || 'Confidential / On File'}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[11px]">Clinical Department</span>
                    <span className="font-semibold text-slate-800">{selectedStaffProfile.department || 'Clinical Operations'}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[11px]">Affiliated Practice</span>
                    <span className="font-semibold text-slate-800">{selectedStaffProfile.practice_name || companyName || 'Primary Care'}</span>
                  </div>
                  {selectedStaffProfile.created_at && (
                    <div>
                      <span className="text-slate-400 block text-[11px]">Enrolled Date</span>
                      <span className="font-medium text-slate-700">
                        {new Date(selectedStaffProfile.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  )}
                  <div>
                    <span className="text-slate-400 block text-[11px]">Tenant Partition</span>
                    <span className="font-mono text-emerald-700 font-semibold">{tenantId}</span>
                  </div>
                </div>
              </div>

              {/* Section 2: Self-Service Shift Management */}
              <div className="space-y-2 pt-1 border-t border-slate-100">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-xs uppercase tracking-wider text-slate-400">
                    Shift Availability & Self-Service
                  </h4>
                  <span className="text-[10px] text-slate-400">Personal Availability</span>
                </div>

                <div className="bg-sky-50/50 rounded-xl border border-sky-100 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-bold text-slate-800 text-xs">
                        Current Shift Status: {selectedStaffProfile.on_shift !== false ? 'On Shift (Available)' : 'Off Duty (Unavailable)'}
                      </p>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        {selectedStaffProfile.on_shift !== false
                          ? 'You are active and visible in provider lists for clinical task assignments and exam room rounds.'
                          : 'You are off duty. Switch to On Shift when commencing clinical service.'}
                      </p>
                    </div>
                  </div>

                  {/* Contextual Action for Current User */}
                  {((selectedStaffProfile.user_id && selectedStaffProfile.user_id === userId) || selectedStaffProfile.name === userName) ? (
                    <div>
                      {!selectedStaffProfile.is_active ? (
                        <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-[11px]">
                          Your account is currently inactive. Contact your Clinic Owner to activate your account before starting a shift.
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          {selectedStaffProfile.on_shift !== false ? (
                            <button
                              type="button"
                              onClick={() => handleSelfShiftToggle(true)}
                              className="px-4 py-2 bg-slate-800 hover:bg-slate-900 text-white rounded-xl font-semibold text-xs transition-all shadow-xs flex items-center gap-1.5 cursor-pointer"
                            >
                              <Clock className="w-3.5 h-3.5 text-amber-400" />
                              <span>End Shift / Set Off Duty</span>
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => handleSelfShiftToggle(false)}
                              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-semibold text-xs transition-all shadow-xs flex items-center gap-1.5 cursor-pointer"
                            >
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-200" />
                              <span>Start Shift / Set On Shift</span>
                            </button>
                          )}
                          <span className="text-[11px] text-slate-500">
                            Self-service shift update authenticated to your session.
                          </span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-[11px] text-slate-500 italic">
                      This staff member self-manages their shift availability through their personal session.
                    </p>
                  )}
                </div>
              </div>

              {/* Section 3: Owner-Only Administrative Controls */}
              {userRole === 'CLINIC_OWNER' && (
                <div className="space-y-2 pt-2 border-t border-slate-100">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Shield className="w-4 h-4 text-emerald-700" />
                      <h4 className="font-bold text-xs uppercase tracking-wider text-slate-900">
                        Clinic Owner Governance
                      </h4>
                    </div>
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                      Administrative Access
                    </span>
                  </div>

                  <div className="bg-slate-50 rounded-xl border border-slate-200 p-4 space-y-3.5">
                    {/* Account Activation / Deactivation */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-3 border-b border-slate-200/80">
                      <div>
                        <p className="font-bold text-slate-800 text-xs">Account Enablement (is_active)</p>
                        <p className="text-[11px] text-slate-500 mt-0.5">
                          Inactive accounts cannot log in or make API calls. Historical records are preserved.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleToggleStaffStatus(selectedStaffProfile.id, selectedStaffProfile.is_active)}
                        className={`px-3.5 py-1.5 rounded-xl font-semibold text-xs transition-all cursor-pointer shrink-0 ${
                          selectedStaffProfile.is_active
                            ? 'bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-300'
                            : 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs'
                        }`}
                      >
                        {selectedStaffProfile.is_active ? 'Deactivate Account' : 'Activate Account'}
                      </button>
                    </div>

                    {/* Administrative Shift Override */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                      <div>
                        <div className="flex items-center gap-1.5">
                          <p className="font-bold text-slate-800 text-xs">Administrative Shift Override</p>
                          <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-amber-100 text-amber-800 border border-amber-300">
                            Override
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500 mt-0.5">
                          Optionally override staff shift status in operational emergencies. Action is recorded in audit logs.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleToggleStaffShift(selectedStaffProfile.id, selectedStaffProfile.on_shift !== false)}
                        className="px-3.5 py-1.5 rounded-xl font-medium text-xs text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 transition-all cursor-pointer shrink-0"
                      >
                        {selectedStaffProfile.on_shift !== false ? 'Override: Set Off Duty' : 'Override: Set On Shift'}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="pt-3 border-t border-slate-100 flex justify-end">
              <button
                type="button"
                onClick={() => setShowStaffProfileModal(false)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl font-semibold text-xs transition-colors cursor-pointer"
              >
                Close Profile
              </button>
            </div>
          </div>
        </div>
      )}

      {/* DRAWER: LANGGRAPH AUTONOMOUS AI OPERATIONS AGENT */}
      {showAICopilot && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex justify-end z-50 animate-in fade-in duration-200">
          <div className="w-full max-w-xl bg-white h-full shadow-2xl flex flex-col border-l border-slate-200 animate-in slide-in-from-right duration-250">
            {/* Drawer Header */}
            <div className="p-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-500 text-white flex items-center justify-center shadow-md shadow-emerald-500/20">
                  <Bot className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-sm text-slate-900">PractiCare Operations Agent</h3>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-semibold border border-emerald-200">
                      LangGraph Engine
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Tenant: <strong className="font-mono text-slate-700">{tenantId}</strong> • Role: <strong className="text-emerald-700">{userRole}</strong>
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowAICopilot(false)}
                className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 rounded-lg transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Private Conversation Selector Bar */}
            <div className="px-4 py-2 border-b border-slate-200 bg-white flex items-center justify-between text-xs shrink-0">
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setShowConversationList(!showConversationList)}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-800 font-medium transition-colors cursor-pointer max-w-[280px]"
                >
                  <MessageSquare className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  <span className="truncate">
                    {activeConversationId
                      ? (conversations.find((c) => c.id === activeConversationId)?.title || 'Current Consultation')
                      : 'New Consultation'}
                  </span>
                  <ChevronDown className="w-3 h-3 text-slate-400 shrink-0 ml-1" />
                </button>

                {/* Dropdown list of owned conversations */}
                {showConversationList && (
                  <div className="absolute left-0 mt-1 w-80 bg-white border border-slate-200 rounded-xl shadow-xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
                    <div className="p-2.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
                      <span className="text-[11px] font-bold text-slate-700 flex items-center gap-1">
                        <History className="w-3.5 h-3.5 text-emerald-600" /> Private Consultations
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {conversations.length} saved
                      </span>
                    </div>
                    <div className="max-h-60 overflow-y-auto p-1 divide-y divide-slate-100">
                      {conversations.length === 0 ? (
                        <div className="p-4 text-center text-[11px] text-slate-500">
                          No previous private consultations found for this account.
                        </div>
                      ) : (
                        conversations.map((c) => (
                          <div
                            key={c.id}
                            onClick={() => handleSelectConversation(c.id)}
                            className={`p-2 rounded-lg flex items-center justify-between hover:bg-slate-50 cursor-pointer transition-colors ${
                              c.id === activeConversationId ? 'bg-emerald-50/70 border-l-2 border-emerald-500' : ''
                            }`}
                          >
                            <div className="min-w-0 pr-2">
                              <p className="font-semibold text-slate-800 text-[11px] truncate">
                                {c.title}
                              </p>
                              <span className="text-[9px] text-slate-400 font-mono">
                                {new Date(c.updated_at).toLocaleDateString()} • {new Date(c.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                              </span>
                            </div>
                            <button
                              type="button"
                              onClick={(e) => handleDeleteConversation(c.id, e)}
                              title="Delete conversation"
                              className="p-1 text-slate-400 hover:text-rose-600 rounded hover:bg-rose-50 transition-colors shrink-0"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>

              <button
                type="button"
                onClick={handleNewChat}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-700 font-semibold text-xs border border-emerald-200 transition-colors cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>New Chat</span>
              </button>
            </div>

            {/* Quick Prompts Bar */}
            <div className="px-4 py-2 bg-slate-100/70 border-b border-slate-200 flex items-center gap-1.5 overflow-x-auto text-[11px] shrink-0">
              <span className="text-slate-500 font-medium shrink-0 flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-emerald-600" /> Prompts:
              </span>
              <button
                onClick={() => handleSendAIMessage("I want to know how my team is performing the tasks.")}
                disabled={isAILoading}
                className="px-2.5 py-1 rounded-full bg-white border border-slate-200 hover:border-emerald-400 hover:text-emerald-700 text-slate-700 font-medium shrink-0 transition-all cursor-pointer disabled:opacity-50"
              >
                Team Performance
              </button>
              <button
                onClick={() => handleSendAIMessage("Check our overdue tasks, identify the responsible staff, and prepare a follow-up plan.")}
                disabled={isAILoading}
                className="px-2.5 py-1 rounded-full bg-white border border-slate-200 hover:border-emerald-400 hover:text-emerald-700 text-slate-700 font-medium shrink-0 transition-all cursor-pointer disabled:opacity-50"
              >
                Overdue Tasks & Staff
              </button>
              <button
                onClick={() => handleSendAIMessage("How is our team's performance, and which rooms need attention?")}
                disabled={isAILoading}
                className="px-2.5 py-1 rounded-full bg-white border border-slate-200 hover:border-emerald-400 hover:text-emerald-700 text-slate-700 font-medium shrink-0 transition-all cursor-pointer disabled:opacity-50"
              >
                Multi-Step Operations
              </button>
            </div>

            {/* Messages Chat Log */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {aiMessages.map((msg, index) => (
                <div
                  key={index}
                  className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
                >
                  <div
                    className={`max-w-[90%] rounded-2xl p-4 text-xs shadow-xs ${
                      msg.role === 'user'
                        ? 'bg-emerald-600 text-white rounded-br-xs'
                        : 'bg-slate-50 border border-slate-200/90 text-slate-800 rounded-bl-xs'
                    }`}
                  >
                    {/* Tool executions & Agent mode header for assistant */}
                    {msg.role === 'assistant' && (
                      <div className="mb-2.5 pb-2 border-b border-slate-200 flex flex-wrap items-center gap-1.5 text-[10px]">
                        {msg.metrics?.agent_mode && (
                          <span className={`px-2 py-0.5 rounded-full font-mono font-bold border ${
                            msg.metrics.agent_mode === 'gemini'
                              ? 'bg-purple-50 text-purple-700 border-purple-200'
                              : 'bg-slate-100 text-slate-700 border-slate-200'
                          }`}>
                            {msg.metrics.agent_mode === 'gemini' ? `🤖 Gemini (${msg.metrics.model_name || 'gemini-flash-latest'})` : '⚙️ Deterministic Engine'}
                          </span>
                        )}
                        {msg.toolCalls && msg.toolCalls.length > 0 && (
                          <>
                            <span className="font-bold text-slate-500 uppercase tracking-wider ml-1">
                              Tools:
                            </span>
                            {msg.toolCalls.map((tc, tcIdx) => (
                              <span
                                key={tcIdx}
                                className={`font-mono px-2 py-0.5 rounded-full font-semibold border flex items-center gap-1 ${
                                  tc.status === 'SUCCESS'
                                    ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                                    : 'bg-rose-50 text-rose-800 border-rose-300'
                                }`}
                              >
                                <span className={`w-1.5 h-1.5 rounded-full ${tc.status === 'SUCCESS' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                                {tc.tool}
                              </span>
                            ))}
                          </>
                        )}
                        {(msg.metrics?.total_latency_ms || msg.metrics?.total_duration_ms) && (
                          <span className="font-mono text-slate-400 ml-auto flex items-center gap-2">
                            {msg.metrics?.total_tokens ? (
                              <span>🪙 {msg.metrics.total_tokens} toks</span>
                            ) : null}
                            <span>⏱️ {msg.metrics.total_latency_ms || msg.metrics.total_duration_ms}ms</span>
                          </span>
                        )}
                      </div>
                    )}

                    {/* Message content */}
                    {msg.role === 'user' ? (
                      <p className="font-medium whitespace-pre-wrap">{msg.content}</p>
                    ) : (
                      <div className="space-y-1">{renderAIMarkdown(msg.content)}</div>
                    )}

                    {/* Human-In-The-Loop Approval Card */}
                    {msg.approvalPending && (
                      <div className="mt-3.5 p-3 rounded-xl bg-amber-50 border border-amber-300 text-amber-950">
                        <div className="flex items-center gap-2 mb-1.5">
                          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                          <h4 className="font-bold text-xs">Human Authorization Required</h4>
                        </div>
                        <p className="text-[11px] text-amber-900 mb-2 whitespace-pre-line">
                          {msg.approvalPending.description}
                        </p>
                        <div className="text-[10px] font-mono bg-amber-100/60 p-2 rounded-lg mb-2.5">
                          <div><strong>Tool:</strong> {msg.approvalPending.tool_name}</div>
                          <div><strong>Token:</strong> {msg.approvalPending.approval_id}</div>
                          <div><strong>Arguments:</strong> {JSON.stringify(msg.approvalPending.arguments)}</div>
                        </div>
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleResolveApproval(msg.approvalPending!.approval_id, 'reject')}
                            disabled={isAILoading}
                            className="px-3 py-1 rounded-lg border border-slate-300 bg-white hover:bg-slate-100 text-slate-700 text-xs font-semibold transition-all cursor-pointer disabled:opacity-50"
                          >
                            Reject
                          </button>
                          <button
                            onClick={() => handleResolveApproval(msg.approvalPending!.approval_id, 'approve')}
                            disabled={isAILoading}
                            className="px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-xs transition-all cursor-pointer disabled:opacity-50"
                          >
                            Approve Action
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {/* In-Flight Thinking Indicator */}
              {isAILoading && (
                <div className="flex flex-col items-start">
                  <div className="bg-slate-50 border border-slate-200 rounded-2xl p-3.5 text-xs text-slate-600 flex items-center gap-2.5 shadow-xs">
                    <RefreshCw className="w-4 h-4 animate-spin text-emerald-600" />
                    <span>LangGraph agent reasoning & executing authorized tools through Gateway...</span>
                  </div>
                </div>
              )}
            </div>

            {/* Input Submission Form */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSendAIMessage();
              }}
              className="p-3 border-t border-slate-200 bg-slate-50 flex items-center gap-2 shrink-0"
            >
              <input
                type="text"
                value={aiInput}
                onChange={(e) => setAiInput(e.target.value)}
                placeholder="Ask about team performance, rooms, tasks..."
                disabled={isAILoading}
                className="flex-1 px-3.5 py-2.5 bg-white border border-slate-200 rounded-xl text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600 disabled:bg-slate-100"
              />
              <button
                type="submit"
                disabled={isAILoading || !aiInput.trim()}
                className="px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white rounded-xl font-semibold text-xs shadow-xs transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Send</span>
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
