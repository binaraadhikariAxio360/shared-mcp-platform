'use client';

import React, { useState, useEffect } from 'react';
import {
  LayoutDashboard,
  Home,
  Users,
  Briefcase,
  UserCheck,
  Building2,
  DollarSign,
  TrendingUp,
  MapPin,
  Bed,
  Bath,
  Maximize2,
  CheckCircle2,
  AlertCircle,
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
  Tag,
  ShieldCheck,
  ArrowRight,
  Award,
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
    tenantName: 'Austin Premier Realty Network',
    userRole: 'PRINCIPAL_BROKER',
    userId: 'user-broker-001',
    userName: 'Julian Montgomery',
    roleLabel: 'Principal Broker (Admin)',
    description: 'Full CRUD on listings, buyers, deals, escrow stages, and agents.',
  },
  {
    tenantId: 'tenant-001',
    tenantName: 'Austin Premier Realty Network',
    userRole: 'LICENSED_AGENT',
    userId: 'user-agent-001',
    userName: 'Sarah Sterling',
    roleLabel: 'Licensed Agent (Realtor)',
    description: 'Full CRUD on own listings and buyers; update listing status; read deals.',
  },
  {
    tenantId: 'tenant-001',
    tenantName: 'Austin Premier Realty Network',
    userRole: 'ESCROW_OFFICER',
    userId: 'user-escrow-001',
    userName: 'Daniel Craig',
    roleLabel: 'Escrow Officer (Compliance)',
    description: 'Full CRUD on deals/contracts and closing stages; read-only on listings.',
  },
  {
    tenantId: 'tenant-001',
    tenantName: 'Austin Premier Realty Network',
    userRole: 'CLIENT_BUYER',
    userId: 'user-buyer-001',
    userName: 'Lucas Davenport',
    roleLabel: 'Client Buyer (Viewer)',
    description: 'Read-only view on available properties; cannot modify listings or deals.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'Lone Star Luxury Realty',
    userRole: 'PRINCIPAL_BROKER',
    userId: 'user-broker-002',
    userName: 'Victoria Sterling',
    roleLabel: 'Principal Broker (Admin)',
    description: 'Full brokerage control across Dallas-Fort Worth luxury inventory.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'Lone Star Luxury Realty',
    userRole: 'LICENSED_AGENT',
    userId: 'user-agent-002',
    userName: 'Brandon Hayes',
    roleLabel: 'Licensed Agent (Realtor)',
    description: 'Manage exclusive high-value ranch estates and buyer negotiations.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'Lone Star Luxury Realty',
    userRole: 'ESCROW_OFFICER',
    userId: 'user-escrow-002',
    userName: 'Monique Dupont',
    roleLabel: 'Escrow Officer (Compliance)',
    description: 'Coordinate title verification and closing transfers for Lone Star Realty.',
  },
  {
    tenantId: 'tenant-002',
    tenantName: 'Lone Star Luxury Realty',
    userRole: 'CLIENT_BUYER',
    userId: 'user-buyer-002',
    userName: 'Eleanor Vance',
    roleLabel: 'Client Buyer (Viewer)',
    description: 'Browse luxury property portfolio in read-only client mode.',
  },
];

interface PropertyListing {
  id: string;
  tenant_id: string;
  title: string;
  address: string;
  price: number;
  beds: number;
  baths: number;
  sqft: number;
  amenities: string;
  status: string; // AVAILABLE, UNDER_CONTRACT, CLOSED
  assigned_agent?: string;
}

interface BuyerProfile {
  id: string;
  tenant_id: string;
  name: string;
  budget: number;
  preferred_type: string;
  target_area: string;
  is_preapproved: boolean;
  target_property_id?: string;
  target_property_title?: string;
  affinity_score: number;
}

interface DealContract {
  id: string;
  tenant_id: string;
  property_id: string;
  buyer_id: string;
  property_title?: string;
  buyer_name?: string;
  contract_price: number;
  closing_date: string;
  stage: string; // OFFER, UNDER_CONTRACT, CLOSED
  commission_rate: number;
}

interface BrokerAgent {
  id: string;
  tenant_id: string;
  name: string;
  email: string;
  phone: string;
  license_no: string;
  active_listings_count: number;
}

interface DashboardSummary {
  tenant_id: string;
  brokerage_name: string;
  active_listings_count: number;
  under_contract_count: number;
  closed_count: number;
  total_listings_volume: number;
  under_contract_volume: number;
  matched_buyers_count: number;
  average_deal_size: number;
  stage_breakdown: Record<string, number>;
  pipeline_volume: number;
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

export default function PropSightsApp() {
  // Multi-Tenant & RBAC Session State
  const [tenantId, setTenantId] = useState('tenant-001');
  const [userRole, setUserRole] = useState('PRINCIPAL_BROKER');
  const [userId, setUserId] = useState('user-broker-001');
  const [userName, setUserName] = useState('Victoria Sterling');
  const [companyName, setCompanyName] = useState('Austin Premier Realty');
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isSessionChecked, setIsSessionChecked] = useState(false);

  // Dedicated SaaS Auth Portal State
  const [authTab, setAuthTab] = useState<'signin' | 'signup'>('signin');
  const [loginEmail, setLoginEmail] = useState('broker@austinrealty.com');
  const [loginPassword, setLoginPassword] = useState('password123');
  const [registerFullName, setRegisterFullName] = useState('');
  const [registerEmail, setRegisterEmail] = useState('');
  const [registerPassword, setRegisterPassword] = useState('');
  const [registerCompany, setRegisterCompany] = useState('');
  const [registerRole, setRegisterRole] = useState('PRINCIPAL_BROKER');
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(false);

  // Profile Switcher Modal State
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [modalTenant, setModalTenant] = useState('tenant-001');
  const [modalRole, setModalRole] = useState('PRINCIPAL_BROKER');

  const apiBase = 'http://localhost:5003';

  // Navigation state
  type TabType = 'dashboard' | 'properties' | 'buyers' | 'deals' | 'agents';
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');

  // Core Data
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [properties, setProperties] = useState<PropertyListing[]>([]);
  const [buyers, setBuyers] = useState<BuyerProfile[]>([]);
  const [deals, setDeals] = useState<DealContract[]>([]);
  const [agents, setAgents] = useState<BrokerAgent[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Filters
  const [propStatusFilter, setPropStatusFilter] = useState('ALL');
  const [buyerTypeFilter, setBuyerTypeFilter] = useState('ALL');
  const [dealStageFilter, setDealStageFilter] = useState('ALL');

  // Modals
  const [showPropModal, setShowPropModal] = useState(false);
  const [editingProp, setEditingProp] = useState<PropertyListing | null>(null);
  const [propForm, setPropForm] = useState({
    title: '',
    address: '',
    price: '',
    beds: '3',
    baths: '2.5',
    sqft: '2200',
    amenities: 'Balcony, Pool, Parking, Smart Home',
    status: 'AVAILABLE',
    assigned_agent: 'Sarah Sterling',
  });

  const [showBuyerModal, setShowBuyerModal] = useState(false);
  const [editingBuyer, setEditingBuyer] = useState<BuyerProfile | null>(null);
  const [buyerForm, setBuyerForm] = useState({
    name: '',
    budget: '',
    preferred_type: 'Single Family',
    target_area: 'Downtown Austin',
    is_preapproved: true,
    target_property_id: '',
    affinity_score: '95',
  });

  const [showDealModal, setShowDealModal] = useState(false);
  const [editingDeal, setEditingDeal] = useState<DealContract | null>(null);
  const [dealForm, setDealForm] = useState({
    property_id: '',
    buyer_id: '',
    contract_price: '',
    closing_date: '2026-11-20',
    stage: 'UNDER_CONTRACT',
    commission_rate: '0.03',
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
      text: "Good morning. PropSights Broker Intelligence is active and synchronized with PostgreSQL 16. How can I assist with luxury MLS inventory, buyer affinity matching, or escrow closings today?",
      timestamp: '09:00 AM',
    },
  ]);

