'use client';

import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, FileText, Image as ImageIcon, RefreshCw, Type, Upload, X } from 'lucide-react';

// AI inventory import: upload (PDF / image) or paste text -> Gemini extraction -> editable preview ->
// explicit confirmation -> server-side validation and a single transactional import.
// The server decides everything that matters (validation, duplicates, idempotency); this UI only edits and reports.

type SourceType = 'pdf' | 'image' | 'text';
type RowAction = 'create' | 'restock' | 'skip';
type IssueLevel = 'error' | 'warning' | 'info';

interface PreviewIssue {
  field: string;
  level: IssueLevel;
  message: string;
}

interface ExistingItem {
  item_id: string;
  name: string;
  current_stock: number;
  unit: string;
  expiry_date?: string | null;
  batch_number?: string | null;
  supplier?: string | null;
}

interface PreviewRow {
  row_id: string;
  values: Record<string, string | number | null>;
  confidence: Record<string, string>;
  issues: PreviewIssue[];
  match: {
    status: 'new' | 'existing_match' | 'similar_exists' | 'duplicate_in_import';
    existing_item_id?: string | null;
    existing?: ExistingItem | null;
    duplicate_of_row?: string;
    similar?: ExistingItem[];
  };
  action: RowAction;
}

interface PreviewResponse {
  import_token: string;
  source_hash: string;
  source_type: SourceType;
  filename?: string | null;
  notes?: string;
  truncated?: boolean;
  previous_imports: { import_id: string; imported_at: string | null; created_count: number; updated_count: number }[];
  rows: PreviewRow[];
}

interface ImportResult {
  status: 'IMPORTED' | 'NOTHING_IMPORTED';
  counts: { created: number; updated: number; skipped: number; rejected: number };
  created: { row_id: string; item_id: string; item_name: string; quantity: number; unit: string }[];
  updated: {
    row_id: string;
    item_id: string;
    item_name: string;
    quantity_added: number;
    previous_stock: number;
    new_stock: number;
    fields_filled: string[];
    kept_existing: { field: string; kept: string; document_value: string }[];
  }[];
  skipped: { row_id: string; item_name: string; reason: string }[];
  rejected: { row_id: string; item_name: string; errors: string[] }[];
}

interface EditableRow {
  row_id: string;
  action: RowAction;
  existing_item_id: string | null;
  values: Record<string, string>;
  edited: Set<string>;
  preview: PreviewRow;
}

interface Props {
  apiBase: string;
  getHeaders: () => Record<string, string>;
  rooms: { id: string; room_number: string }[];
  onClose: () => void;
  onImported: () => void;
  showToast: (text: string, type?: 'success' | 'info' | 'error') => void;
}

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const EDITABLE_FIELDS: { key: string; label: string; width: string }[] = [
  { key: 'item_name', label: 'Item *', width: 'min-w-[150px]' },
  { key: 'quantity', label: 'Qty *', width: 'w-16' },
  { key: 'unit', label: 'Unit *', width: 'w-20' },
  { key: 'expiry_date', label: 'Expiry (YYYY-MM-DD)', width: 'w-28' },
  { key: 'batch_number', label: 'Batch', width: 'w-24' },
  { key: 'supplier', label: 'Supplier', width: 'w-28' },
  { key: 'purchase_price', label: 'Unit price', width: 'w-20' },
  { key: 'min_threshold', label: 'Min (default 10)', width: 'w-16' },
];

const toEditable = (row: PreviewRow): EditableRow => ({
  row_id: row.row_id,
  action: row.action,
  existing_item_id: row.match.existing_item_id || null,
  values: Object.fromEntries(
    [...EDITABLE_FIELDS.map((f) => f.key), 'room_id'].map((k) => [k, row.values[k] == null ? '' : String(row.values[k])])
  ),
  edited: new Set(),
  preview: row,
});

const readFileAsBase64 = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1] || '');
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });

