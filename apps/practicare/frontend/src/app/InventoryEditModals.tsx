'use client';

import React, { useState } from 'react';
import { AlertTriangle, Minus, Plus, RefreshCw, X } from 'lucide-react';

// Manual inventory management for Owner / Inventory Manager: edit details and controlled stock adjustments.
// The backend re-validates everything, enforces RBAC and tenant isolation, and refuses changes against a
// stock value that changed after the form was opened (409). This UI only collects input and reports results.

export interface EditableInventoryItem {
  id: string;
  item_name: string;
  current_stock: number;
  min_threshold: number;
  unit: string;
  expiry_date?: string | null;
  room_id?: string | null;
  supplier?: string | null;
  batch_number?: string | null;
  purchase_price?: number | null;
}

interface CommonProps {
  apiBase: string;
  getHeaders: () => Record<string, string>;
  onClose: () => void;
  onSaved: () => void;
  showToast: (text: string, type?: 'success' | 'info' | 'error') => void;
}

const errorText = async (res: Response, fallback: string) => {
  const data = await res.json().catch(() => ({}));
  if (Array.isArray(data.detail)) return data.detail.map((d: { msg?: string }) => d.msg).join('; ');
  return typeof data.detail === 'string' ? data.detail : fallback;
};

const wholeNumber = (v: string) => /^\d+$/.test(v.trim());
const priceValue = (v: string) => /^\d+(\.\d{1,2})?$/.test(v.trim());