  // Initial Data Fetching with Tenant & Role Isolation
  const fetchDataFor = async (tId: string, uRole: string, uId: string) => {
    setIsLoading(true);
    const headers = { 'x-tenant-id': tId, 'x-user-role': uRole, 'x-user-id': uId };

    try {
      const [sumRes, propRes, buyRes, dealRes, agtRes] = await Promise.all([
        fetch(`${apiBase}/api/v1/dashboard/summary`, { headers }).then((r) => r.json()).catch(() => null),
        fetch(`${apiBase}/api/v1/properties`, { headers }).then((r) => r.json()).catch(() => []),
        fetch(`${apiBase}/api/v1/buyers`, { headers }).then((r) => r.json()).catch(() => []),
        fetch(`${apiBase}/api/v1/deals`, { headers }).then((r) => r.json()).catch(() => []),
        fetch(`${apiBase}/api/v1/agents`, { headers }).then((r) => r.json()).catch(() => []),
      ]);

      if (sumRes && !sumRes.detail) setSummary(sumRes);
      if (Array.isArray(propRes)) setProperties(propRes);
      if (Array.isArray(buyRes)) setBuyers(buyRes);
      if (Array.isArray(dealRes)) setDeals(dealRes);
      if (Array.isArray(agtRes)) setAgents(agtRes);
    } catch (e) {
      console.error('Failed to load PropSights data:', e);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchData = () => fetchDataFor(tenantId, userRole, userId);

  // Mount Session Restoration
  useEffect(() => {
    try {
      const saved = localStorage.getItem('propsights_auth_session');
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
        localStorage.setItem('propsights_auth_session', JSON.stringify({ token: data.access_token, user: data.user }));
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
        localStorage.setItem('propsights_auth_session', JSON.stringify({ token: data.access_token, user: data.user }));
        setTenantId(data.user.tenant_id);
        setUserRole(data.user.role);
        setUserId(data.user.id);
        setUserName(data.user.name);
        setCompanyName(data.user.company_name || data.user.tenant_id);
        setIsLoggedIn(true);
        setShowAuthModal(false);
        fetchDataFor(data.user.tenant_id, data.user.role, data.user.id);
        showToast(`Brokerage registered for ${data.user.company_name}!`);
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
      tenantName: targetTenant === 'tenant-001' ? 'Austin Premier Realty Network' : 'Lone Star Luxury Realty',
      userRole: targetRole,
      userId: `user-${targetRole.toLowerCase()}-${targetTenant}`,
      userName: `User (${targetRole})`,
      roleLabel: targetRole,
      description: '',
    };

    setSummary(null);
    setProperties([]);
    setBuyers([]);
    setDeals([]);
    setAgents([]);

    setTenantId(targetTenant);
    setUserRole(targetRole);
    setUserId(profileMatch.userId);
    setUserName(profileMatch.userName);
    setCompanyName(profileMatch.tenantName);
    setIsLoggedIn(true);
    setShowAuthModal(false);

    localStorage.setItem('propsights_auth_session', JSON.stringify({
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
    localStorage.removeItem('propsights_auth_session');
    setSummary(null);
    setProperties([]);
    setBuyers([]);
    setDeals([]);
    setAgents([]);
    setIsLoggedIn(false);
    setUserRole('CLIENT_BUYER');
    setUserName('Guest Client');
    setCompanyName('');
    showToast('Signed out of session. Session purged.', 'info');
  };

  // ---------------------------------------------------------------------------
  // Property CRUD Handlers
  // ---------------------------------------------------------------------------
  const handleOpenCreateProp = () => {
    setEditingProp(null);
    setPropForm({
      title: '',
      address: '',
      price: '',
      beds: '3',
      baths: '2.5',
      sqft: '2200',
      amenities: 'Balcony, Pool, Parking, Smart Home',
      status: 'AVAILABLE',
      assigned_agent: 'Sarah Sterling',
    });
    setShowPropModal(true);
  };

  const handleOpenEditProp = (item: PropertyListing) => {
    setEditingProp(item);
    setPropForm({
      title: item.title,
      address: item.address,
      price: item.price.toString(),
      beds: item.beds.toString(),
      baths: item.baths.toString(),
      sqft: item.sqft.toString(),
      amenities: item.amenities || '',
      status: item.status,
      assigned_agent: item.assigned_agent || 'Sarah Sterling',
    });
    setShowPropModal(true);
  };

  const handleSaveProperty = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!propForm.title || !propForm.price) return;

    const payload = {
      title: propForm.title,
      address: propForm.address,
      price: parseFloat(propForm.price),
      beds: parseInt(propForm.beds) || 3,
      baths: parseFloat(propForm.baths) || 2.0,
      sqft: parseInt(propForm.sqft) || 2000,
      amenities: propForm.amenities,
      status: propForm.status,
      assigned_agent: propForm.assigned_agent,
    };

    try {
      let res;
      if (editingProp) {
        res = await fetch(`${apiBase}/api/v1/properties/${editingProp.id}`, {
          method: 'PUT',
          headers: getHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
      } else {
        res = await fetch(`${apiBase}/api/v1/properties`, {
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

      showToast(editingProp ? `Listing updated: ${payload.title}` : `New listing created: ${payload.title}`);
      setShowPropModal(false);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleTogglePropStatus = async (item: PropertyListing, nextStatus: string) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/properties/${item.id}`, {
        method: 'PUT',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ status: nextStatus }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission Denied: Cannot modify listing status', 'info');
        return;
      }

      setProperties((prev) =>
        prev.map((p) => (p.id === item.id ? { ...p, status: nextStatus } : p))
      );
      showToast(`Listing ${item.title} status: ${nextStatus}`);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteProperty = async (id: string) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/properties/${id}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Delete failed (Permission Denied)', 'info');
        return;
      }

      setProperties((prev) => prev.filter((p) => p.id !== id));
      showToast('Property listing removed');
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  // ---------------------------------------------------------------------------
  // Buyer CRUD Handlers
  // ---------------------------------------------------------------------------
  const handleOpenCreateBuyer = () => {
    setEditingBuyer(null);
    setBuyerForm({
      name: '',
      budget: '',
      preferred_type: 'Single Family',
      target_area: 'Downtown Austin',
      is_preapproved: true,
      target_property_id: properties[0]?.id || '',
      affinity_score: '95',
    });
    setShowBuyerModal(true);
  };

  const handleOpenEditBuyer = (item: BuyerProfile) => {
    setEditingBuyer(item);
    setBuyerForm({
      name: item.name,
      budget: item.budget.toString(),
      preferred_type: item.preferred_type,
      target_area: item.target_area,
      is_preapproved: item.is_preapproved,
      target_property_id: item.target_property_id || '',
      affinity_score: item.affinity_score.toString(),
    });
    setShowBuyerModal(true);
  };

  const handleSaveBuyer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!buyerForm.name || !buyerForm.budget) return;

    const payload = {
      name: buyerForm.name,
      budget: parseFloat(buyerForm.budget),
      preferred_type: buyerForm.preferred_type,
      target_area: buyerForm.target_area,
      is_preapproved: buyerForm.is_preapproved,
      target_property_id: buyerForm.target_property_id || null,
      affinity_score: parseInt(buyerForm.affinity_score) || 90,
    };

    try {
      let res;
      if (editingBuyer) {
        res = await fetch(`${apiBase}/api/v1/buyers/${editingBuyer.id}`, {
          method: 'PUT',
          headers: getHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
      } else {
        res = await fetch(`${apiBase}/api/v1/buyers`, {
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

      showToast(editingBuyer ? `Buyer profile updated: ${payload.name}` : `New prospective buyer added: ${payload.name}`);
      setShowBuyerModal(false);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteBuyer = async (id: string) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/buyers/${id}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Delete failed (Permission Denied)', 'info');
        return;
      }

      setBuyers((prev) => prev.filter((b) => b.id !== id));
      showToast('Buyer profile removed');
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  // ---------------------------------------------------------------------------
  // Deal CRUD Handlers
  // ---------------------------------------------------------------------------
  const handleOpenCreateDeal = () => {
    setEditingDeal(null);
    setDealForm({
      property_id: properties[0]?.id || '',
      buyer_id: buyers[0]?.id || '',
      contract_price: properties[0]?.price.toString() || '950000',
      closing_date: '2026-11-20',
      stage: 'UNDER_CONTRACT',
      commission_rate: '0.03',
    });
    setShowDealModal(true);
  };

  const handleOpenEditDeal = (item: DealContract) => {
    setEditingDeal(item);
    setDealForm({
      property_id: item.property_id,
      buyer_id: item.buyer_id,
      contract_price: item.contract_price.toString(),
      closing_date: item.closing_date,
      stage: item.stage,
      commission_rate: item.commission_rate.toString(),
    });
    setShowDealModal(true);
  };

  const handleSaveDeal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dealForm.property_id || !dealForm.buyer_id || !dealForm.contract_price) return;

    const payload = {
      property_id: dealForm.property_id,
      buyer_id: dealForm.buyer_id,
      contract_price: parseFloat(dealForm.contract_price),
      closing_date: dealForm.closing_date,
      stage: dealForm.stage,
      commission_rate: parseFloat(dealForm.commission_rate) || 0.03,
    };

    try {
      let res;
      if (editingDeal) {
        res = await fetch(`${apiBase}/api/v1/deals/${editingDeal.id}`, {
          method: 'PUT',
          headers: getHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(payload),
        });
      } else {
        res = await fetch(`${apiBase}/api/v1/deals`, {
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

      showToast(editingDeal ? 'Deal contract updated' : `Escrow deal created: $${payload.contract_price.toLocaleString()}`);
      setShowDealModal(false);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleToggleDealStage = async (deal: DealContract, nextStage: string) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/deals/${deal.id}`, {
        method: 'PUT',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ stage: nextStage }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Permission Denied: Cannot modify deal escrow stage', 'info');
        return;
      }

      setDeals((prev) =>
        prev.map((d) => (d.id === deal.id ? { ...d, stage: nextStage } : d))
      );
      showToast(`Deal moved to ${nextStage}`);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDeleteDeal = async (id: string) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/deals/${id}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Delete failed (Permission Denied)', 'info');
        return;
      }

      setDeals((prev) => prev.filter((d) => d.id !== id));
      showToast('Deal contract removed');
      fetchData();
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
      if (toolName === 'propsights.list_properties') {
        reply = `Retrieved ${data.count} luxury properties representing $${data.total_value.toLocaleString()} in MLS inventory. Top active listings include Skyline View Penthouse ($875k) and Heritage Craftsman ($1.15M).`;
      } else if (toolName === 'propsights.match_buyers') {
        reply = `Affinity Analysis: Found ${data.match_count} qualified buyers with >=90% affinity. Claire Robertson is matched to Skyline Penthouse (95%), and David Vance is matched to Heritage Craftsman (90%).`;
      } else if (toolName === 'propsights.get_pipeline_summary') {
        reply = `Pipeline Audit: ${data.total_deals_count} active escrow transactions totaling $${data.pipeline_volume.toLocaleString()} in contract volume ($${data.under_contract_volume.toLocaleString()} under contract). Projected brokerage commission: $${data.estimated_commissions.toLocaleString()}.`;
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

    if (txt.toLowerCase().includes('property') || txt.toLowerCase().includes('listing') || txt.toLowerCase().includes('portfolio')) {
      handleTriggerTool('propsights.list_properties', txt);
    } else if (txt.toLowerCase().includes('buyer') || txt.toLowerCase().includes('match') || txt.toLowerCase().includes('affinity')) {
      handleTriggerTool('propsights.match_buyers', txt);
    } else if (txt.toLowerCase().includes('pipeline') || txt.toLowerCase().includes('deal') || txt.toLowerCase().includes('escrow') || txt.toLowerCase().includes('contract')) {
      handleTriggerTool('propsights.get_pipeline_summary', txt);
    } else {
      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        sender: 'user',
        text: txt,
        timestamp: '10:05 AM',
      };
      const asstMsg: ChatMessage = {
        id: `asst-${Date.now()}`,
        sender: 'assistant',
        text: `I've analyzed your real estate request regarding "${txt}". Use the quick action chips below to query MLS properties, match buyers with affinity scoring, or audit active escrow deals.`,
        timestamp: '10:05 AM',
      };
      setMessages((prev) => [...prev, userMsg, asstMsg]);
    }
  };

  // Nav Items
  const navItems = [
    { id: 'dashboard', label: 'Executive Dashboard', icon: LayoutDashboard },
    { id: 'properties', label: 'Property Listings', icon: Home, badge: properties.length },
    { id: 'buyers', label: 'Prospective Buyers', icon: Users, badge: buyers.length },
    { id: 'deals', label: 'Deals & Escrow', icon: Briefcase, badge: deals.length },
    { id: 'agents', label: 'Agents & Brokers', icon: UserCheck, badge: agents.length },
  ];

  if (!isSessionChecked) {
    return (
      <div className="min-h-screen w-screen flex items-center justify-center bg-slate-950 text-rose-400">
        <RefreshCw className="w-8 h-8 animate-spin" />
      </div>
    );
  }

  if (isSessionChecked && !isLoggedIn) {
    return (
      <div className="min-h-screen w-screen flex flex-col items-center justify-center bg-gradient-to-br from-slate-950 via-slate-900 to-rose-950 text-slate-100 p-6 relative overflow-y-auto">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-rose-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col items-center mb-6 text-center z-10">
          <div className="h-14 w-14 rounded-2xl bg-gradient-to-tr from-rose-600 via-rose-500 to-amber-600 flex items-center justify-center text-white shadow-xl shadow-rose-500/25 mb-3 border border-rose-400/30">
            <Building2 className="w-7 h-7" />
          </div>
          <h1 className="text-2xl font-black tracking-tight text-white flex items-center gap-2">
            PropSights <span className="text-rose-400 font-medium text-xs px-2 py-0.5 rounded-full bg-rose-950/80 border border-rose-500/30">Realty Intelligence</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1 max-w-sm">
            MLS Property Indexing, Buyer Affinity Matching & Escrow Pipeline with PostgreSQL 16 Multi-Tenant Isolation
          </p>
        </div>

        <div className="w-full max-w-md bg-slate-900/80 border border-slate-800 rounded-2xl shadow-2xl backdrop-blur-xl p-6 z-10">
          <div className="flex p-1 bg-slate-800/80 rounded-xl mb-5 border border-slate-700/60">
            <button
              onClick={() => { setAuthTab('signin'); setAuthError(null); }}
              className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
                authTab === 'signin'
                  ? 'bg-rose-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => { setAuthTab('signup'); setAuthError(null); }}
              className={`flex-1 py-2 text-xs font-semibold rounded-lg transition-all ${
                authTab === 'signup'
                  ? 'bg-rose-600 text-white shadow-md'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Register Brokerage
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
                  placeholder="broker@austinrealty.com"
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500 focus:ring-1 focus:ring-rose-500"
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
                  className="w-full px-3.5 py-2.5 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500 focus:ring-1 focus:ring-rose-500"
                />
              </div>

              <button
                type="submit"
                disabled={isAuthLoading}
                className="w-full mt-2 py-2.5 px-4 bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-semibold text-xs rounded-xl shadow-lg shadow-rose-600/30 transition-all flex items-center justify-center gap-2 cursor-pointer"
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
                  placeholder="Victoria Sterling"
                  className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-300 mb-1">Brokerage / Company Name</label>
                <input
                  type="text"
                  value={registerCompany}
                  onChange={(e) => setRegisterCompany(e.target.value)}
                  placeholder="Highland Real Estate Group"
                  className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500"
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
                    placeholder="broker@highland.com"
                    className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500"
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
                    className="w-full px-3 py-2 bg-slate-800/80 border border-slate-700 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-[11px] font-medium text-slate-300 mb-1">Realty Role</label>
                <select
                  value={registerRole}
                  onChange={(e) => setRegisterRole(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs text-white focus:outline-none focus:border-rose-500"
                >
                  <option value="PRINCIPAL_BROKER">Principal Broker (Admin)</option>
                  <option value="LICENSED_AGENT">Licensed Agent (Agent)</option>
                  <option value="ESCROW_OFFICER">Escrow Officer (Compliance)</option>
                  <option value="CLIENT_BUYER">Client / Buyer (Viewer)</option>
                </select>
              </div>

              <button
                type="submit"
                disabled={isAuthLoading}
                className="w-full mt-2 py-2.5 px-4 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white font-semibold text-xs rounded-xl shadow-lg shadow-amber-600/30 transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                {isAuthLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                <span>{isAuthLoading ? 'Provisioning Tenant...' : 'Create Brokerage & Account'}</span>
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
                onClick={() => handleAuthLogin(undefined, 'broker@austinrealty.com', 'password123')}
                className="w-full p-2 rounded-xl bg-slate-800/70 hover:bg-rose-950/40 hover:border-rose-500/50 border border-slate-700/60 text-left transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="text-xs font-bold text-white group-hover:text-rose-300">Victoria Sterling (Principal Broker)</p>
                  <p className="text-[10px] text-slate-400">Austin Premier Realty • <span className="font-mono text-rose-400">tenant-001</span></p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 font-medium">Quick Login</span>
              </button>

              <button
                type="button"
                onClick={() => handleAuthLogin(undefined, 'agent@austinrealty.com', 'password123')}
                className="w-full p-2 rounded-xl bg-slate-800/70 hover:bg-amber-950/40 hover:border-amber-500/50 border border-slate-700/60 text-left transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="text-xs font-bold text-white group-hover:text-amber-300">Lucas Hayes (Licensed Agent)</p>
                  <p className="text-[10px] text-slate-400">Austin Premier Realty • <span className="font-mono text-amber-400">tenant-001</span></p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-medium">Quick Login</span>
              </button>

              <button
                type="button"
                onClick={() => handleAuthLogin(undefined, 'broker@lonestarrealty.com', 'password123')}
                className="w-full p-2 rounded-xl bg-slate-800/70 hover:bg-purple-950/40 hover:border-purple-500/50 border border-slate-700/60 text-left transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="text-xs font-bold text-white group-hover:text-purple-300">Harrison Ford Vance (Principal Broker)</p>
                  <p className="text-[10px] text-slate-400">Lone Star Luxury Realty • <span className="font-mono text-purple-400">tenant-002</span></p>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 font-medium">Quick Login</span>
              </button>
            </div>
          </div>
        </div>

        <div className="mt-5 text-center text-[11px] text-slate-500 flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-rose-500" />
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
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-rose-700 via-rose-600 to-amber-600 flex items-center justify-center text-white shadow-xs">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <h1 className="font-bold text-sm tracking-tight text-slate-900 leading-tight">PropSights</h1>
              <span className="text-[10px] font-semibold tracking-wide text-rose-600 uppercase">
                Realty Intelligence
              </span>
            </div>
          </div>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold font-mono bg-rose-50 text-rose-700 border border-rose-200">
            v2.0
          </span>
        </div>

        {/* Brokerage Context Banner */}
        <div className="px-4 py-2.5 bg-slate-50/70 border-b border-slate-100">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Brokerage Entity</p>
          <p className="font-semibold text-xs text-slate-800 truncate mt-0.5">
            Austin Premier Realty Network
          </p>
          <p className="text-[11px] font-mono text-slate-500">MLS ID: TX-CORE-9014</p>
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
                    ? 'bg-rose-600 text-white shadow-xs'
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
                      isActive ? 'bg-rose-700 text-white' : 'bg-slate-200/70 text-slate-600'
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
              href="http://localhost:3002"
              target="_blank"
              rel="noreferrer"
              className="p-1.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200 hover:bg-indigo-100 transition-colors flex flex-col items-center gap-0.5"
            >
              <span>TaxSnap</span>
              <span className="text-[8px] opacity-75 font-mono">:3002</span>
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
              <div className="p-2.5 rounded-xl border border-slate-200 bg-white shadow-xs">
                <div className="flex items-center gap-2.5">
                  <div className="relative shrink-0">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-rose-600 to-rose-500 text-white font-bold text-xs flex items-center justify-center shadow-xs">
                      {userName.split(' ').map((n) => n[0]).join('').slice(0, 2).toUpperCase()}
                    </div>
                    <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-white" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-bold text-slate-800 truncate">
                      {userName}
                    </p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className="inline-flex items-center px-1.5 py-0.2 rounded text-[9px] font-bold tracking-tight uppercase bg-rose-50 text-rose-700 border border-rose-200">
                        {userRole}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="mt-2 pt-1.5 border-t border-slate-100 flex items-center justify-between text-[10px] text-slate-500">
                  <span className="truncate max-w-[200px] font-medium text-slate-600" title={companyName || (tenantId === 'tenant-001' ? 'Austin Premier Realty Network' : 'Lone Star Luxury Realty')}>
                    {companyName || (tenantId === 'tenant-001' ? 'Austin Premier Realty Network' : 'Lone Star Luxury Realty')} • {tenantId}
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
              className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-semibold text-xs shadow-xs transition-all"
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
              {activeTab === 'dashboard' ? 'Real Estate Advisory & Pipeline Executive' : activeTab}
            </h2>
            <span className="text-slate-300">|</span>
            <span className="text-xs text-slate-500 font-medium">
              {tenantId === 'tenant-001' ? 'Austin Core Luxury Market' : 'Dallas-Fort Worth Luxury Estates'}
            </span>
            {userRole !== 'PRINCIPAL_BROKER' && (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200 flex items-center gap-1">
                <Shield className="w-3 h-3 text-rose-600" />
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
              onClick={() => handleTriggerTool('propsights.match_buyers', 'Match Pre-Approved Buyers')}
              className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-rose-50 text-rose-700 border border-rose-200 hover:bg-rose-100 transition-colors"
            >
              <Sparkles className="w-3.5 h-3.5 text-rose-600" />
              <span>Run Buyer Matching</span>
            </button>
            <button
              onClick={() => setIsCopilotOpen(!isCopilotOpen)}
              className={`p-2 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                isCopilotOpen
                  ? 'bg-slate-100 border-slate-300 text-slate-800'
                  : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
              }`}
            >
              <Bot className="w-4 h-4 text-rose-600" />
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
                {/* Active Listings Volume */}
                <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Active Inventory</span>
                    <div className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                      <Home className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="mt-2.5">
                    <div className="text-2xl font-bold text-slate-900 font-mono">
                      ${summary ? summary.total_listings_volume.toLocaleString() : '4,920,000'}
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-emerald-600 mt-1 font-medium">
                      <span>{summary?.active_listings_count || properties.length} MLS active listings</span>
                    </div>
                  </div>
                </div>

                {/* Under Contract Volume */}
                <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Under Contract</span>
                    <div className="w-7 h-7 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
                      <Clock className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="mt-2.5">
                    <div className="text-2xl font-bold text-amber-600 font-mono">
                      ${summary ? summary.under_contract_volume.toLocaleString() : '2,400,000'}
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-slate-500 mt-1 font-medium">
                      <span>Escrow in progress</span>
                    </div>
                  </div>
                </div>

                {/* Pre-Approved Buyers */}
                <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Matched Buyers</span>
                    <div className="w-7 h-7 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center">
                      <Users className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="mt-2.5">
                    <div className="text-2xl font-bold text-slate-900 font-mono">
                      {summary?.matched_buyers_count || buyers.length}
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-rose-600 mt-1 font-medium">
                      <span>≥90% property affinity match</span>
                    </div>
                  </div>
                </div>

                {/* Average Deal Size */}
                <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Average Deal Size</span>
                    <div className="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                      <DollarSign className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="mt-2.5">
                    <div className="text-2xl font-bold text-blue-600 font-mono">
                      ${summary ? Math.round(summary.average_deal_size).toLocaleString() : '1,632,500'}
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-slate-500 mt-1 font-medium">
                      <span>3% Standard Broker Commission</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Middle Section: Deal Escrow Pipeline + Featured Properties */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Active Escrow Pipeline */}
                <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs">
                  <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                    <div>
                      <h3 className="font-bold text-sm text-slate-900">Live Escrow & Contract Pipeline</h3>
                      <p className="text-xs text-slate-500">Track pending closings, buyer earnest money, and commissions</p>
                    </div>
                    <button
                      onClick={handleOpenCreateDeal}
                      className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg transition-colors shadow-xs"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Add Deal
                    </button>
                  </div>

                  <div className="mt-4 space-y-3">
                    {deals.map((deal) => (
                      <div
                        key={deal.id}
                        className="p-3.5 rounded-xl border border-slate-200/90 bg-slate-50/60 hover:bg-white hover:border-slate-300 hover:shadow-xs transition-all flex flex-col gap-2.5"
                      >
                        {/* Line 1: Deal Title & Status Badge */}
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <h4 className="font-bold text-xs text-slate-900 truncate flex-1 min-w-0" title={deal.property_title || 'Luxury Estate'}>
                            {deal.property_title || 'Luxury Estate'}
                          </h4>
                          <span
                            className={`text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wider shrink-0 ${
                              deal.stage === 'CLOSED'
                                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                : deal.stage === 'UNDER_CONTRACT'
                                ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                : 'bg-blue-50 text-blue-700 border border-blue-200'
                            }`}
                          >
                            {deal.stage.replace('_', ' ')}
                          </span>
                        </div>

                        {/* Line 2: Buyer & Closing Meta Badges */}
                        <div className="flex items-center gap-2 flex-wrap text-[11px]">
                          <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-700 shadow-2xs">
                            <Users className="w-3 h-3 text-slate-400 shrink-0" />
                            <span className="text-slate-500 font-normal">Buyer:</span>
                            <span className="font-semibold text-slate-800 truncate max-w-[220px]" title={deal.buyer_name}>
                              {deal.buyer_name}
                            </span>
                          </div>

                          <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-700 shadow-2xs">
                            <Calendar className="w-3 h-3 text-rose-500 shrink-0" />
                            <span className="text-slate-500 font-normal">Closing:</span>
                            <span className="font-mono font-medium text-slate-800">
                              {deal.closing_date}
                            </span>
                          </div>
                        </div>

                        {/* Line 3: Deal Amount & Calculated Commission */}
                        <div className="pt-2 border-t border-slate-200/70 flex items-center justify-between gap-2 flex-wrap text-xs">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[11px] text-slate-500">Contract Value:</span>
                            <span className="font-mono font-bold text-slate-900 text-sm">
                              ${deal.contract_price.toLocaleString()}
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] text-slate-400">Commission ({Math.round(deal.commission_rate * 100)}%):</span>
                            <span className="font-mono font-bold text-emerald-700 text-xs bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200/80">
                              +${(deal.contract_price * deal.commission_rate).toLocaleString()}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Top Matched Pre-Approved Buyers */}
                <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                      <div>
                        <h3 className="font-bold text-sm text-slate-900">Pre-Approved Buyers</h3>
                        <p className="text-xs text-slate-500">Verified purchasing capacity</p>
                      </div>
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                        {buyers.filter((b) => b.is_preapproved).length} Verified
                      </span>
                    </div>

                    <div className="mt-3.5 space-y-2.5">
                      {buyers.slice(0, 4).map((b) => (
                        <div
                          key={b.id}
                          className="p-2.5 rounded-lg border border-slate-100 bg-slate-50/60 flex items-start justify-between gap-2"
                        >
                          <div>
                            <p className="font-semibold text-xs text-slate-800">{b.name}</p>
                            <p className="text-[10px] text-slate-500 mt-0.5 font-mono">
                              Budget: ${b.budget.toLocaleString()} • {b.target_area}
                            </p>
                          </div>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 font-mono">
                            {b.affinity_score}% Match
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <button
                    onClick={() => setActiveTab('buyers')}
                    className="mt-4 w-full py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1"
                  >
                    <span>View All Buyer Profiles</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ===================================================================
              VIEW 2: PROPERTY LISTINGS
          ==================================================================== */}
          {activeTab === 'properties' && (
            <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
                <div>
                  <h3 className="font-bold text-base text-slate-900">Luxury Property Inventory (MLS)</h3>
                  <p className="text-xs text-slate-500">
                    Live residential & commercial listings across Austin Premier Realty Network
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={propStatusFilter}
                    onChange={(e) => setPropStatusFilter(e.target.value)}
                    className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-slate-50 text-slate-700 font-medium"
                  >
                    <option value="ALL">All Statuses</option>
                    <option value="AVAILABLE">Available</option>
                    <option value="UNDER_CONTRACT">Under Contract</option>
                    <option value="CLOSED">Closed</option>
                  </select>
                  <button
                    onClick={handleOpenCreateProp}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg transition-colors shadow-xs"
                  >
                    <Plus className="w-4 h-4" />
                    New Listing
                  </button>
                </div>
              </div>

              {/* Property Grid / Table */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {properties
                  .filter(
                    (p) =>
                      propStatusFilter === 'ALL' ||
                      p.status.toUpperCase() === propStatusFilter.toUpperCase()
                  )
                  .map((item) => (
                    <div
                      key={item.id}
                      className="rounded-xl border border-slate-200 p-4 bg-white hover:border-slate-300 transition-all shadow-xs flex flex-col justify-between"
                    >
                      <div>
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <h4 className="font-bold text-sm text-slate-900">{item.title}</h4>
                            <p className="text-[11px] text-slate-500 flex items-center gap-1 mt-0.5">
                              <MapPin className="w-3 h-3 text-slate-400" />
                              {item.address}
                            </p>
                          </div>
                          {/* Status Switcher Dropdown */}
                          <div className="relative inline-block">
                            <span
                              className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase cursor-pointer border ${
                                item.status === 'AVAILABLE'
                                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                  : item.status === 'UNDER_CONTRACT'
                                  ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                  : 'bg-slate-100 text-slate-600 border-slate-200'
                              }`}
                            >
                              {item.status}
                            </span>
                            <select
                              value={item.status}
                              onChange={(e) => handleTogglePropStatus(item, e.target.value)}
                              className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
                            >
                              <option value="AVAILABLE">AVAILABLE</option>
                              <option value="UNDER_CONTRACT">UNDER_CONTRACT</option>
                              <option value="CLOSED">CLOSED</option>
                            </select>
                          </div>
                        </div>

                        {/* Property Specs */}
                        <div className="flex items-center gap-4 text-xs text-slate-600 mt-3 pt-3 border-t border-slate-100">
                          <span className="flex items-center gap-1">
                            <Bed className="w-3.5 h-3.5 text-slate-400" />
                            {item.beds} Beds
                          </span>
                          <span className="flex items-center gap-1">
                            <Bath className="w-3.5 h-3.5 text-slate-400" />
                            {item.baths} Baths
                          </span>
                          <span className="flex items-center gap-1">
                            <Maximize2 className="w-3.5 h-3.5 text-slate-400" />
                            {item.sqft.toLocaleString()} sqft
                          </span>
                        </div>

                        <p className="text-[11px] text-slate-500 mt-2 line-clamp-1">
                          Amenities: {item.amenities}
                        </p>
                      </div>

                      <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                        <div>
                          <span className="text-[10px] font-semibold text-slate-400 uppercase">List Price</span>
                          <p className="font-mono font-bold text-base text-rose-600">
                            ${item.price.toLocaleString()}
                          </p>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleOpenEditProp(item)}
                            className="p-1.5 hover:bg-slate-100 text-slate-400 hover:text-slate-700 rounded transition-colors"
                            title="Edit Listing"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeleteProperty(item.id)}
                            className="p-1.5 hover:bg-rose-50 text-slate-400 hover:text-rose-600 rounded transition-colors"
                            title="Delete Listing"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* ===================================================================
              VIEW 3: PROSPECTIVE BUYERS
          ==================================================================== */}
          {activeTab === 'buyers' && (
            <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
                <div>
                  <h3 className="font-bold text-base text-slate-900">Prospective Luxury Buyers</h3>
                  <p className="text-xs text-slate-500">
                    High-net-worth client profiles, pre-approval status, and affinity match metrics
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={buyerTypeFilter}
                    onChange={(e) => setBuyerTypeFilter(e.target.value)}
                    className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-slate-50 text-slate-700 font-medium"
                  >
                    <option value="ALL">All Types</option>
                    <option value="Single Family">Single Family</option>
                    <option value="Penthouse">Penthouse</option>
                    <option value="Modern Loft">Modern Loft</option>
                    <option value="Hillside Estate">Hillside Estate</option>
                  </select>
                  <button
                    onClick={handleOpenCreateBuyer}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg transition-colors shadow-xs"
                  >
                    <Plus className="w-4 h-4" />
                    New Buyer
                  </button>
                </div>
              </div>

              {/* Buyers Table */}
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                    <tr>
                      <th className="p-3">Buyer Name</th>
                      <th className="p-3">Purchasing Budget</th>
                      <th className="p-3">Preferred Property</th>
                      <th className="p-3">Target Area</th>
                      <th className="p-3">Pre-Approval</th>
                      <th className="p-3">Affinity Match</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {buyers
                      .filter(
                        (b) =>
                          buyerTypeFilter === 'ALL' ||
                          b.preferred_type.toLowerCase().includes(buyerTypeFilter.toLowerCase())
                      )
                      .map((item) => (
                        <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="p-3 font-semibold text-slate-900">{item.name}</td>
                          <td className="p-3 font-mono font-bold text-slate-900 text-sm">
                            ${item.budget.toLocaleString()}
                          </td>
                          <td className="p-3 text-slate-700 font-medium">{item.preferred_type}</td>
                          <td className="p-3 text-slate-500">{item.target_area}</td>
                          <td className="p-3">
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                item.is_preapproved
                                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                  : 'bg-slate-100 text-slate-500'
                              }`}
                            >
                              {item.is_preapproved ? 'Pre-Approved' : 'Unverified'}
                            </span>
                          </td>
                          <td className="p-3">
                            <span className="font-mono font-bold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-full text-[10px] border border-rose-200">
                              {item.affinity_score}% Match
                            </span>
                          </td>
                          <td className="p-3 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                onClick={() => handleOpenEditBuyer(item)}
                                className="p-1.5 hover:bg-slate-100 text-slate-400 hover:text-slate-700 rounded transition-colors"
                                title="Edit Buyer"
                              >
                                <Pencil className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => handleDeleteBuyer(item.id)}
                                className="p-1.5 hover:bg-rose-50 text-slate-400 hover:text-rose-600 rounded transition-colors"
                                title="Delete Buyer"
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
              VIEW 4: DEALS & ESCROW
          ==================================================================== */}
          {activeTab === 'deals' && (
            <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
                <div>
                  <h3 className="font-bold text-base text-slate-900">Escrow Contracts & Deal Pipeline</h3>
                  <p className="text-xs text-slate-500">
                    Track offer lifecycle, contract closing milestones, and title escrow
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={dealStageFilter}
                    onChange={(e) => setDealStageFilter(e.target.value)}
                    className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-slate-50 text-slate-700 font-medium"
                  >
                    <option value="ALL">All Stages</option>
                    <option value="OFFER">Offer</option>
                    <option value="UNDER_CONTRACT">Under Contract</option>
                    <option value="CLOSED">Closed</option>
                  </select>
                  <button
                    onClick={handleOpenCreateDeal}
                    className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg transition-colors shadow-xs"
                  >
                    <Plus className="w-4 h-4" />
                    New Deal
                  </button>
                </div>
              </div>

              {/* Deals Table */}
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                    <tr>
                      <th className="p-3">Property Listing</th>
                      <th className="p-3">Buyer Name</th>
                      <th className="p-3">Contract Price</th>
                      <th className="p-3">Stage</th>
                      <th className="p-3">Estimated Commission</th>
                      <th className="p-3">Target Closing</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {deals
                      .filter(
                        (d) =>
                          dealStageFilter === 'ALL' ||
                          d.stage.toUpperCase() === dealStageFilter.toUpperCase()
                      )
                      .map((item) => (
                        <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="p-3 font-semibold text-slate-900">{item.property_title}</td>
                          <td className="p-3 text-slate-700">{item.buyer_name}</td>
                          <td className="p-3 font-mono font-bold text-slate-900 text-sm">
                            ${item.contract_price.toLocaleString()}
                          </td>
                          <td className="p-3">
                            <div className="relative inline-block">
                              <span
                                className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase cursor-pointer border ${
                                  item.stage === 'CLOSED'
                                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                    : item.stage === 'UNDER_CONTRACT'
                                    ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                    : 'bg-blue-50 text-blue-700 border border-blue-200'
                                }`}
                              >
                                {item.stage}
                              </span>
                              <select
                                value={item.stage}
                                onChange={(e) => handleToggleDealStage(item, e.target.value)}
                                className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
                              >
                                <option value="OFFER">OFFER</option>
                                <option value="UNDER_CONTRACT">UNDER_CONTRACT</option>
                                <option value="CLOSED">CLOSED</option>
                              </select>
                            </div>
                          </td>
                          <td className="p-3 font-mono text-emerald-600 font-semibold">
                            ${(item.contract_price * item.commission_rate).toLocaleString()}
                          </td>
                          <td className="p-3 text-slate-500 font-mono text-[11px]">{item.closing_date}</td>
                          <td className="p-3 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <button
                                onClick={() => handleOpenEditDeal(item)}
                                className="p-1.5 hover:bg-slate-100 text-slate-400 hover:text-slate-700 rounded transition-colors"
                                title="Edit Deal"
                              >
                                <Pencil className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => handleDeleteDeal(item.id)}
                                className="p-1.5 hover:bg-rose-50 text-slate-400 hover:text-rose-600 rounded transition-colors"
                                title="Delete Deal"
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
              VIEW 5: AGENTS & BROKERS
          ==================================================================== */}
          {activeTab === 'agents' && (
            <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-xs space-y-4">
              <div className="pb-4 border-b border-slate-100">
                <h3 className="font-bold text-base text-slate-900">Brokerage Team & Licensed Agents</h3>
                <p className="text-xs text-slate-500">
                  Austin Premier Realty roster, state licensing, and portfolio assignments
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {agents.map((agt) => (
                  <div
                    key={agt.id}
                    className="p-4 rounded-xl border border-slate-200 bg-slate-50/60 flex items-start justify-between gap-3 shadow-2xs"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="font-bold text-sm text-slate-900">{agt.name}</h4>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-200/70 text-slate-700">
                          {agt.license_no}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 mt-1">{agt.email}</p>
                      <p className="text-xs text-slate-500 font-mono mt-0.5">{agt.phone}</p>
                    </div>
                    <div className="text-right">
                      <span className="text-[10px] font-semibold text-slate-400 uppercase">Active Listings</span>
                      <p className="font-bold text-rose-600 text-lg mt-0.5">{agt.active_listings_count}</p>
                    </div>
                  </div>
                ))}
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
              <div className="w-8 h-8 rounded-lg bg-rose-600 flex items-center justify-center text-white shadow-xs">
                <Bot className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-bold text-xs text-slate-900">PropSights Intelligence Agent</h3>
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
              <ShieldCheck className="w-3.5 h-3.5 text-rose-600" />
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
              <div>role: Principal Broker Lead</div>
              <div>database: PostgreSQL 16 (practicare_db/property_listings)</div>
            </div>
          )}

          {/* Messages Stream */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3.5">
            {messages.map((m) => (
              <div key={m.id} className="space-y-1.5">
                <div className={`flex items-start gap-2 ${m.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                  {m.sender === 'assistant' && (
                    <div className="w-6 h-6 rounded-md bg-rose-100 text-rose-700 flex items-center justify-center shrink-0 mt-0.5">
                      <Sparkles className="w-3.5 h-3.5" />
                    </div>
                  )}
                  <div
                    className={`max-w-[85%] rounded-xl p-3 text-xs leading-relaxed shadow-xs ${
                      m.sender === 'user'
                        ? 'bg-rose-600 text-white font-medium'
                        : 'bg-slate-50 text-slate-800 border border-slate-200/80'
                    }`}
                  >
                    <p>{m.text}</p>
                    <span
                      className={`block text-[9px] mt-1.5 ${
                        m.sender === 'user' ? 'text-rose-200' : 'text-slate-400'
                      }`}
                    >
                      {m.timestamp}
                    </span>
                  </div>
                </div>

                {/* Tool Execution Card */}
                {m.toolCall && (
                  <div className="ml-8 rounded-lg border border-rose-100 bg-rose-50/40 p-2.5 text-[11px] space-y-1.5 shadow-2xs">
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-rose-700 text-[10px]">
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
                      className="text-[10px] text-rose-600 hover:underline flex items-center gap-1 font-semibold"
                    >
                      <span>{expandedTraceId === m.id ? 'Hide Trace Payload' : 'View Execution Trace'}</span>
                      <ChevronRight className={`w-3 h-3 transition-transform ${expandedTraceId === m.id ? 'rotate-90' : ''}`} />
                    </button>

                    {expandedTraceId === m.id && (
                      <div className="mt-1 pt-1 border-t border-rose-100 space-y-1 text-[9px] font-mono">
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

          {/* Quick Action Suggestion Chips */}
          <div className="p-3 border-t border-slate-100 bg-slate-50/50 space-y-1.5">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Quick Deal Operations
            </p>
            <div className="flex flex-wrap gap-1.5">
              <button
                onClick={() => handleTriggerTool('propsights.list_properties', 'Summarize active luxury listings')}
                className="text-[10px] font-semibold px-2 py-1 bg-white border border-slate-200 hover:border-rose-300 hover:text-rose-600 rounded-md transition-colors shadow-2xs"
              >
                Summarize active portfolio
              </button>
              <button
                onClick={() => handleTriggerTool('propsights.match_buyers', 'Match pre-approved buyers to listings')}
                className="text-[10px] font-semibold px-2 py-1 bg-white border border-slate-200 hover:border-rose-300 hover:text-rose-600 rounded-md transition-colors shadow-2xs"
              >
                Match pre-approved buyers
              </button>
              <button
                onClick={() => handleTriggerTool('propsights.get_pipeline_summary', 'Audit escrow deals under contract')}
                className="text-[10px] font-semibold px-2 py-1 bg-white border border-slate-200 hover:border-rose-300 hover:text-rose-600 rounded-md transition-colors shadow-2xs"
              >
                Audit pipeline under contract
              </button>
            </div>
          </div>

          {/* Chat Input */}
          <form onSubmit={handleSendChat} className="p-3 border-t border-slate-200 bg-white flex items-center gap-2">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Ask PropSights Copilot or query MLS..."
              className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-xs focus:bg-white focus:outline-none focus:border-rose-600"
            />
            <button
              type="submit"
              disabled={isCallingTool}
              className="p-2 bg-rose-600 hover:bg-rose-700 text-white rounded-lg transition-colors disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </form>
        </aside>
      )}

      {/* =====================================================================
          4. MODAL DIALOGS FOR CRUD
      ====================================================================== */}
      {/* MODAL 1: PROPERTY */}
      {showPropModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-sm text-slate-900">
                {editingProp ? 'Edit Property Listing' : 'Create Luxury Listing'}
              </h3>
              <button onClick={() => setShowPropModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveProperty} className="mt-4 space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Property Title *</label>
                <input
                  type="text"
                  required
                  value={propForm.title}
                  onChange={(e) => setPropForm({ ...propForm, title: e.target.value })}
                  placeholder="e.g. Skyline View Penthouse"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-rose-600"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Address *</label>
                <input
                  type="text"
                  required
                  value={propForm.address}
                  onChange={(e) => setPropForm({ ...propForm, address: e.target.value })}
                  placeholder="300 Colorado St #4201, Austin, TX 78701"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-rose-600"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">List Price ($ USD) *</label>
                  <input
                    type="number"
                    step="1000"
                    required
                    value={propForm.price}
                    onChange={(e) => setPropForm({ ...propForm, price: e.target.value })}
                    placeholder="875000"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-rose-600"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Status</label>
                  <select
                    value={propForm.status}
                    onChange={(e) => setPropForm({ ...propForm, status: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                  >
                    <option value="AVAILABLE">AVAILABLE</option>
                    <option value="UNDER_CONTRACT">UNDER_CONTRACT</option>
                    <option value="CLOSED">CLOSED</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Beds</label>
                  <input
                    type="number"
                    value={propForm.beds}
                    onChange={(e) => setPropForm({ ...propForm, beds: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Baths</label>
                  <input
                    type="number"
                    step="0.5"
                    value={propForm.baths}
                    onChange={(e) => setPropForm({ ...propForm, baths: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">SqFt</label>
                  <input
                    type="number"
                    value={propForm.sqft}
                    onChange={(e) => setPropForm({ ...propForm, sqft: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
                  />
                </div>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Amenities</label>
                <input
                  type="text"
                  value={propForm.amenities}
                  onChange={(e) => setPropForm({ ...propForm, amenities: e.target.value })}
                  placeholder="Pool, Private Elevator, Concierge"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                />
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowPropModal(false)}
                  className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Save Listing
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: BUYER */}
      {showBuyerModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-sm text-slate-900">
                {editingBuyer ? 'Edit Buyer Profile' : 'Register Prospective Buyer'}
              </h3>
              <button onClick={() => setShowBuyerModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveBuyer} className="mt-4 space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Buyer Name *</label>
                <input
                  type="text"
                  required
                  value={buyerForm.name}
                  onChange={(e) => setBuyerForm({ ...buyerForm, name: e.target.value })}
                  placeholder="e.g. Claire Robertson"
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-rose-600"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Budget ($ USD) *</label>
                  <input
                    type="number"
                    step="5000"
                    required
                    value={buyerForm.budget}
                    onChange={(e) => setBuyerForm({ ...buyerForm, budget: e.target.value })}
                    placeholder="920000"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white focus:outline-none focus:border-rose-600"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Affinity Match (%)</label>
                  <input
                    type="number"
                    min="50"
                    max="100"
                    value={buyerForm.affinity_score}
                    onChange={(e) => setBuyerForm({ ...buyerForm, affinity_score: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Preferred Type</label>
                  <select
                    value={buyerForm.preferred_type}
                    onChange={(e) => setBuyerForm({ ...buyerForm, preferred_type: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                  >
                    <option value="Single Family">Single Family</option>
                    <option value="Penthouse">Penthouse</option>
                    <option value="Modern Loft">Modern Loft</option>
                    <option value="Hillside Estate">Hillside Estate</option>
                  </select>
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Target Area</label>
                  <input
                    type="text"
                    value={buyerForm.target_area}
                    onChange={(e) => setBuyerForm({ ...buyerForm, target_area: e.target.value })}
                    placeholder="Downtown Austin"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                  />
                </div>
              </div>

              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 flex items-center justify-between">
                <div>
                  <span className="font-bold text-slate-800">Pre-Approved Buyer</span>
                  <p className="text-[10px] text-slate-500">Lender verified underwriting pre-qualification letter</p>
                </div>
                <input
                  type="checkbox"
                  checked={buyerForm.is_preapproved}
                  onChange={(e) => setBuyerForm({ ...buyerForm, is_preapproved: e.target.checked })}
                  className="w-4 h-4 text-rose-600 rounded focus:ring-rose-500"
                />
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowBuyerModal(false)}
                  className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Save Buyer
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: DEAL */}
      {showDealModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="font-bold text-sm text-slate-900">
                {editingDeal ? 'Edit Deal Contract' : 'Create Escrow Contract'}
              </h3>
              <button onClick={() => setShowDealModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveDeal} className="mt-4 space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Property Listing *</label>
                <select
                  value={dealForm.property_id}
                  onChange={(e) => setDealForm({ ...dealForm, property_id: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                >
                  {properties.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title} (${p.price.toLocaleString()})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="font-semibold text-slate-700 block mb-1">Buyer *</label>
                <select
                  value={dealForm.buyer_id}
                  onChange={(e) => setDealForm({ ...dealForm, buyer_id: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                >
                  {buyers.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name} (Budget: ${b.budget.toLocaleString()})
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Contract Price ($ USD) *</label>
                  <input
                    type="number"
                    step="1000"
                    required
                    value={dealForm.contract_price}
                    onChange={(e) => setDealForm({ ...dealForm, contract_price: e.target.value })}
                    placeholder="875000"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Stage</label>
                  <select
                    value={dealForm.stage}
                    onChange={(e) => setDealForm({ ...dealForm, stage: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                  >
                    <option value="OFFER">OFFER</option>
                    <option value="UNDER_CONTRACT">UNDER_CONTRACT</option>
                    <option value="CLOSED">CLOSED</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Closing Date</label>
                  <input
                    type="date"
                    required
                    value={dealForm.closing_date}
                    onChange={(e) => setDealForm({ ...dealForm, closing_date: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Commission Rate</label>
                  <input
                    type="number"
                    step="0.005"
                    value={dealForm.commission_rate}
                    onChange={(e) => setDealForm({ ...dealForm, commission_rate: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:bg-white font-mono"
                  />
                </div>
              </div>

              <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowDealModal(false)}
                  className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg font-semibold shadow-xs"
                >
                  Save Deal
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
                <div className="w-8 h-8 rounded-lg bg-rose-100 text-rose-700 flex items-center justify-center font-bold">
                  <ShieldCheck className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900">Switch Brokerage & User Role</h3>
                  <p className="text-[11px] text-slate-500">Real Estate Multi-Tenant Partitioning & RBAC</p>
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
                  <label className="font-semibold text-slate-700 block mb-1">Brokerage / Tenant</label>
                  <select
                    value={modalTenant}
                    onChange={(e) => setModalTenant(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-medium text-slate-800 focus:bg-white focus:outline-none focus:border-rose-600"
                  >
                    <option value="tenant-001">Austin Premier Realty (tenant-001)</option>
                    <option value="tenant-002">Lone Star Luxury Realty (tenant-002)</option>
                  </select>
                </div>

                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Assigned Role</label>
                  <select
                    value={modalRole}
                    onChange={(e) => setModalRole(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 font-medium text-slate-800 focus:bg-white focus:outline-none focus:border-rose-600"
                  >
                    <option value="PRINCIPAL_BROKER">Principal Broker (Admin)</option>
                    <option value="LICENSED_AGENT">Licensed Agent (Realtor)</option>
                    <option value="ESCROW_OFFICER">Escrow Officer (Compliance)</option>
                    <option value="CLIENT_BUYER">Client Buyer (Viewer)</option>
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
                            ? 'bg-rose-50 border-rose-400 ring-2 ring-rose-500/20'
                            : 'bg-slate-50/70 border-slate-200 hover:bg-slate-100 hover:border-slate-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-slate-900 text-xs truncate">{p.userName}</span>
                          <span className="text-[9px] px-1 py-0.2 rounded font-mono bg-slate-200/80 text-slate-700">
                            {p.tenantId}
                          </span>
                        </div>
                        <p className="text-[10px] text-rose-700 font-semibold mt-0.5">{p.roleLabel}</p>
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
                    className="px-4 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg font-semibold text-xs shadow-xs transition-all"
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