export default function InventoryImportModal({ apiBase, getHeaders, rooms, onClose, onImported, showToast }: Props) {
  const [sourceType, setSourceType] = useState<SourceType>('pdf');
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [rows, setRows] = useState<EditableRow[]>([]);
  const [reviewed, setReviewed] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);

  const resetPreview = () => {
    setPreview(null);
    setRows([]);
    setReviewed(false);
    setResult(null);
    setError('');
  };

  const handleExtract = async () => {
    setError('');
    let body: Record<string, string>;
    if (sourceType === 'text') {
      if (!text.trim()) {
        setError('Paste or type the inventory lines to import.');
        return;
      }
      body = { source_type: 'text', text };
    } else {
      if (!file) {
        setError(`Choose a ${sourceType === 'pdf' ? 'PDF document' : 'image'} first.`);
        return;
      }
      if (file.size > MAX_FILE_BYTES) {
        setError('File is too large (maximum 10 MB).');
        return;
      }
      body = {
        source_type: sourceType,
        filename: file.name,
        mime_type: file.type,
        content_base64: await readFileAsBase64(file),
      };
    }
    setExtracting(true);
    try {
      const res = await fetch(`${apiBase}/api/v1/inventory/import/extract`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getHeaders() },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(typeof data.detail === 'string' ? data.detail : 'Extraction failed. Nothing was imported.');
        return;
      }
      const prev = data as PreviewResponse;
      setPreview(prev);
      setRows(prev.rows.map(toEditable));
      setReviewed(false);
      setResult(null);
      if (prev.rows.length === 0) setError('No inventory records were found in this source. Nothing will be imported.');
    } catch (e) {
      console.error(e);
      setError('Could not reach the server. Nothing was imported.');
    } finally {
      setExtracting(false);
    }
  };

  const updateRow = (rowId: string, patch: Partial<EditableRow>) =>
    setRows((prev) => prev.map((r) => (r.row_id === rowId ? { ...r, ...patch } : r)));

  const updateValue = (row: EditableRow, key: string, value: string) => {
    const edited = new Set(row.edited);
    edited.add(key);
    updateRow(row.row_id, { values: { ...row.values, [key]: value }, edited });
  };

  // Highlight from the server's flags until the user edits that field (the server re-validates on confirm).
  const cellTone = (row: EditableRow, key: string) => {
    if (row.action === 'skip' || row.edited.has(key)) return 'border-slate-200 bg-white';
    const issues = row.preview.issues.filter((i) => i.field === key);
    if (issues.some((i) => i.level === 'error')) return 'border-rose-400 bg-rose-50';
    const conf = row.preview.confidence[key];
    if (issues.some((i) => i.level === 'warning') || conf === 'low' || conf === 'medium') return 'border-amber-400 bg-amber-50';
    if (conf === 'missing') return 'border-dashed border-slate-300 bg-slate-50';
    return 'border-slate-200 bg-white';
  };

  const handleConfirm = async () => {
    if (!preview || !reviewed) return;
    setConfirming(true);
    setError('');
    try {
      const res = await fetch(`${apiBase}/api/v1/inventory/import/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getHeaders() },
        body: JSON.stringify({
          import_token: preview.import_token,
          source_hash: preview.source_hash,
          source_type: preview.source_type,
          rows: rows.map((r) => ({
            row_id: r.row_id,
            action: r.action,
            existing_item_id: r.action === 'restock' ? r.existing_item_id : null,
            ...Object.fromEntries(Object.entries(r.values).map(([k, v]) => [k, v.trim() === '' ? null : v.trim()])),
          })),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.status === 409) {
        setError(data.detail?.message || 'This import was already confirmed; nothing was imported again.');
        if (data.detail?.previous_result) setResult(data.detail.previous_result as ImportResult);
        return;
      }
      if (!res.ok) {
        setError(typeof data.detail === 'string' ? data.detail : 'Import failed. Nothing was saved.');
        return;
      }
      const out = data as ImportResult;
      setResult(out);
      if (out.status === 'IMPORTED') {
        showToast(`Inventory import saved: ${out.counts.created} created, ${out.counts.updated} updated.`, 'success');
        onImported();
      } else {
        setError('Nothing was imported. Fix the rejected rows below and confirm again, or skip them.');
        setReviewed(false);
      }
    } catch (e) {
      console.error(e);
      setError('Could not reach the server. The import was not confirmed.');
    } finally {
      setConfirming(false);
    }
  };

  const activeRows = rows.filter((r) => r.action !== 'skip').length;
  const rejectedIds = new Set((result?.rejected || []).map((r) => r.row_id));
  const imported = result?.status === 'IMPORTED';

  return (
    <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl border border-slate-200 shadow-xl w-full max-w-6xl max-h-[92vh] flex flex-col animate-in fade-in zoom-in-95">
        <div className="flex items-center justify-between p-5 pb-3 border-b border-slate-100">
          <div>
            <h3 className="font-bold text-sm text-slate-900">Import Inventory with AI</h3>
            <p className="text-[11px] text-slate-500">
              Extract records from a PDF, an image or text. Review and correct every row; nothing is saved until you confirm.
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Close">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-4 overflow-y-auto text-xs">
          {!preview && (
            <>
              <div className="flex gap-2">
                {([
                  { id: 'pdf', label: 'PDF document', icon: FileText },
                  { id: 'image', label: 'Image (JPG, PNG…)', icon: ImageIcon },
                  { id: 'text', label: 'Text', icon: Type },
                ] as const).map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    onClick={() => {
                      setSourceType(id);
                      setFile(null);
                      setError('');
                    }}
                    className={`px-3 py-2 rounded-lg border flex items-center gap-1.5 font-semibold ${
                      sourceType === id ? 'border-emerald-600 bg-emerald-50 text-emerald-800' : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    {label}
                  </button>
                ))}
              </div>

              {sourceType === 'text' ? (
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={8}
                  placeholder={'One item per line, e.g.\nNitrile gloves M, 20 boxes, batch NG-221, exp 2027-06-30, MedCo, $8.50/box\nLidocaine 2% 5ml, 12 vials, exp 2026-12-31'}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg p-2.5 font-mono focus:bg-white focus:outline-none focus:border-emerald-600"
                />
              ) : (
                <label className="block border-2 border-dashed border-slate-200 rounded-xl p-6 text-center cursor-pointer hover:border-emerald-400">
                  <Upload className="w-6 h-6 text-slate-400 mx-auto mb-1" />
                  <span className="font-semibold text-slate-700">{file ? file.name : `Choose a ${sourceType === 'pdf' ? 'PDF' : 'JPG, PNG, WEBP or HEIC'} file`}</span>
                  <span className="block text-slate-400 mt-0.5">Maximum 10 MB</span>
                  <input
                    type="file"
                    className="hidden"
                    accept={sourceType === 'pdf' ? 'application/pdf,.pdf' : 'image/jpeg,image/png,image/webp,image/heic,image/heif'}
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                  />
                </label>
              )}
            </>
          )}

          {error && (
            <div className="p-2.5 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {preview && preview.previous_imports.length > 0 && !imported && (
            <div className="p-2.5 rounded-lg border border-amber-300 bg-amber-50 text-amber-800 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                This exact {preview.source_type === 'text' ? 'text' : 'file'} was already imported
                {preview.previous_imports[0].imported_at ? ` on ${preview.previous_imports[0].imported_at.slice(0, 16).replace('T', ' ')}` : ''}.
                Rows matching existing records are set to <strong>Skip</strong>.
              </span>
            </div>
          )}
          {preview?.truncated && <p className="text-amber-700">Only the first 200 records were extracted.</p>}
          {preview?.notes && <p className="text-slate-500">AI note: {preview.notes}</p>}

          {preview && rows.length > 0 && !imported && (
            <>
              <div className="flex flex-wrap gap-3 text-[11px] text-slate-500">
                <span><span className="inline-block w-3 h-3 align-middle rounded border border-rose-400 bg-rose-50 mr-1" />Missing / invalid — must fix</span>
                <span><span className="inline-block w-3 h-3 align-middle rounded border border-amber-400 bg-amber-50 mr-1" />Low confidence / ambiguous — verify</span>
                <span><span className="inline-block w-3 h-3 align-middle rounded border border-dashed border-slate-300 bg-slate-50 mr-1" />Not in document — stays empty</span>
              </div>
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-left text-[11px]">
                  <thead className="bg-slate-50 text-slate-500 uppercase tracking-wider font-semibold border-b border-slate-200">
                    <tr>
                      <th className="p-2">Action</th>
                      {EDITABLE_FIELDS.map((f) => (
                        <th key={f.key} className="p-2 whitespace-nowrap">{f.label}</th>
                      ))}
                      <th className="p-2">Location</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {rows.map((row) => {
                      const m = row.preview.match;
                      return (
                        <React.Fragment key={row.row_id}>
                          <tr className={`${row.action === 'skip' ? 'opacity-50' : ''} ${rejectedIds.has(row.row_id) ? 'bg-rose-50/60' : ''}`}>
                            <td className="p-2 align-top">
                              <select
                                value={row.action}
                                onChange={(e) => updateRow(row.row_id, { action: e.target.value as RowAction })}
                                className="border border-slate-200 rounded p-1 bg-white"
                              >
                                <option value="create">Create new</option>
                                {m.existing_item_id && <option value="restock">Add to stock</option>}
                                <option value="skip">Skip</option>
                              </select>
                            </td>
                            {EDITABLE_FIELDS.map((f) => (
                              <td key={f.key} className="p-1.5 align-top">
                                <input
                                  value={row.values[f.key]}
                                  onChange={(e) => updateValue(row, f.key, e.target.value)}
                                  disabled={row.action === 'skip'}
                                  className={`${f.width} w-full border rounded p-1 font-mono ${cellTone(row, f.key)}`}
                                />
                              </td>
                            ))}
                            <td className="p-1.5 align-top">
                              <select
                                value={row.values.room_id}
                                onChange={(e) => updateValue(row, 'room_id', e.target.value)}
                                disabled={row.action !== 'create'}
                                className="border border-slate-200 rounded p-1 bg-white"
                              >
                                <option value="">Central Supply</option>
                                {rooms.map((r) => (
                                  <option key={r.id} value={r.id}>Room {r.room_number}</option>
                                ))}
                              </select>
                            </td>
                          </tr>
                          <tr className={row.action === 'skip' ? 'opacity-50' : ''}>
                            <td colSpan={EDITABLE_FIELDS.length + 2} className="px-2 pb-2 pt-0">
                              <div className="flex flex-col gap-0.5">
                                {m.status === 'existing_match' && m.existing && (
                                  <span className="text-amber-700 font-semibold">
                                    Matches existing {m.existing.item_id}: {m.existing.current_stock} {m.existing.unit}
                                    {m.existing.batch_number ? `, batch ${m.existing.batch_number}` : ''}
                                    {m.existing.expiry_date ? `, exp ${m.existing.expiry_date}` : ''}. Choose “Add to stock” to restock it.
                                  </span>
                                )}
                                {m.status === 'duplicate_in_import' && (
                                  <span className="text-amber-700 font-semibold">Duplicate of {m.duplicate_of_row} in this import.</span>
                                )}
                                {row.preview.issues
                                  .filter((i) => !(i.level === 'info' && i.field === 'min_threshold'))
                                  .filter((i) => !row.edited.has(i.field))
                                  .map((i, idx) => (
                                    <span
                                      key={idx}
                                      className={i.level === 'error' ? 'text-rose-700' : i.level === 'warning' ? 'text-amber-700' : 'text-slate-400'}
                                    >
                                      {i.level === 'error' ? '✖' : i.level === 'warning' ? '⚠' : 'ℹ'} {i.message}
                                    </span>
                                  ))}
                                {result?.rejected
                                  .filter((r) => r.row_id === row.row_id)
                                  .flatMap((r) => r.errors)
                                  .map((msg, idx) => (
                                    <span key={`rej-${idx}`} className="text-rose-700 font-semibold">✖ Rejected: {msg}</span>
                                  ))}
                              </div>
                            </td>
                          </tr>
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <label className="flex items-center gap-2 font-semibold text-slate-700">
                <input type="checkbox" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} />
                I have reviewed these {activeRows} record(s) and want to save them.
              </label>
            </>
          )}

          {result && (
            <div className="space-y-2">
              <div className={`p-3 rounded-lg border ${imported ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-slate-200 bg-slate-50 text-slate-700'}`}>
                <div className="font-bold flex items-center gap-1.5">
                  {imported && <CheckCircle2 className="w-4 h-4" />}
                  {result.counts.created} created · {result.counts.updated} updated · {result.counts.skipped} skipped · {result.counts.rejected} rejected
                </div>
              </div>
              {result.created.length > 0 && (
                <ul className="list-disc pl-5 text-slate-700">
                  {result.created.map((c) => (
                    <li key={c.row_id}>Created <span className="font-mono">{c.item_id}</span> — {c.item_name} ({c.quantity} {c.unit})</li>
                  ))}
                </ul>
              )}
              {result.updated.length > 0 && (
                <ul className="list-disc pl-5 text-slate-700">
                  {result.updated.map((u) => (
                    <li key={u.row_id}>
                      Restocked <span className="font-mono">{u.item_id}</span> — {u.item_name}: {u.previous_stock} → {u.new_stock}
                      {u.fields_filled.length > 0 && ` (filled: ${u.fields_filled.join(', ')})`}
                      {u.kept_existing.map((k) => ` · kept ${k.field} “${k.kept}” (document said “${k.document_value}”)`).join('')}
                    </li>
                  ))}
                </ul>
              )}
              {imported && result.rejected.length > 0 && (
                <ul className="list-disc pl-5 text-rose-700">
                  {result.rejected.map((r) => (
                    <li key={r.row_id}>Rejected {r.row_id} — {r.item_name}: {r.errors.join(' ')}</li>
                  ))}
                </ul>
              )}
              {imported && result.skipped.length > 0 && (
                <p className="text-slate-500">Skipped: {result.skipped.map((s) => `${s.row_id} ${s.item_name}`).join(', ')}</p>
              )}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-slate-100 flex justify-between gap-2 text-xs">
          <div>
            {preview && !imported && (
              <button onClick={resetPreview} className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium">
                Start over
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded-lg font-medium">
              {imported ? 'Close' : 'Cancel'}
            </button>
            {!preview && (
              <button
                onClick={handleExtract}
                disabled={extracting}
                className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white rounded-lg font-semibold shadow-xs flex items-center gap-1.5"
              >
                {extracting && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                {extracting ? 'Extracting…' : 'Extract records'}
              </button>
            )}
            {preview && rows.length > 0 && !imported && (
              <button
                onClick={handleConfirm}
                disabled={!reviewed || confirming || activeRows === 0}
                className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg font-semibold shadow-xs"
              >
                {confirming ? 'Saving…' : `Confirm import (${activeRows})`}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