const Modal = ({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) => (
  <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
    <div className="bg-white rounded-xl border border-slate-200 shadow-xl max-w-lg w-full p-6 animate-in fade-in zoom-in-95">
      <div className="flex items-center justify-between pb-3 border-b border-slate-100">
        <h3 className="font-bold text-sm text-slate-900">{title}</h3>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Close">
          <X className="w-4 h-4" />
        </button>
      </div>
      {children}
    </div>
  </div>
);

const ErrorBox = ({ text }: { text: string }) =>
  text ? (
    <div className="p-2.5 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 flex items-start gap-2">
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
      <span>{text}</span>
    </div>
  ) : null;

// ---------------------------------------------------------------------------------------------------------
// Edit details
// ---------------------------------------------------------------------------------------------------------

export function EditInventoryModal({
  item,
  rooms,
  ...p
}: CommonProps & { item: EditableInventoryItem; rooms: { id: string; room_number: string }[] }) {
  const initial = {
    item_name: item.item_name || '',
    unit: item.unit || '',
    current_stock: String(item.current_stock ?? 0),
    min_threshold: String(item.min_threshold ?? 0),
    expiry_date: item.expiry_date || '',
    room_id: item.room_id || '',
    supplier: item.supplier || '',
    batch_number: item.batch_number || '',
    purchase_price: item.purchase_price === null || item.purchase_price === undefined ? '' : item.purchase_price.toFixed(2),
  };
  const [form, setForm] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [confirmStock, setConfirmStock] = useState(false);

  const set = (k: keyof typeof initial, v: string) => {
    setForm({ ...form, [k]: v });
    if (k === 'current_stock') setConfirmStock(false);
  };

  const validate = () => {
    if (!form.item_name.trim()) return 'Item name is required.';
    if (!form.unit.trim()) return 'Unit is required.';
    if (!wholeNumber(form.current_stock)) return 'Stock must be a whole number of 0 or more.';
    if (!wholeNumber(form.min_threshold)) return 'Minimum threshold must be a whole number of 0 or more.';
    if (form.purchase_price.trim() && !priceValue(form.purchase_price)) return 'Unit price must be 0 or more with at most 2 decimals.';
    return '';
  };

  // Only fields the user actually changed are sent, so unrelated values are never overwritten.
  const changedPayload = () => {
    const out: Record<string, string | number | null> = {};
    (Object.keys(initial) as (keyof typeof initial)[]).forEach((k) => {
      if (form[k].trim() === initial[k].trim()) return;
      const v = form[k].trim();
      if (k === 'current_stock' || k === 'min_threshold') out[k] = parseInt(v, 10);
      else out[k] = v === '' ? null : v;
    });
    return out;
  };

  const stockChanged = form.current_stock.trim() !== initial.current_stock;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving) return;
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    const payload = changedPayload();
    if (Object.keys(payload).length === 0) {
      p.onClose();
      return;
    }
    if (stockChanged && !confirmStock) {
      setConfirmStock(true);
      setError('');
      return;
    }
    if (stockChanged) payload.expected_current_stock = item.current_stock;
    setSaving(true);
    setError('');
    try {
      const res = await fetch(`${p.apiBase}/api/v1/inventory/${item.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...p.getHeaders() },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        setError(await errorText(res, 'The item was not updated.'));
        return;
      }
      p.showToast(`'${form.item_name.trim()}' updated`, 'success');
      p.onSaved();
      p.onClose();
    } catch (err) {
      console.error(err);
      setError('Could not reach the server. Nothing was saved.');
    } finally {
      setSaving(false);
    }
  };

  const input = 'w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white focus:outline-none focus:border-emerald-600';
  return (
    <Modal title={`Edit ${item.item_name}`} onClose={p.onClose}>
      <form onSubmit={handleSave} className="mt-4 space-y-3 text-xs">
        <div className="grid grid-cols-3 gap-2">
          <label className="col-span-2 font-semibold text-slate-700">
            Item name *
            <input className={input} value={form.item_name} onChange={(e) => set('item_name', e.target.value)} />
          </label>
          <label className="font-semibold text-slate-700">
            Unit *
            <input className={input} value={form.unit} onChange={(e) => set('unit', e.target.value)} />
          </label>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <label className="font-semibold text-slate-700">
            Stock quantity
            <input className={input} inputMode="numeric" value={form.current_stock} onChange={(e) => set('current_stock', e.target.value)} />
          </label>
          <label className="font-semibold text-slate-700">
            Min threshold
            <input className={input} inputMode="numeric" value={form.min_threshold} onChange={(e) => set('min_threshold', e.target.value)} />
          </label>
          <label className="font-semibold text-slate-700">
            Expiry date
            <input className={input} type="date" value={form.expiry_date} onChange={(e) => set('expiry_date', e.target.value)} />
          </label>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <label className="font-semibold text-slate-700">
            Batch no.
            <input className={input} value={form.batch_number} onChange={(e) => set('batch_number', e.target.value)} />
          </label>
          <label className="font-semibold text-slate-700">
            Supplier
            <input className={input} value={form.supplier} onChange={(e) => set('supplier', e.target.value)} />
          </label>
          <label className="font-semibold text-slate-700">
            Unit price
            <input className={input} inputMode="decimal" value={form.purchase_price} onChange={(e) => set('purchase_price', e.target.value)} />
          </label>
        </div>
        <label className="block font-semibold text-slate-700">
          Location
          <select className={input} value={form.room_id} onChange={(e) => set('room_id', e.target.value)}>
            <option value="">Central Supply</option>
            {rooms.map((r) => (
              <option key={r.id} value={r.id}>Room {r.room_number}</option>
            ))}
          </select>
        </label>
        <p className="text-[11px] text-slate-400">Clearing an optional field (expiry, batch, supplier, price) removes that value.</p>

        {confirmStock && (
          <div className="p-2.5 rounded-lg border border-amber-300 bg-amber-50 text-amber-800">
            Confirm stock change: <strong>{item.current_stock} → {form.current_stock.trim()} {form.unit}</strong>. Prefer
            “Restock / Reduce” for deliveries and usage. Press Save again to confirm.
          </div>
        )}
        <ErrorBox text={error} />

        <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
          <button type="button" onClick={p.onClose} className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium">
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg font-semibold shadow-xs flex items-center gap-1.5"
          >
            {saving && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
            {saving ? 'Saving…' : confirmStock ? 'Confirm & save' : 'Save changes'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------------------------------------
// Restock / controlled reduction
// ---------------------------------------------------------------------------------------------------------

export function AdjustStockModal({ item, ...p }: CommonProps & { item: EditableInventoryItem }) {
  const [mode, setMode] = useState<'restock' | 'reduce'>('restock');
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const qty = wholeNumber(amount) ? parseInt(amount, 10) : NaN;
  const change = mode === 'restock' ? qty : -qty;
  const newStock = item.current_stock + change;
  const problem = !(qty > 0)
    ? 'Enter a whole number greater than 0.'
    : newStock < 0
    ? `Cannot remove ${qty} ${item.unit}: only ${item.current_stock} ${item.unit} in stock.`
    : '';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving) return;
    if (problem) {
      setError(problem);
      return;
    }
    if (!reviewing) {
      setReviewing(true);
      setError('');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const res = await fetch(`${p.apiBase}/api/v1/inventory/${item.id}/adjust`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...p.getHeaders() },
        body: JSON.stringify({ quantity_change: change, expected_current_stock: item.current_stock, reason: reason.trim() || null }),
      });
      if (!res.ok) {
        setError(await errorText(res, 'Stock was not changed.'));
        setReviewing(false);
        if (res.status === 409) p.onSaved(); // refresh so the user sees the current quantity
        return;
      }
      const saved = await res.json();
      p.showToast(`${item.item_name}: ${item.current_stock} → ${saved.current_stock} ${item.unit}`, 'success');
      p.onSaved();
      p.onClose();
    } catch (err) {
      console.error(err);
      setError('Could not reach the server. Stock was not changed.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={`Adjust stock — ${item.item_name}`} onClose={p.onClose}>
      <form onSubmit={handleSubmit} className="mt-4 space-y-3 text-xs">
        <div className="flex gap-2">
          {(['restock', 'reduce'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => {
                setMode(m);
                setReviewing(false);
              }}
              className={`px-3 py-1.5 rounded-lg border font-semibold flex items-center gap-1 ${
                mode === m ? 'border-emerald-600 bg-emerald-50 text-emerald-800' : 'border-slate-200 text-slate-600'
              }`}
            >
              {m === 'restock' ? <Plus className="w-3.5 h-3.5" /> : <Minus className="w-3.5 h-3.5" />}
              {m === 'restock' ? 'Restock (add)' : 'Reduce (use / discard)'}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="font-semibold text-slate-700">
            Quantity ({item.unit})
            <input
              className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
              inputMode="numeric"
              value={amount}
              onChange={(e) => {
                setAmount(e.target.value);
                setReviewing(false);
              }}
            />
          </label>
          <label className="font-semibold text-slate-700">
            Reason (optional)
            <input
              className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2 focus:bg-white"
              value={reason}
              maxLength={200}
              placeholder={mode === 'restock' ? 'Delivery received' : 'Used in Room 101'}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
        </div>
        <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-slate-700">
          Current: <strong>{item.current_stock} {item.unit}</strong>
          {!problem && (
            <>
              {' '}→ New: <strong>{newStock} {item.unit}</strong> ({change > 0 ? '+' : ''}{change})
            </>
          )}
        </div>
        {reviewing && !problem && (
          <div className="p-2.5 rounded-lg border border-amber-300 bg-amber-50 text-amber-800">
            Confirm: {mode === 'restock' ? 'add' : 'remove'} <strong>{qty} {item.unit}</strong>. If someone else changes this
            item first, nothing is applied.
          </div>
        )}
        <ErrorBox text={error} />
        <div className="pt-3 flex justify-end gap-2 border-t border-slate-100">
          <button type="button" onClick={p.onClose} className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium">
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg font-semibold shadow-xs flex items-center gap-1.5"
          >
            {saving && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
            {saving ? 'Saving…' : reviewing ? 'Confirm adjustment' : 'Review adjustment'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
